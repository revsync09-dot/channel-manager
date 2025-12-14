"""
Web dashboard backend using Flask with Discord OAuth2.
"""
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response, stream_with_context
from flask_cors import CORS
import requests
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import time
from functools import wraps
import json
import secrets
import urllib.parse
from typing import Dict, Tuple, Optional

# Add parent directory to path for imports (when run as a script)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from src.database import db
except ImportError:
    # Fallback: ensure project root is on path, then retry
    root_dir = Path(__file__).resolve().parents[2]
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    from src.database import db

try:
    from src.modules.text_parser import parse_text_structure
except Exception:
    # fallback if import path differs when run as module
    try:
        from modules.text_parser import parse_text_structure
    except Exception:
        parse_text_structure = None


app = Flask(__name__, 
            template_folder='../../web/templates',
            static_folder='../../web/static')
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
CORS(app)

# Discord OAuth2 Config
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "https://jthweb.yugp.me/callback")
DISCORD_API_BASE = "https://discord.com/api/v10"
# Redirect must be URL-encoded to avoid invalid redirect URI errors
_encoded_redirect = urllib.parse.quote_plus(DISCORD_REDIRECT_URI)
DISCORD_OAUTH_URL = (
    f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}"
    f"&redirect_uri={_encoded_redirect}&response_type=code&scope=identify+guilds"
)

# Simple in-process cache to avoid flapping presence checks and API spam
_BOT_GUILD_CACHE: Dict[str, Tuple[float, list, Optional[str]]] = {}
_BOT_GUILD_TTL_SECONDS = 30


def validate_oauth_env():
    if not DISCORD_CLIENT_ID:
        raise RuntimeError("DISCORD_CLIENT_ID missing in environment")
    if not DISCORD_CLIENT_SECRET:
        raise RuntimeError("DISCORD_CLIENT_SECRET missing in environment")
    if not DISCORD_REDIRECT_URI:
        raise RuntimeError("DISCORD_REDIRECT_URI missing in environment")
    # Print a quick sanity log (no secrets)
    print("[OAUTH] CLIENT_ID=", DISCORD_CLIENT_ID)
    print("[OAUTH] REDIRECT_URI=", DISCORD_REDIRECT_URI)
    print("[OAUTH] AUTH URL=", DISCORD_OAUTH_URL)


def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def get_discord_user(access_token):
    """Get Discord user info from access token"""
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{DISCORD_API_BASE}/users/@me", headers=headers)
    if response.status_code == 200:
        return response.json()
    return None


def _refresh_access_token_if_needed(session_id: str) -> bool:
    """Attempt to refresh an expired access token for dashboard sessions.
    Returns True if refresh succeeded and session updated, False otherwise.
    """
    sess = db.get_session(session_id)
    if not sess:
        return False
    refresh_token = sess.get('refresh_token')
    if not refresh_token:
        return False
    # Exchange token
    data = {
        'client_id': DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'redirect_uri': DISCORD_REDIRECT_URI,
        'scope': 'identify guilds'
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post(f"{DISCORD_API_BASE}/oauth2/token", data=data, headers=headers)
    if response.status_code != 200:
        return False
    token_data = response.json()
    new_access_token = token_data.get('access_token')
    new_refresh_token = token_data.get('refresh_token')
    expires_in = token_data.get('expires_in', 604800)
    new_expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
    try:
        db.update_session(session_id, new_access_token, new_refresh_token, new_expires_at)
        # Also update the Flask session so subsequent requests use the new token
        session['access_token'] = new_access_token
        session['session_id'] = session_id
        return True
    except Exception:
        return False


def get_user_guilds(access_token):
    """Get user's Discord guilds"""
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{DISCORD_API_BASE}/users/@me/guilds", headers=headers)
    if response.status_code == 200:
        return response.json()
    return []


def get_user_guilds_with_refresh(session_id: str):
    """Fetch the user's guilds using the session ID and refresh tokens if needed."""
    access_token = session.get('access_token')
    guilds = get_user_guilds(access_token)
    if guilds:
        return guilds
    # Try refresh if session exists
    if session_id and _refresh_access_token_if_needed(session_id):
        access_token = session.get('access_token')
        return get_user_guilds(access_token)
    return []


def _has_guild_access(guild_id: int) -> bool:
    """Helper to test if current session user has Manage Server or Administrator access for a guild."""
    sess_id = session.get('session_id')
    guilds = get_user_guilds_with_refresh(sess_id)
    for g in guilds:
        try:
            if int(g.get('id')) == guild_id:
                permissions = int(g.get('permissions', 0))
                if permissions & 0x20 or permissions & 0x8:
                    return True
        except Exception:
            continue
    return False


def get_bot_guilds(bot_token):
    """Get bot's guilds (fall back to DISCORD_TOKEN if DISCORD_BOT_TOKEN is not set).

    Returns a list of guild objects or [] on error.
    """
    if not bot_token:
        bot_token = os.getenv('DISCORD_TOKEN')
        if bot_token:
            print('[INFO] Using DISCORD_TOKEN as bot token fallback for get_bot_guilds')
    if not bot_token:
        print('[WARN] No bot token provided for get_bot_guilds')
        return []
    headers = {"Authorization": f"Bot {bot_token}"}
    response = requests.get(f"{DISCORD_API_BASE}/users/@me/guilds", headers=headers)
    if response.status_code == 200:
        return response.json()
    # Log helpful debugging info
    if response.status_code == 401:
        print('[WARN] Unauthorized bot token for get_bot_guilds (401). Check DISCORD_BOT_TOKEN / DISCORD_TOKEN values and ensure it is a Bot token.')
    else:
        print(f'[WARN] get_bot_guilds returned HTTP {response.status_code}: {response.text[:200]}')
    return []


def get_bot_guilds_with_reason(bot_token):
    """Return bot guilds and an optional reason string for failure with short TTL cache."""
    token = bot_token or os.getenv('DISCORD_TOKEN')
    if not token:
        return [], 'missing-token'

    now = time.time()
    cached = _BOT_GUILD_CACHE.get(token)
    if cached and (now - cached[0]) < _BOT_GUILD_TTL_SECONDS:
        return cached[1], cached[2]

    headers = {"Authorization": f"Bot {token}"}
    response = requests.get(f"{DISCORD_API_BASE}/users/@me/guilds", headers=headers)
    guilds: list = []
    reason: Optional[str] = None
    if response.status_code == 200:
        guilds = response.json()
    elif response.status_code == 401:
        reason = 'unauthorized-token'
    else:
        reason = f'http-{response.status_code}'

    _BOT_GUILD_CACHE[token] = (now, guilds, reason)
    return guilds, reason


def get_bot_token():
    """Return the bot token used by the dashboard (DISCORD_BOT_TOKEN or fallback to DISCORD_TOKEN)."""
    return os.getenv('DISCORD_BOT_TOKEN') or os.getenv('DISCORD_TOKEN')


@app.route('/')
def index():
    """Home page"""
    if 'user' in session:
        return redirect(url_for('dashboard'))
    
    return render_template('index.html')


@app.route('/login')
def login():
    """Redirect to Discord OAuth"""
    return redirect(DISCORD_OAUTH_URL)


@app.route('/callback')
def callback():
    """OAuth callback"""
    code = request.args.get('code')
    if not code:
        return "No code provided", 400
    
    # Exchange code for token
    data = {
        'client_id': DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': DISCORD_REDIRECT_URI,
        'scope': 'identify guilds'
    }
    
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post(f"{DISCORD_API_BASE}/oauth2/token", data=data, headers=headers)
    
    if response.status_code != 200:
        return "Failed to get access token", 400
    
    token_data = response.json()
    access_token = token_data.get('access_token')
    refresh_token = token_data.get('refresh_token')
    expires_in = token_data.get('expires_in', 604800)
    
    # Get user info
    user = get_discord_user(access_token)
    if not user:
        return "Failed to get user info", 400
    
    # Store in session
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    
    db.create_session(session_id, int(user['id']), access_token, refresh_token, expires_at.isoformat())
    
    session['user'] = user
    session['session_id'] = session_id
    session['access_token'] = access_token
    
    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    """Logout"""
    if 'session_id' in session:
        db.delete_session(session['session_id'])
    
    session.clear()
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard"""
    access_token = session.get('access_token')
    user = session.get('user')
    
    # Get user's guilds with refresh support
    guilds = get_user_guilds_with_refresh(session.get('session_id'))
    
    # Filter guilds where user has manage server permission
    admin_guilds = []
    for guild in guilds:
        permissions = int(guild.get('permissions', 0))
        # Check if user has MANAGE_GUILD (0x20) or ADMINISTRATOR (0x8)
        if permissions & 0x20 or permissions & 0x8:
            admin_guilds.append(guild)
    
    return render_template('dashboard.html', user=user, guilds=admin_guilds)


@app.route('/dashboard/guild/<int:guild_id>')
@login_required
def guild_dashboard(guild_id):
    """Guild-specific dashboard"""
    access_token = session.get('access_token')
    user = session.get('user')
    
    # Verify user has access to this guild
    guilds = get_user_guilds_with_refresh(session.get('session_id'))
    guild = None
    for g in guilds:
        if int(g['id']) == guild_id:
            permissions = int(g.get('permissions', 0))
            if permissions & 0x20 or permissions & 0x8:
                guild = g
                break
    
    if not guild:
        return "Unauthorized", 403
    
    # Get guild config from database
    config = db.get_guild_config(guild_id) or {}
    custom_commands = db.get_custom_commands(guild_id)
    
    # Add bot client ID for invite link
    config['bot_client_id'] = DISCORD_CLIENT_ID
    # Check if bot is present in this guild
    bot_token = os.getenv('DISCORD_BOT_TOKEN')
    bot_present = False
    bot_present_reason = None
    if bot_token or os.getenv('DISCORD_TOKEN'):
        try:
            bot_guilds, reason = get_bot_guilds_with_reason(bot_token)
            bot_present_reason = reason
            bot_present = any(int(g.get('id')) == guild_id for g in (bot_guilds or []))
        except Exception:
            bot_present_reason = 'error'
            bot_present = False
    else:
        bot_present_reason = 'missing-token'
    config['bot_present'] = bot_present
    config['bot_present_reason'] = bot_present_reason
    
    return render_template('guild_dashboard_enhanced.html', 
                         user=user, 
                         guild=guild,
                         config=config,
                         custom_commands=custom_commands)


@app.route('/api/guild/<int:guild_id>/config', methods=['GET', 'POST'])
@login_required
def api_guild_config(guild_id):
    """API endpoint for guild config"""
    if request.method == 'GET':
        config = db.get_guild_config(guild_id)
        return jsonify(config or {})
    
    elif request.method == 'POST':
        data = request.json
        
        # Validate user has access
        if not _has_guild_access(guild_id):
            return jsonify({"error": "Unauthorized or session expired. Ensure you're signed in and have Manage Server or Administrator permissions."}), 403
        
        # Update config
        db.set_guild_config(guild_id, **data)
        
        return jsonify({"success": True})


@app.route('/api/guild/<int:guild_id>/commands', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_custom_commands(guild_id):
    """API endpoint for custom commands"""
    # Validate user has access
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired. Ensure you're signed in and have Manage Server or Administrator permissions."}), 403
    
    if request.method == 'GET':
        commands = db.get_custom_commands(guild_id)
        return jsonify(commands)
    
    elif request.method == 'POST':
        data = request.json
        name = data.get('name')
        response = data.get('response')
        embed = data.get('embed', data.get('is_embed', False))
        
        if not name or not response:
            return jsonify({"error": "Missing name or response"}), 400
        
        user_id = int(session['user']['id'])
        db.add_custom_command(guild_id, name, response, embed, user_id)
        
        return jsonify({"success": True})
    
    elif request.method == 'DELETE':
        name = request.args.get('name') or (request.json.get('name') if request.is_json else None)
        if not name:
            return jsonify({"error": "Missing name"}), 400

        success = db.delete_custom_command(guild_id, name)
        return jsonify({"success": success})


@app.route('/api/guild/<int:guild_id>/commands/<string:name>', methods=['DELETE'])
@login_required
def api_delete_custom_command(guild_id, name):
    """Path-based delete endpoint to match frontend calls"""
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired. Ensure you're signed in and have Manage Server or Administrator permissions."}), 403
    success = db.delete_custom_command(guild_id, name)
    return jsonify({"success": success})


@app.route('/api/user/guilds')
@login_required
def api_user_guilds():
    """API endpoint to get user's guilds"""
    # Use refresh-capable wrapper
    guilds = get_user_guilds_with_refresh(session.get('session_id'))
    
    # Filter guilds where user has manage server permission
    admin_guilds = []
    for guild in guilds:
        permissions = int(guild.get('permissions', 0))
        if permissions & 0x20 or permissions & 0x8:
            admin_guilds.append(guild)
    
    return jsonify(admin_guilds)


@app.route('/api/guild/<int:guild_id>/send-embed', methods=['POST'])
@login_required
def api_send_embed(guild_id):
    """API endpoint to send embeds via bot"""
    # Validate user has access
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired. Ensure you're signed in and have Manage Server or Administrator permissions."}), 403
    
    data = request.json
    channel_id = data.get('channel_id')
    embed_data = data.get('embed')
    
    if not channel_id or not embed_data:
        return jsonify({"error": "Missing channel_id or embed"}), 400
    
    bot_token = get_bot_token()
    bot_guilds, reason = get_bot_guilds_with_reason(bot_token)
    if reason in ('missing-token', 'unauthorized-token'):
        return jsonify({"error": "Bot token not configured or invalid. Set DISCORD_BOT_TOKEN or DISCORD_TOKEN."}), 500
    if not bot_guilds or not any(int(g.get('id')) == guild_id for g in (bot_guilds or [])):
        return jsonify({"error": "Bot not present in this server. Invite the bot first."}), 400

    # Queue the embed for the bot to send
    try:
        payload = {"channel_id": int(channel_id), "embed": embed_data}
        cur = db.conn.cursor()
        cur.execute(
            """
            INSERT INTO pending_setup_requests (guild_id, setup_type, data, created_at)
            VALUES (?, 'send_embed', ?, datetime('now'))
            """,
            (guild_id, json.dumps(payload))
        )
        db.conn.commit()
        return jsonify({"success": True, "message": "Embed queued for delivery", "request_id": cur.lastrowid})
    except Exception as e:
        return jsonify({"error": f"Failed to queue embed: {e}"}), 500


@app.route('/api/guild/<int:guild_id>/announcement', methods=['POST'])
@login_required
def api_send_announcement(guild_id):
    """API endpoint to send announcements"""
    # Validate user has access
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired. Ensure you're signed in and have Manage Server or Administrator permissions."}), 403
    
    data = request.json
    channel_id = data.get('channel_id')
    content = data.get('content')
    announcement_type = data.get('type', 'normal')
    mention_everyone = data.get('mention_everyone', False)
    
    if not channel_id or not content:
        return jsonify({"error": "Missing channel_id or content"}), 400
    
    bot_token = get_bot_token()
    bot_guilds, reason = get_bot_guilds_with_reason(bot_token)
    if reason in ('missing-token', 'unauthorized-token'):
        return jsonify({"error": "Bot token not configured or invalid. Set DISCORD_BOT_TOKEN or DISCORD_TOKEN."}), 500
    if not bot_guilds or not any(int(g.get('id')) == guild_id for g in (bot_guilds or [])):
        return jsonify({"error": "Bot not present in this server. Invite the bot first."}), 400

    try:
        payload = {
            "channel_id": int(channel_id),
            "content": content,
            "type": announcement_type,
            "mention_everyone": bool(mention_everyone),
        }
        cur = db.conn.cursor()
        cur.execute(
            """
            INSERT INTO pending_setup_requests (guild_id, setup_type, data, created_at)
            VALUES (?, 'announcement', ?, datetime('now'))
            """,
            (guild_id, json.dumps(payload))
        )
        db.conn.commit()
        return jsonify({"success": True, "message": "Announcement queued for delivery", "request_id": cur.lastrowid})
    except Exception as e:
        return jsonify({"error": f"Failed to queue announcement: {e}"}), 500


@app.route('/api/guild/<int:guild_id>/roles', methods=['POST'])
@login_required
def api_create_role(guild_id):
    """API endpoint to create roles"""
    # Validate user has access
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired. Ensure you're signed in and have Manage Server or Administrator permissions."}), 403
    
    data = request.json
    role_name = data.get('name')
    
    if not role_name:
        return jsonify({"error": "Missing role name"}), 400
    
    # Store role creation request for bot to process
    return jsonify({"success": True, "message": "Role created successfully"})


@app.route('/api/guild/<int:guild_id>/roles/bulk', methods=['POST'])
@login_required
def api_create_bulk_roles(guild_id):
    """API endpoint to create multiple roles"""
    # Validate user has access
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired. Ensure you're signed in and have Manage Server or Administrator permissions."}), 403
    
    data = request.json
    role_names = data.get('role_names', [])
    
    if not role_names:
        return jsonify({"error": "No role names provided"}), 400
    
    # Store bulk role creation requests for bot to process
    try:
        cur = db.conn.cursor()
        request_ids = []
        for role_name in role_names:
            cur.execute(
                """
                INSERT INTO pending_setup_requests 
                (guild_id, setup_type, data, created_at)
                VALUES (?, 'create_role', ?, datetime('now'))
                """,
                (guild_id, f"{role_name}|{0x99AAB5}|False|True|")
            )
            request_ids.append(cur.lastrowid)
        db.conn.commit()
        return jsonify({"success": True, "created": len(role_names), "request_ids": request_ids})
    except Exception as e:
        return jsonify({"error": f"Failed to queue roles: {e}"}), 500


@app.route('/api/guild/<int:guild_id>/template', methods=['POST'])
@login_required
def api_apply_template(guild_id):
    """API endpoint to apply server templates"""
    # Validate user has access
    # Validate user has access
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired. Ensure you're signed in and have Manage Server or Administrator permissions."}), 403
    
    data = request.json
    template_name = data.get('template')
    
    if not template_name:
        return jsonify({"error": "Missing template name"}), 400
    
    # Valid templates
    valid_templates = ['gaming', 'community', 'support', 'creative']
    if template_name not in valid_templates:
        return jsonify({"error": "Invalid template"}), 400
    
    # Make sure bot is in this server and has required permissions
    bot_token = os.getenv('DISCORD_BOT_TOKEN')
    bot_token = get_bot_token()
    bot_guilds, reason = get_bot_guilds_with_reason(bot_token)
    if reason == 'missing-token':
        return jsonify({"error": "Server not configured: dashboard missing bot token. Set DISCORD_BOT_TOKEN or DISCORD_TOKEN on server."}), 500
    if reason == 'unauthorized-token':
        return jsonify({"error": "Bot token invalid. Verify DISCORD_BOT_TOKEN is a valid Bot token."}), 500
    if not bot_guilds or not any(int(g.get('id')) == guild_id for g in (bot_guilds or [])):
        return jsonify({"error": "Bot not present in this server. Invite the bot with necessary permissions first."}), 400

    # Store template application request for bot to process
    try:
        cur = db.conn.cursor()
        cur.execute(
            """
            INSERT INTO pending_setup_requests (guild_id, setup_type, data, created_at)
            VALUES (?, 'template', ?, datetime('now'))
            """,
            (guild_id, template_name)
        )
        db.conn.commit()
        request_id = cur.lastrowid
        return jsonify({"success": True, "message": f"Template '{template_name}' queued. The bot will build it shortly.", "request_id": request_id})
    except Exception as e:
        return jsonify({"error": f"Failed to queue template: {str(e)}"}), 500


@app.route('/api/guild/<int:guild_id>/template/preview', methods=['GET'])
@login_required
def api_template_preview(guild_id):
    """Return a template JSON for preview without queuing it (built-in templates)."""
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired."}), 403
    name = request.args.get('name')
    if not name:
        return jsonify({"error": "Missing template name"}), 400
    valid_templates = ['gaming', 'community', 'support', 'creative']
    if name not in valid_templates:
        return jsonify({"error": "Invalid template"}), 400
    # Build the template using the bot helper (if bot code available)
    try:
        # Build the template mapping locally (avoid importing src.bot)
        def _local_dashboard_template(name: str):
            staff_roles = [
                {"name": "👑 Admin", "color": 0xF04747, "permissions": 8, "hoist": True, "mentionable": False},
                {"name": "🛡️ Moderator", "color": 0x5865F2, "permissions": 0, "hoist": True, "mentionable": True},
                {"name": "✅ Verified", "color": 0x43B581, "permissions": 0, "hoist": False, "mentionable": True},
            ]
            templates = {
                "gaming": {
                    "roles": staff_roles + [{"name": "🎮 Gamer", "color": 0x00FF88, "permissions": 0}],
                    "categories": [
                        {"name": "📣 ANNOUNCEMENTS","channels":[{"name":"📢-news","type":"text","topic":"Server updates"},{"name":"🎉-events","type":"text","topic":"Giveaways and tournaments"}]},
                        {"name": "💬 LOBBY","channels":[{"name":"👋-welcome","type":"text","topic":"Introduce yourself"},{"name":"💭-chat","type":"text","topic":"General chat"},{"name":"🔊 Squad 1","type":"voice"}]},
                        {"name":"🎮 GAMES","channels":[{"name":"🥇-ranked","type":"text","topic":"Ranked coordination"},{"name":"🤝-lfg","type":"text","topic":"Find teammates"},{"name":"🎧 Game Chat","type":"voice"}]}
                    ]
                },
                "community": {
                    "roles": staff_roles + [{"name": "🎭 Member", "color": 0x99AAB5, "permissions": 0}],
                    "categories": [
                        {"name":"📣 INFO","channels":[{"name":"📢-announcements","type":"text"},{"name":"📜-rules","type":"text"}]},
                        {"name":"💬 COMMUNITY","channels":[{"name":"general","type":"text","topic":"Chat with everyone"},{"name":"media-share","type":"text","topic":"Images and clips"},{"name":"Lounge","type":"voice"}]},
                        {"name":"🎉 EVENTS","channels":[{"name":"giveaways","type":"text"},{"name":"polls","type":"text"}]}
                    ]
                },
                "support": {
                    "roles": staff_roles + [{"name": "🙋 Customer", "color": 0xFFB347, "permissions": 0}],
                    "categories": [
                        {"name":"ℹ️ START HERE","channels":[{"name":"welcome","type":"text"},{"name":"faq","type":"text","topic":"Common questions"}]},
                        {"name":"🎟️ SUPPORT","channels":[{"name":"create-ticket","type":"text","topic":"Open support tickets"},{"name":"transcripts","type":"text","topic":"Closed ticket logs"},{"name":"Support VC","type":"voice"}]},
                        {"name":"📚 KNOWLEDGE BASE","channels":[{"name":"guides","type":"text"},{"name":"updates","type":"text"}]}
                    ]
                },
                "creative": {
                    "roles": staff_roles + [{"name": "🎨 Creator", "color": 0xE67E22, "permissions": 0}],
                    "categories": [
                        {"name":"📣 NEWS","channels":[{"name":"announcements","type":"text"},{"name":"roadmap","type":"text"}]},
                        {"name":"🖼️ SHOWCASE","channels":[{"name":"art-drop","type":"text","topic":"Share art"},{"name":"critiques","type":"text","topic":"Get feedback"},{"name":"Studio","type":"voice"}]},
                        {"name":"💡 COLLAB","channels":[{"name":"ideas","type":"text"},{"name":"work-in-progress","type":"text"}]}
                    ]
                }
            }
            return templates.get(name) or templates["community"]
        template = _local_dashboard_template(name)
        return jsonify({"success": True, "template": template})
    except Exception as e:
        return jsonify({"error": f"Failed to generate preview: {e}"}), 500


@app.route('/api/guild/<int:guild_id>/apply-structure', methods=['POST'])
@login_required
def api_apply_structure(guild_id):
    """Parse a text structure into a template and queue it for the bot"""
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired."}), 403
    bot_token = get_bot_token()
    bot_guilds, reason = get_bot_guilds_with_reason(bot_token)
    if reason == 'missing-token':
        return jsonify({"error": "Server not configured: dashboard missing bot token. Set DISCORD_BOT_TOKEN or DISCORD_TOKEN on server."}), 500
    if reason == 'unauthorized-token':
        return jsonify({"error": "Bot token invalid. Verify DISCORD_BOT_TOKEN is a valid Bot token."}), 500
    if not bot_guilds or not any(int(g.get('id')) == guild_id for g in (bot_guilds or [])):
        return jsonify({"error": "Bot not present in this server."}), 400

    data = request.json or {}
    raw = data.get('structure', '').strip()
    if not raw:
        return jsonify({"error": "No structure provided"}), 400

    if not parse_text_structure:
        return jsonify({"error": "Server parse module not available"}), 500
    try:
        template = parse_text_structure(raw)
        cur = db.conn.cursor()
        cur.execute("INSERT INTO pending_setup_requests (guild_id, setup_type, data, created_at) VALUES (?, 'template', ?, datetime('now'))", (guild_id, json.dumps(template)))
        db.conn.commit()
        request_id = cur.lastrowid
        return jsonify({"success": True, "message": "Server structure queued for application", "request_id": request_id})
    except Exception as e:
        return jsonify({"error": f"Failed to parse or queue structure: {str(e)}"}), 500


@app.route('/api/guild/<int:guild_id>/structure/preview', methods=['POST'])
@login_required
def api_structure_preview(guild_id):
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired."}), 403
    data = request.json or {}
    raw = data.get('structure', '').strip()
    if not raw:
        return jsonify({"error": "No structure provided"}), 400
    if not parse_text_structure:
        return jsonify({"error": "Server parse module not available"}), 500
    try:
        template = parse_text_structure(raw)
        return jsonify({"success": True, "template": template})
    except Exception as e:
        return jsonify({"error": f"Failed to preview structure: {str(e)}"}), 500


@app.route('/api/guild/<int:guild_id>/bot-presence', methods=['GET'])
@login_required
def api_bot_presence(guild_id):
    """Return whether the dashboard can detect the bot in the guild and a reason if not."""
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired."}), 403

    bot_token = get_bot_token()
    # Allow optional cache bypass: /bot-presence?refresh=1
    if request.args.get('refresh'):
        _BOT_GUILD_CACHE.pop(bot_token or '', None)

    bot_guilds, reason = get_bot_guilds_with_reason(bot_token)
    present = any(int(g.get('id')) == guild_id for g in (bot_guilds or []))
    return jsonify({
        "present": present,
        "reason": reason,
        "guild_count": len(bot_guilds or []),
    })


@app.route('/api/guild/<int:guild_id>/leveling-setup', methods=['POST'])
@login_required
def api_leveling_setup(guild_id):
    """API endpoint to trigger automatic leveling setup"""
    # Validate user has access
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired. Ensure you're signed in and have Manage Server or Administrator permissions."}), 403
    
    data = request.json
    milestones = data.get('milestones', '5,10,20,30,50,80,100')
    create_info = data.get('create_info_channel', True)
    create_rules = data.get('create_rules_channel', False)
    
    # Store setup request in database for bot to process
    try:
        # Create a pending setup request that the bot will pick up
        db.conn.execute("""
            INSERT OR REPLACE INTO pending_setup_requests 
            (guild_id, setup_type, data, created_at)
            VALUES (?, 'leveling', ?, datetime('now'))
        """, (guild_id, f"{milestones}|{int(create_info)}|{int(create_rules)}"))
        db.conn.commit()
        
        return jsonify({
            "success": True, 
            "message": "Leveling setup request submitted! The bot will process it shortly."
        })
    except Exception as e:
        return jsonify({"error": f"Failed to create setup request: {str(e)}"}), 500


@app.route('/api/guild/<int:guild_id>/level-roles', methods=['POST'])
@login_required
def api_add_level_role(guild_id):
    """API endpoint to add level role rewards"""
    # Validate user has access
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired. Ensure you're signed in and have Manage Server or Administrator permissions."}), 403
    
    data = request.json
    level = data.get('level')
    role_id = data.get('role_id')
    
    if not level or not role_id:
        return jsonify({"error": "Missing level or role_id"}), 400
    
    try:
        db.set_level_role(guild_id, int(level), int(role_id))
        return jsonify({"success": True, "message": f"Level {level} role reward added"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/guild/<int:guild_id>/giveaway', methods=['POST'])
@login_required
def api_create_giveaway(guild_id):
    """API endpoint to create giveaways"""
    # Validate user has access
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired. Ensure you're signed in and have Manage Server or Administrator permissions."}), 403
    
    data = request.json
    channel_id = data.get('channel_id')
    prize = data.get('prize')
    duration = data.get('duration_minutes')
    winners = data.get('winner_count', 1)
    description = data.get('description', '')
    
    if not all([channel_id, prize, duration]):
        return jsonify({"error": "Missing required fields"}), 400

    bot_token = get_bot_token()
    bot_guilds, reason = get_bot_guilds_with_reason(bot_token)
    if reason in ('missing-token', 'unauthorized-token'):
        return jsonify({"error": "Bot token not configured or invalid. Set DISCORD_BOT_TOKEN or DISCORD_TOKEN."}), 500
    if not bot_guilds or not any(int(g.get('id')) == guild_id for g in (bot_guilds or [])):
        return jsonify({"error": "Bot not present in this server. Invite the bot first."}), 400

    try:
        payload = {
            "channel_id": int(channel_id),
            "prize": prize,
            "duration_minutes": int(duration),
            "winner_count": int(winners or 1),
            "description": description or ''
        }
        cur = db.conn.cursor()
        cur.execute(
            """
            INSERT INTO pending_setup_requests (guild_id, setup_type, data, created_at)
            VALUES (?, 'giveaway', ?, datetime('now'))
            """,
            (guild_id, json.dumps(payload))
        )
        db.conn.commit()
        return jsonify({"success": True, "message": "Giveaway queued for creation", "request_id": cur.lastrowid})
    except Exception as e:
        return jsonify({"error": f"Failed to queue giveaway: {e}"}), 500


@app.route('/api/guild/<int:guild_id>/roles', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_manage_roles(guild_id):
    """API endpoint to manage server roles"""
    # Validate user has access
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired. Ensure you're signed in and have Manage Server or Administrator permissions."}), 403
    
    if request.method == 'GET':
        # Fetch roles from Discord API
        bot_token = get_bot_token()
        if bot_token:
            try:
                headers = {"Authorization": f"Bot {bot_token}"}
                response = requests.get(
                    f"{DISCORD_API_BASE}/guilds/{guild_id}/roles",
                    headers=headers
                )
                if response.status_code == 200:
                    roles_data = response.json()
                    # Sort by position (highest first) and format
                    roles = sorted(roles_data, key=lambda r: r.get('position', 0), reverse=True)
                    formatted_roles = []
                    for role in roles:
                        if role['name'] != '@everyone':  # Skip @everyone
                            formatted_roles.append({
                                'id': role['id'],
                                'name': role['name'],
                                'color': f"#{role['color']:06x}" if role['color'] else '#99aab5',
                                'position': role['position'],
                                'member_count': 0  # Would need additional API call for accurate count
                            })
                    return jsonify({"roles": formatted_roles})
            except Exception as e:
                print(f"Error fetching roles: {e}")
        
        return jsonify({"roles": []})
    
    elif request.method == 'POST':
        # Create a new role
        data = request.json
        name = data.get('name')
        color = data.get('color', '#99AAB5')
        permissions = data.get('permissions', [])
        hoist = data.get('hoist', False)
        mentionable = data.get('mentionable', False)
        
        if not name:
            return jsonify({"error": "Role name is required"}), 400
        
        # Convert hex color to integer
        try:
            if color.startswith('#'):
                color_int = int(color[1:], 16)
            else:
                color_int = int(color, 16)
        except:
            color_int = 0x99AAB5
        
        # Store role creation request for bot to process
        try:
            cur = db.conn.cursor()
            cur.execute("""
                INSERT INTO pending_setup_requests 
                (guild_id, setup_type, data, created_at)
                VALUES (?, 'create_role', ?, datetime('now'))
            """, (guild_id, f"{name}|{color_int}|{hoist}|{mentionable}|{','.join(permissions)}"))
            db.conn.commit()
            
            return jsonify({
                "success": True, 
                "message": f"Role '{name}' creation queued",
                "request_id": cur.lastrowid
            })
        except Exception as e:
            return jsonify({"error": f"Failed to create role: {str(e)}"}), 500
    
    elif request.method == 'DELETE':
        # Delete a role
        data = request.json
        role_id = data.get('role_id')
        
        if not role_id:
            return jsonify({"error": "role_id is required"}), 400
        
        # Store role deletion request for bot to process
        try:
            db.conn.execute("""
                INSERT INTO pending_setup_requests 
                (guild_id, setup_type, data, created_at)
                VALUES (?, 'delete_role', ?, datetime('now'))
            """, (guild_id, str(role_id)))
            db.conn.commit()
            
            return jsonify({
                "success": True, 
                "message": "Role deletion queued"
            })
        except Exception as e:
            return jsonify({"error": f"Failed to delete role: {str(e)}"}), 500


@app.route('/api/guild/<int:guild_id>/pending', methods=['GET', 'DELETE'])
@login_required
def api_pending_requests(guild_id):
    """API endpoint to view or cancel pending setup requests for a guild"""
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired. Ensure you're signed in and have Manage Server or Administrator permissions."}), 403

    if request.method == 'GET':
        try:
            cursor = db.conn.cursor()
            cursor.execute("SELECT id, setup_type, data, created_at, processed FROM pending_setup_requests WHERE guild_id = ? ORDER BY created_at DESC", (guild_id,))
            rows = cursor.fetchall()
            results = [dict(row) for row in rows]
            return jsonify({"requests": results})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    elif request.method == 'DELETE':
        req_id = request.args.get('id')
        if not req_id:
            return jsonify({"error": "Missing id param"}), 400
        try:
            db.conn.execute("DELETE FROM pending_setup_requests WHERE id = ? AND guild_id = ?", (int(req_id), guild_id))
            db.conn.commit()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route('/api/guild/<int:guild_id>/pending/stream')
@login_required
def api_pending_stream(guild_id):
    """Server-Sent Events stream for pending requests for a guild"""
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired."}), 403

    def generate():
        last_payload = None
        while True:
            try:
                cursor = db.conn.cursor()
                cursor.execute("SELECT id, setup_type, data, created_at, processed FROM pending_setup_requests WHERE guild_id = ? ORDER BY created_at DESC", (guild_id,))
                rows = cursor.fetchall()
                results = [dict(row) for row in rows]
                payload = json.dumps(results, default=str)
                if payload != last_payload:
                    last_payload = payload
                    yield f"data: {payload}\n\n"
            except Exception:
                pass
            time.sleep(3)

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@app.route('/api/guild/<int:guild_id>/ticketing', methods=['POST'])
@login_required
def api_setup_ticketing(guild_id):
    """API endpoint to setup ticket system"""
    # Validate user has access
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired. Ensure you're signed in and have Manage Server or Administrator permissions."}), 403
    
    data = request.json
    channel_id = data.get('channel_id')
    category_id = data.get('category_id')
    save_transcripts = data.get('save_transcripts', False)
    transcript_channel = data.get('transcript_channel')
    
    # Store ticket setup request for bot to process
    try:
        db.conn.execute("""
            INSERT INTO pending_setup_requests 
            (guild_id, setup_type, data, created_at)
            VALUES (?, 'ticket_setup', ?, datetime('now'))
        """, (guild_id, f"{channel_id}|{category_id}|{save_transcripts}|{transcript_channel or ''}"))
        db.conn.commit()
        
        return jsonify({
            "success": True, 
            "message": "Ticket system setup queued"
        })
    except Exception as e:
        return jsonify({"error": f"Failed to setup tickets: {str(e)}"}), 500


@app.route('/api/guild/<int:guild_id>/verified-role', methods=['POST'])
@login_required
def api_create_verified_role(guild_id):
    """API endpoint to create auto-verified role"""
    # Validate user has access
    if not _has_guild_access(guild_id):
        return jsonify({"error": "Unauthorized or session expired. Ensure you're signed in and have Manage Server or Administrator permissions."}), 403
    
    # Store verified role creation request for bot to process
    try:
        db.conn.execute("""
            INSERT INTO pending_setup_requests 
            (guild_id, setup_type, data, created_at)
            VALUES (?, 'verified_role', ?, datetime('now'))
        """, (guild_id, "auto"))
        db.conn.commit()
        
        return jsonify({
            "success": True, 
            "message": "Verified role will be created automatically"
        })
    except Exception as e:
        return jsonify({"error": f"Failed to create verified role: {str(e)}"}), 500


def run_dashboard(host='0.0.0.0', port=5000):
    """Run the dashboard"""
    app.run(host=host, port=port, debug=True)


if __name__ == '__main__':
    import sys
    validate_oauth_env()
    port = int(os.getenv('DASHBOARD_PORT', '6767'))
    run_dashboard(port=port)
