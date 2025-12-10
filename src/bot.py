import asyncio
import os
from urllib.parse import urlparse, urlunparse
import sys
import sqlite3
import json
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from .modules.text_parser import parse_text_structure
from .modules.server_builder import build_server_from_template, create_roles, template_from_guild
from .modules.ticket_system import handle_ticket_select, send_ticket_panel_to_channel
from .modules.verify_system import (
    init_verify_state,
    handle_verify_button,
    post_verify_panel,
    update_verify_config,
    get_verify_config,
    build_verify_embed,
)
from .modules.giveaway import init_giveaway, handle_giveaway_button, start_giveaway, end_giveaway_command as end_gw_command
from .modules.change_logger import start_change_logger, stop_change_logger
from .modules.modmail import init_modmail, setup_modmail_commands
from .modules.reaction_roles import init_reaction_roles, setup_reaction_role_commands
from .modules.moderation import setup_moderation_commands
from .modules.custom_commands import init_custom_commands, setup_custom_command_commands
from .modules.economy import init_economy
from .modules.leveling import init_leveling
from .database import db

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
EMBED_COLOR = 0x22C55E
RULES_ACCENT_COLOR = 0x9C66FF  # Purple accent similar to screenshot
EMBED_THUMB = (
    "https://media.discordapp.net/attachments/1443222738750668952/1446618834638471259/Channel-manager.png"
)
MAX_CHANNELS = 500
MAX_ROLES = 200
STARTED_AT = discord.utils.utcnow()
RULES_DEFAULT = {
    "titleText": "Server Rules",
    "welcomeTitle": "Welcome!",
    "welcomeBody": (
        "Thanks for being here. These rules are the basics for keeping things safe, friendly, and fun for everyone."
    ),
    "descriptionText": (
        "If something isn’t covered below, staff may apply common-sense judgment to protect the community. "
        "Questions or concerns? Ask the team before it becomes an issue."
    ),
    "categories": [
        {
            "emoji": "\U0001F4D8",
            "color": "red",
            "title": "General Guidelines",
            "description": (
                "Be kind and on-topic. No spam/NSFW/hate speech. Follow staff direction and use the right channels."
            ),
        },
        {
            "emoji": "\U0001F7E9",
            "color": "green",
            "title": "Minor Offenses",
            "description": (
                "- Light spam or emoji flooding\n- Off-topic messages\n- Mild language/low-effort trolling\n"
                "Likely: warning or short mute."
            ),
        },
        {
            "emoji": "\U0001F7E7",
            "color": "orange",
            "title": "Moderate Offenses",
            "description": (
                "- Advertising without permission\n- Impersonation\n- Ignoring staff direction\n- Disturbing content\n"
                "Likely: timeout, mute, or kick."
            ),
        },
        {
            "emoji": "\U0001F7E5",
            "color": "red",
            "title": "Major Offenses",
            "description": (
                "- Hate/harassment/threats\n- Doxxing/personal info\n- Severe NSFW/illegal content\n- Raid/ban evasion\n"
                "Likely: ban and report to Discord."
            ),
        },
    ],
    "bannerUrl": None,
    "footerText": None,
}
RULES_STATE: dict[int, dict] = {}

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Attach the shared Database instance to the bot so modules may use bot.db
bot.db = db

async def _is_owner_or_admin(interaction: discord.Interaction) -> bool:
    """Return True if the invoking user is the guild owner, server administrator, or app owner/owner team member."""
    if not interaction.guild:
        return False
    owner_id = interaction.guild.owner_id
    if not owner_id:
        try:
            owner = await interaction.guild.fetch_owner()
            owner_id = owner.id
        except Exception:
            owner_id = None
    if owner_id == interaction.user.id:
        return True
    member = interaction.user if isinstance(interaction.user, discord.Member) else await interaction.guild.fetch_member(interaction.user.id)
    if member and member.guild_permissions.administrator:
        return True
    app_info = getattr(bot, '_app_info', None)
    if app_info and hasattr(app_info, 'owner'):
        if app_info.owner and app_info.owner.id == interaction.user.id:
            return True
        if hasattr(app_info, 'team') and app_info.team:
            return any(m.id == interaction.user.id for m in app_info.team.members)
    return False









async def process_pending_setups():
    """Background task to process pending setup requests from dashboard"""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            # Check for pending setup requests
            conn = sqlite3.connect(db.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, guild_id, setup_type, data 
                FROM pending_setup_requests 
                WHERE processed = 0
            """)
            
            requests = cursor.fetchall()
            
            for request_id, guild_id, setup_type, data in requests:
                guild = bot.get_guild(guild_id)
                if not guild:
                    # Mark as processed even if guild not found
                    cursor.execute("UPDATE pending_setup_requests SET processed = 1 WHERE id = ?", (request_id,))
                    conn.commit()
                    continue
                
                if setup_type == 'leveling':
                    try:
                        # Parse data: "5,10,20|1|0" -> milestones, create_info, create_rules
                        parts = data.split('|')
                        milestones_str = parts[0]
                        create_info = bool(int(parts[1])) if len(parts) > 1 else True
                        create_rules = bool(int(parts[2])) if len(parts) > 2 else False
                        
                        # Parse milestones
                        milestones = [int(m.strip()) for m in milestones_str.split(',')]
                        
                        # Import leveling module functions
                        from modules.leveling import create_leveling_roles, create_leveling_info_channel, create_rules_info_channel
                        
                        # Create roles
                        await create_leveling_roles(guild, milestones, bot.leveling, bot)
                        
                        # Create channels if requested
                        if create_info:
                            await create_leveling_info_channel(guild, bot)
                        if create_rules:
                            await create_rules_info_channel(guild)
                        
                        # Mark as processed
                        cursor.execute("UPDATE pending_setup_requests SET processed = 1 WHERE id = ?", (request_id,))
                        conn.commit()
                        
                        print(f"✅ Processed leveling setup for guild {guild_id}")
                    except Exception as e:
                        print(f"❌ Error processing leveling setup for guild {guild_id}: {e}")
                        # Mark as processed to avoid infinite retries
                        cursor.execute("UPDATE pending_setup_requests SET processed = 1 WHERE id = ?", (request_id,))
                        conn.commit()
                
                elif setup_type == 'create_role':
                    try:
                        # Parse data: "name|color_int|hoist|mentionable|permissions"
                        parts = data.split('|')
                        name = parts[0]
                        color_int = int(parts[1]) if len(parts) > 1 else 0x99AAB5
                        hoist = parts[2] == 'True' if len(parts) > 2 else False
                        mentionable = parts[3] == 'True' if len(parts) > 3 else False
                        
                        # Create role
                        role = await guild.create_role(
                            name=name,
                            color=discord.Color(color_int),
                            hoist=hoist,
                            mentionable=mentionable,
                            reason="Created via dashboard"
                        )
                        
                        cursor.execute("UPDATE pending_setup_requests SET processed = 1 WHERE id = ?", (request_id,))
                        conn.commit()
                        print(f"✅ Created role '{name}' for guild {guild_id}")
                    except Exception as e:
                        print(f"❌ Error creating role for guild {guild_id}: {e}")
                        cursor.execute("UPDATE pending_setup_requests SET processed = 1 WHERE id = ?", (request_id,))
                        conn.commit()
                
                elif setup_type == 'delete_role':
                    try:
                        role_id = int(data)
                        role = guild.get_role(role_id)
                        if role:
                            await role.delete(reason="Deleted via dashboard")
                            print(f"✅ Deleted role {role_id} from guild {guild_id}")
                        
                        cursor.execute("UPDATE pending_setup_requests SET processed = 1 WHERE id = ?", (request_id,))
                        conn.commit()
                    except Exception as e:
                        print(f"❌ Error deleting role for guild {guild_id}: {e}")
                        cursor.execute("UPDATE pending_setup_requests SET processed = 1 WHERE id = ?", (request_id,))
                        conn.commit()
                
                elif setup_type == 'verified_role':
                    try:
                        # Create a verified role with appropriate permissions
                        role = await guild.create_role(
                            name="✅ Verified",
                            color=discord.Color(0x43B581),  # Green
                            hoist=False,
                            mentionable=False,
                            reason="Auto-created verified role"
                        )
                        
                        # Store in config for verification system
                        config = db.get_guild_config(guild_id) or {}
                        config['verified_role_id'] = role.id
                        db.update_guild_config(guild_id, config)
                        
                        cursor.execute("UPDATE pending_setup_requests SET processed = 1 WHERE id = ?", (request_id,))
                        conn.commit()
                        print(f"✅ Created verified role for guild {guild_id}")
                    except Exception as e:
                        print(f"❌ Error creating verified role for guild {guild_id}: {e}")
                        cursor.execute("UPDATE pending_setup_requests SET processed = 1 WHERE id = ?", (request_id,))
                        conn.commit()
                
                elif setup_type == 'ticket_setup':
                    try:
                        # Parse data: "channel_id|category_id|save_transcripts|transcript_channel"
                        parts = data.split('|')
                        panel_channel_id = int(parts[0]) if parts[0] else None
                        category_id = int(parts[1]) if len(parts) > 1 and parts[1] else None
                        
                        if panel_channel_id:
                            from modules.ticket_system import send_ticket_panel_to_channel
                            channel = guild.get_channel(panel_channel_id)
                            if channel:
                                # Send ticket panel
                                await send_ticket_panel_to_channel(bot, channel)
                        
                        # Store config
                        if category_id:
                            config = db.get_guild_config(guild_id) or {}
                            config['ticket_category_id'] = category_id
                            db.update_guild_config(guild_id, config)
                        
                        cursor.execute("UPDATE pending_setup_requests SET processed = 1 WHERE id = ?", (request_id,))
                        conn.commit()
                        print(f"✅ Setup ticket system for guild {guild_id}")
                    except Exception as e:
                        print(f"❌ Error setting up tickets for guild {guild_id}: {e}")
                        cursor.execute("UPDATE pending_setup_requests SET processed = 1 WHERE id = ?", (request_id,))
                        conn.commit()

                elif setup_type == 'template':
                    try:
                        # data may be a built-in name or a JSON string representing the template
                        template = None
                        raw = data.strip() if data else ''
                        if raw.startswith('{') or raw.startswith('['):
                            template = json.loads(raw)
                        else:
                            template = _get_dashboard_template(raw)
                        _ensure_template_safe(template)
                        await build_server_from_template(guild, template)

                        cursor.execute("UPDATE pending_setup_requests SET processed = 1 WHERE id = ?", (request_id,))
                        conn.commit()
                        print(f"✅ Applied template (queued) for guild {guild_id}")
                    except Exception as e:
                        print(f"❌ Error applying template for guild {guild_id}: {e}")
                        cursor.execute("UPDATE pending_setup_requests SET processed = 1 WHERE id = ?", (request_id,))
                        conn.commit()
            
            conn.close()
        except Exception as e:
            print(f"Error in process_pending_setups: {e}")
        
        # Check every 10 seconds
        await asyncio.sleep(10)


@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
    except Exception:
        pass
    print(f"Bot logged in as {bot.user}")
    
    # Ensure DB is attached to bot for modules
    if not hasattr(bot, 'db') or getattr(bot, 'db', None) is None:
        bot.db = db

    # Store app info for owner checks
    bot._app_info = await bot.application_info()
    
    bot._change_observer = start_change_logger(bot)
    init_verify_state(bot)
    init_giveaway(bot)
    init_modmail(bot)
    init_reaction_roles(bot)
    init_custom_commands(bot)
    init_economy(bot)
    init_leveling(bot)
    setup_modmail_commands(bot)
    setup_reaction_role_commands(bot)
    setup_moderation_commands(bot)
    setup_custom_command_commands(bot)
    await send_ticket_panel_to_channel(bot)
    
    # Start background task for processing dashboard requests
    bot.loop.create_task(process_pending_setups())
    
    print("✅ All modules loaded successfully!")
    print(f"💰 Economy system enabled")
    print(f"📊 Leveling system enabled")
    print(f"🔄 Dashboard request processor started")
    print(f"🌐 Dashboard: Run the web dashboard separately with 'python -m src.web.dashboard'")


@bot.event
async def on_disconnect():
    observer = getattr(bot, "_change_observer", None)
    if observer:
        stop_change_logger(observer)


@bot.event
async def on_guild_join(guild: discord.Guild):
    try:
        owner = guild.owner or await guild.fetch_owner()
        bot_name = bot.user.name if bot.user else "Channel Manager"
        embed = discord.Embed(
            title=f"Thank you for adding {bot_name} ⚡ to {guild.name}!",
            description="Get ready to upgrade moderation, automation und dashboard workflows.",
            color=EMBED_COLOR,
        )
        embed.set_thumbnail(url=EMBED_THUMB)
        embed.add_field(
            name="🕹️ How to Interact",
            value=(
                f"• Mention me: @{bot_name}⚡ followed by your question.\n"
                "• Use the prefix `bb` plus your prompt (e.g., `bb hello`).\n"
                "• Reply to one of my answers so the conversation keeps context."
            ),
            inline=False,
        )
        embed.add_field(
            name="🛡️ Core Systems",
            value=(
                "• ĐY'ª Modmail: Private threads between users and staff with transcript history.\n"
                "• ĐYZđ Reaction Roles: Set auto-roles per emoji panel using `/reactionrole_*` commands.\n"
                "• ĐY\"ù Moderation: Kick, ban, timeout, warn, purge, slowmode + logging with `/modlog`.\n"
                "• ƒsT‹÷? Custom Commands: Build commands with `{user}`, `{server}`, `{channel}` variables."
            ),
            inline=False,
        )
        embed.add_field(
            name="⚙️ Automation & Growth",
            value=(
                "• ĐY'ø Economy: Custom currency, daily rewards, pay/transfer, leaderboard + admin tools.\n"
                "• ĐY\"S Leveling: XP per message, level role rewards, rank announcements and quick setup.\n"
                "• ĐYZ% Giveaways & Tickets: Timed giveaways, entries with ĐYZ%, plus ticket panels and transcripts."
            ),
            inline=False,
        )
        embed.add_field(
            name="🌐 Dashboard & Templates",
            value=(
                "• Secure Discord OAuth login with server-specific config.\n"
                "• Server templates (Gaming, Community, Support, Creative) plus Embed maker + Announcements.\n"
                "• Real-time moderation, welcome/leave messages, auto-roles und prefix settings."
            ),
            inline=False,
        )
        embed.set_footer(text="Channel Manager · CHECK `README.md` für Details + `FEATURES.md` für alle Systeme")
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Support Server",
                style=discord.ButtonStyle.link,
                url="https://discord.gg/zjr3Umcu",
            )
        )
        await owner.send(embed=embed, view=view)
    except Exception:
        return


@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        handled_ticket = await handle_ticket_select(interaction)
        if handled_ticket:
            return
        handled_verify = await handle_verify_button(interaction)
        if handled_verify:
            return
        handled_gw = await handle_giveaway_button(interaction)
        if handled_gw:
            return


@bot.event
async def on_message(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    config = get_verify_config(message.guild.id)
    verify_role_id = config.get("verifiedRole")
    unverified_role_id = config.get("unverifiedRole")
    if not verify_role_id or not unverified_role_id:
        return
    member = message.author if isinstance(message.author, discord.Member) else None
    if not member:
        return
    if any(str(r.id) == str(verify_role_id) for r in member.roles):
        return
    bot_member = message.guild.me
    if not bot_member:
        return
    perms = message.channel.permissions_for(bot_member)
    if perms.manage_messages:
        try:
            await message.delete()
        except Exception:
            pass
    try:
        notify = await message.channel.send(
            f"{message.author.mention}, please verify first using /verify to get access."
        )
        await asyncio.sleep(5)
        await notify.delete()
    except Exception:
        return


@bot.event
async def on_member_join(member: discord.Member):
    config = get_verify_config(member.guild.id)
    unverified_role_id = config.get("unverifiedRole")
    if unverified_role_id and str(unverified_role_id).isdigit():
        role = member.guild.get_role(int(unverified_role_id))
        if role:
            try:
                await member.add_roles(role, reason="Auto assign unverified role on join")
            except Exception:
                pass


class RulesView(discord.ui.View):
    def __init__(self, config: dict):
        super().__init__(timeout=None)
        self.add_item(RulesSelect(config))


class RulesSelect(discord.ui.Select):
    def __init__(self, config: dict):
        options = []
        for index, item in enumerate(config.get("categories", [])):
            emoji_val = _safe_emoji(item.get("emoji"))
            opt_kwargs = {
                "label": item.get("title", "Item"),
                "description": item.get("description", "")[:100],
                "value": str(index),
            }
            if emoji_val:
                opt_kwargs["emoji"] = emoji_val
            options.append(discord.SelectOption(**opt_kwargs))
        if not options:
            options.append(discord.SelectOption(label="No categories set", value="0"))
        super().__init__(placeholder="Make a selection", min_values=1, max_values=1, options=options, custom_id="rules-select")
        self.config = config

    async def callback(self, interaction: discord.Interaction):
        choice_index = int(self.values[0])
        detail_embed = _build_rules_detail(choice_index, self.config)
        await interaction.response.send_message(embed=detail_embed, ephemeral=True)


class RulesTextModal(discord.ui.Modal, title="Update Rules Texts"):
    def __init__(self, config: dict):
        super().__init__(timeout=None)
        self.title_input = discord.ui.TextInput(
            label="Title",
            custom_id="rules_title",
            default=config.get("titleText", "Server Rules"),
            max_length=100,
        )
        self.welcome_input = discord.ui.TextInput(
            label="Welcome line",
            custom_id="rules_welcome",
            default=config.get("welcomeTitle", "Welcome!"),
            max_length=100,
        )
        self.body_input = discord.ui.TextInput(
            label="Welcome body",
            custom_id="rules_body",
            style=discord.TextStyle.long,
            default=config.get("welcomeBody", "")[:400],
            max_length=400,
        )
        self.desc_input = discord.ui.TextInput(
            label="Notes paragraph",
            custom_id="rules_desc",
            style=discord.TextStyle.long,
            default=config.get("descriptionText", "")[:400],
            max_length=400,
        )
        self.add_item(self.title_input)
        self.add_item(self.welcome_input)
        self.add_item(self.body_input)
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        config = _get_rules_config(interaction.guild_id)
        config.update(
            {
                "titleText": str(self.title_input),
                "welcomeTitle": str(self.welcome_input),
                "welcomeBody": str(self.body_input),
                "descriptionText": str(self.desc_input),
            }
        )
        _set_rules_config(interaction.guild_id, config)
        await interaction.response.send_message("Rules texts updated.", ephemeral=True)


class RulesBulkModal(discord.ui.Modal, title="Update up to 5 rules"):
    def __init__(self):
        super().__init__(timeout=None)
        self.rule1 = discord.ui.TextInput(label="Rule 1 (Title | Description)", required=False, max_length=300)
        self.rule2 = discord.ui.TextInput(label="Rule 2 (Title | Description)", required=False, max_length=300)
        self.rule3 = discord.ui.TextInput(label="Rule 3 (Title | Description)", required=False, max_length=300)
        self.rule4 = discord.ui.TextInput(label="Rule 4 (Title | Description)", required=False, max_length=300)
        self.rule5 = discord.ui.TextInput(label="Rule 5 (Title | Description)", required=False, max_length=300)
        for item in (self.rule1, self.rule2, self.rule3, self.rule4, self.rule5):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        entries = [self.rule1, self.rule2, self.rule3, self.rule4, self.rule5]
        palette = ["\U0001F7E6", "\U0001F7E9", "\U0001F7E7", "\U0001F7E5", "\U0001F7EA"]
        categories = []
        for idx, entry in enumerate(entries):
            text = str(entry).strip()
            if not text:
                continue
            parts = text.split("|", 1)
            title = parts[0].strip()[:100] if parts else f"Rule {idx+1}"
            description = parts[1].strip()[:500] if len(parts) > 1 else "Details for this rule."
            categories.append(
                {
                    "emoji": palette[idx % len(palette)],
                    "color": "red",
                    "title": title or f"Rule {idx+1}",
                    "description": description,
                }
            )
        if not categories:
            await interaction.response.send_message("No rules provided.", ephemeral=True)
            return
        config = _get_rules_config(interaction.guild_id)
        config["categories"] = categories
        _set_rules_config(interaction.guild_id, config)
        await interaction.response.send_message(f"Updated {len(categories)} rules.", ephemeral=True)


@bot.tree.command(name="setup", description="Load a prebuilt server template (customize via dashboard).")
async def setup_command(interaction: discord.Interaction):
    if not await _is_owner_or_admin(interaction):
        await interaction.response.send_message("Only the server owner or admins can use this command.", ephemeral=True)
        return
    
    raw_dashboard_url = os.getenv("DASHBOARD_URL", "https://jthweb.yugp.me")
    # Normalize URL to remove explicit port if present so the dashboard button doesn't show :6767
    try:
        parsed = urlparse(raw_dashboard_url)
        if parsed.scheme and parsed.hostname:
            dashboard_url = urlunparse((parsed.scheme, parsed.hostname, parsed.path or "", parsed.params, parsed.query, parsed.fragment))
        else:
            dashboard_url = raw_dashboard_url
    except Exception:
        dashboard_url = raw_dashboard_url
    
    embed = discord.Embed(
        title="🚀 Server Setup",
        description=(
            "**Welcome to Channel Manager!**\n\n"
            "Setup your server with pre-built templates using our web dashboard.\n\n"
            "**Available Templates:**\n"
            "🎮 Gaming Server - Perfect for gaming communities\n"
            "💬 Community Server - Great for social servers\n"
            "🎫 Support Server - Ideal for customer support\n"
            "🎨 Creative Server - For artists and creators\n\n"
            "**Quick Start:**\n"
            "1. Click the button below to open the dashboard\n"
            "2. Login with your Discord account\n"
            "3. Select your server and choose a template\n"
            "4. Customize channels, roles, and settings\n\n"
            "**Features:**\n"
            "✨ Server templates\n"
            "📝 Custom commands\n"
            "🔨 Moderation tools\n"
            "📢 Announcements\n"
            "🎭 Role management\n"
            "📊 Embed maker\n"
        ),
        color=EMBED_COLOR,
    )
    embed.set_thumbnail(url=EMBED_THUMB)
    embed.set_footer(text="All bot customization happens via the web dashboard")
    
    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            label="🌐 Open Dashboard",
            style=discord.ButtonStyle.link,
            url=dashboard_url,
        )
    )
    view.add_item(
        discord.ui.Button(
            label="Support Server",
            style=discord.ButtonStyle.link,
            url="https://discord.gg/zjr3Umcu",
        )
    )
    
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name="sync", description="Sync slash commands (Admin+).")
@app_commands.checks.has_permissions(administrator=True)
async def sync_command(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        synced = await bot.tree.sync()
        await interaction.followup.send(f"✅ Synced {len(synced)} command(s) globally.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to sync: {e}", ephemeral=True)


@bot.tree.command(name="health", description="Show bot status.")
async def health_command(interaction: discord.Interaction):
    if not await _is_owner_or_admin(interaction):
        await _safe_send(interaction, content="Only the server owner or admins can use this command.", ephemeral=True)
        return

    status = getattr(bot, "status", discord.Status.online).name
    ping = max(0, round(bot.latency * 1000)) if hasattr(bot, "latency") else 0
    guild_count = len(bot.guilds)
    channel_count = sum(len(guild.channels) for guild in bot.guilds)
    uptime_seconds = int((discord.utils.utcnow() - STARTED_AT).total_seconds())
    uptime_parts = (
        f"{uptime_seconds // 86400}d "
        f"{(uptime_seconds % 86400) // 3600}h "
        f"{(uptime_seconds % 3600) // 60}m "
        f"{uptime_seconds % 60}s"
    )

    embed = discord.Embed(title="Channel Manager Health", color=EMBED_COLOR)
    embed.set_thumbnail(url=EMBED_THUMB)
    embed.add_field(name="Status", value=str(status), inline=True)
    embed.add_field(name="Ping", value=f"{ping} ms", inline=True)
    embed.add_field(name="Uptime", value=uptime_parts, inline=True)
    embed.add_field(name="Servers", value=str(guild_count), inline=True)
    embed.add_field(name="Channels (cached)", value=str(channel_count), inline=True)
    embed.add_field(name="Runtime", value=f"Python {sys.version.split()[0]} | discord.py {discord.__version__}", inline=False)
    embed.set_footer(text="Channel Manager - system health")
    embed.timestamp = discord.utils.utcnow()

    await _safe_send(interaction, embed=embed, ephemeral=True)


@bot.tree.command(name="help", description="Show a short help message.")
async def help_command(interaction: discord.Interaction):
    channel_example = (
        "INFORMATION (category)\n"
        "  #announcements\n"
        "  #bot-info\n\n"
        "SUPPORT (category)\n"
        "  #create-ticket\n"
        "  #help\n"
        "  #bug-report\n\n"
        "COMMUNITY (category)\n"
        "  #general\n"
        "  #showcase\n"
    )

    roles_block = (
        "STAFF & ADMIN (roles)\n"
        "  Owner | Color: #ff0000 | Permissions: [Administrator, Manage Server, Manage Roles]\n"
        "  Moderator | Color: #ff944d | Permissions: [Kick Members, Ban Members, Timeout Members, Manage Messages]"
    )

    embed = discord.Embed(title="Channel Builder Help", color=EMBED_COLOR)
    embed.set_thumbnail(url=EMBED_THUMB)
    embed.description = "\n".join(
        [
            "1) Run /setup and pick what you need.",
            "2) For text import, paste something like this:",
            "```",
            channel_example,
            "```",
            "3) Roles import example:",
            "```",
            roles_block,
            "```",
            "Notes:",
            "- Bot must be in the source server to clone.",
            "- Max around 500 channels per server.",
            "- Bot needs Manage Channels and Manage Roles permissions.",
            "",
            "Rules module:",
            "- /rules to show the rules panel",
            "- /rules_setup (owner) to configure texts, rules, and banner via buttons",
            "",
            "Verify module:",
            "- /verify to show the verify panel (uses per-server config)",
            "- /verify_setup (owner) to set unverified/verified roles, banner, footer",
            "",
            "Giveaway module:",
            "- /giveaway_start (owner) to start a giveaway (prize/duration/description)",
            "- /giveaway_end (owner) to end and get transcript",
        ]
    )
    embed.set_footer(text="Channel Manager - simple help")
    await _safe_send(interaction, embed=embed, ephemeral=True)


@bot.tree.command(name="rules", description="Show server rules with a selector.")
async def rules_command(interaction: discord.Interaction):
    if not interaction.guild:
        await _safe_send(interaction, content="Use this in a server.", ephemeral=True)
        return
    config = _get_rules_config(interaction.guild_id)
    rules_embed = _build_rules_embed(config)
    view = RulesView(config)
    await _safe_send(interaction, embed=rules_embed, view=view, ephemeral=False)

    if interaction.guild and interaction.user.id == interaction.guild.owner_id:
        owner_embed = discord.Embed(
            title="Rules panel posted",
            description=(
                "Only you see this note.\n"
                "- Embed + dropdown show rules; clicks give details (ephemeral) so the channel stays clean.\n"
                "- Use /rules_setup to manage texts, rules, and banner (owner only).\n"
                "- Planned dashboard will mirror these fields. Only this server sees its own banner/config."
            ),
            color=EMBED_COLOR,
        )
        owner_embed.set_footer(text="Owner note - Channel Manager")
        await interaction.followup.send(embed=owner_embed, ephemeral=True)


class RulesBannerModal(discord.ui.Modal, title="Set Rules Banner URL"):
    def __init__(self):
        super().__init__(timeout=None)
        self.url_input = discord.ui.TextInput(label="Banner image URL (leave empty to remove)", required=False)
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        config = _get_rules_config(interaction.guild_id)
        url = str(self.url_input).strip()
        config["bannerUrl"] = url if url else None
        _set_rules_config(interaction.guild_id, config)
        msg = "Banner updated." if url else "Banner removed."
        await interaction.response.send_message(msg, ephemeral=True)


class RulesFooterModal(discord.ui.Modal, title="Set Rules Footer"):
    def __init__(self):
        super().__init__(timeout=None)
        self.footer_input = discord.ui.TextInput(
            label="Footer text (optional)",
            required=False,
            max_length=120,
            placeholder="e.g. Be respectful to everyone."
        )
        self.add_item(self.footer_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        config = _get_rules_config(interaction.guild_id)
        footer_val = str(self.footer_input).strip()
        config["footerText"] = footer_val if footer_val else None
        _set_rules_config(interaction.guild_id, config)
        msg = "Footer updated." if footer_val else "Footer cleared."
        await interaction.response.send_message(msg, ephemeral=True)


class VerifySetupModal(discord.ui.Modal, title="Verify Setup"):
    def __init__(self):
        super().__init__(timeout=None)
        self.unverified = discord.ui.TextInput(label="Unverified role ID (optional)", required=False, max_length=20)
        self.verified = discord.ui.TextInput(label="Verified role ID (required)", required=True, max_length=20)
        self.title_input = discord.ui.TextInput(label="Title", required=False, max_length=100, default="Verify to access")
        self.desc_input = discord.ui.TextInput(label="Description", required=False, style=discord.TextStyle.long, default="Click verify to unlock access.")
        self.banner_input = discord.ui.TextInput(label="Banner URL (optional)", required=False)
        self.footer_input = discord.ui.TextInput(label="Footer (optional)", required=False, max_length=120)
        for item in (self.unverified, self.verified, self.title_input, self.desc_input, self.banner_input, self.footer_input):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        config = get_verify_config(interaction.guild_id)
        config.update(
            {
                "unverifiedRole": str(self.unverified).strip() or None,
                "verifiedRole": str(self.verified).strip() or None,
                "title": str(self.title_input).strip() or "Verify to access",
                "description": str(self.desc_input).strip() or "Click verify to unlock access.",
                "bannerUrl": str(self.banner_input).strip() or None,
                "footerText": str(self.footer_input).strip() or None,
            }
        )
        update_verify_config(interaction.guild_id, config)
        preview = build_verify_embed(config)
        await interaction.response.send_message("Verify settings saved. Preview below.", embed=preview, ephemeral=True)


class RulesSetupView(discord.ui.View):
    def __init__(self, config: dict):
        super().__init__(timeout=300)
        self.config = config
        self.add_item(RulesSetupTextButton())
        self.add_item(RulesSetupBulkButton())
        self.add_item(RulesSetupBannerButton())
        self.add_item(RulesSetupClearBannerButton())
        self.add_item(RulesSetupFooterButton())


class RulesSetupTextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Edit Texts")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not await _is_owner_or_admin(interaction):
            await interaction.response.send_message("Only the server owner can edit rules.", ephemeral=True)
            return
        modal = RulesTextModal(_get_rules_config(interaction.guild_id))
        await interaction.response.send_modal(modal)


class RulesSetupBulkButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="Bulk Rules")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not await _is_owner_or_admin(interaction):
            await interaction.response.send_message("Only the server owner can edit rules.", ephemeral=True)
            return
        await interaction.response.send_modal(RulesBulkModal())


class RulesSetupBannerButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Set Banner")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not await _is_owner_or_admin(interaction):
            await interaction.response.send_message("Only the server owner can edit rules.", ephemeral=True)
            return
        await interaction.response.send_modal(RulesBannerModal())


class RulesSetupClearBannerButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.danger, label="Clear Banner")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not await _is_owner_or_admin(interaction):
            await interaction.response.send_message("Only the server owner can edit rules.", ephemeral=True)
            return
        config = _get_rules_config(interaction.guild_id)
        config["bannerUrl"] = None
        _set_rules_config(interaction.guild_id, config)
        await interaction.response.send_message("Banner removed.", ephemeral=True)


class RulesSetupFooterButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="Set Footer")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not await _is_owner_or_admin(interaction):
            await interaction.response.send_message("Only the server owner can edit rules.", ephemeral=True)
            return
        await interaction.response.send_modal(RulesFooterModal())


@bot.tree.command(name="rules_setup", description="Admin+: configure rules (texts, categories, banner) in one place.")
@app_commands.check(_is_owner_or_admin)
async def rules_setup_command(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return
    await _ensure_defer(interaction, ephemeral=True)
    config = _get_rules_config(interaction.guild_id)
    cats = config.get("categories", [])
    summary = "\n".join([f"{idx+1}) {c.get('title','')}" for idx, c in enumerate(cats)]) or "No categories set yet."
    banner = config.get("bannerUrl") or "None"
    embed = discord.Embed(
        title="Rules Setup",
        description=(
            "Manage all rules settings here. Buttons below let you edit texts, bulk rules, and banner.\n"
            f"Current banner: {banner}"
        ),
        color=EMBED_COLOR,
    )
    embed.add_field(name="Rules overview", value=summary, inline=False)
    embed.set_footer(text="Owner only - changes apply to this server only")
    await interaction.followup.send(embed=embed, view=RulesSetupView(config), ephemeral=True)


@rules_setup_command.error
async def rules_setup_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await _safe_send(interaction, content="Only the server owner can use /rules_setup inside a server.", ephemeral=True)


@bot.tree.command(name="verify", description="Show the verify panel.")
async def verify_command(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return
    config = get_verify_config(interaction.guild_id)
    embed = build_verify_embed(config)
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(custom_id="verify-accept", style=discord.ButtonStyle.success, label="Verify"))
    await _safe_send(interaction, embed=embed, view=view, ephemeral=False)


@bot.tree.command(name="verify_setup", description="Owner: configure verify roles/banner/footer.")
@app_commands.check(_is_owner_or_admin)
async def verify_setup_command(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return
    await interaction.response.send_modal(VerifySetupModal())


@verify_setup_command.error
async def verify_setup_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await _safe_send(interaction, content="Only the server owner can use /verify_setup inside a server.", ephemeral=True)


@bot.tree.command(name="giveaway_start", description="Admin+: start a giveaway.")
@app_commands.check(_is_owner_or_admin)
async def giveaway_start_command(
    interaction: discord.Interaction,
    prize: str,
    duration_minutes: app_commands.Range[int, 1, 10080],
    description: str | None = None,
):
    if not interaction.guild:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return
    await _ensure_defer(interaction, ephemeral=True)
    msg_id = await start_giveaway(interaction.channel, interaction.guild.id, prize, duration_minutes, description)
    await interaction.followup.send(f"Giveaway started (message ID: {msg_id}).", ephemeral=True)


@giveaway_start_command.error
async def giveaway_start_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await _safe_send(interaction, content="Only the server owner can start a giveaway.", ephemeral=True)


@bot.tree.command(name="giveaway_end", description="Admin+: end a giveaway and get transcript.")
@app_commands.check(_is_owner_or_admin)
@app_commands.describe(message_id="Message ID of the giveaway (leave empty for latest)")
async def giveaway_end_command(interaction: discord.Interaction, message_id: int | None = None):
    await _ensure_defer(interaction, ephemeral=True)
    await end_gw_command(interaction, message_id)


@giveaway_end_command.error
async def giveaway_end_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await _safe_send(interaction, content="Only the server owner can end a giveaway.", ephemeral=True)
@bot.tree.command(name="delete_channel", description="Delete all channels and categories in this server.")
async def delete_channels_command(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("Please run this inside a server.", ephemeral=True)
        return
    if not await _is_owner_or_admin(interaction):
        await interaction.response.send_message("Only the server owner or admins can use this command.", ephemeral=True)
        return

    await interaction.response.send_message("Deleting all channels and categories...", ephemeral=True)
    bot_member = interaction.guild.me
    if not bot_member:
        await interaction.followup.send("Bot member not found in guild.", ephemeral=True)
        return
    channels = await interaction.guild.fetch_channels()
    delete_tasks = []
    for ch in channels:
        if getattr(ch, "permissions_for", None) and ch.permissions_for(bot_member).manage_channels:
            delete_tasks.append(ch.delete(reason="Requested by /delete_channel"))
    await asyncio.gather(*delete_tasks, return_exceptions=True)
    await interaction.followup.send(f"Delete finished. Channels/categories removed: {len(delete_tasks)}.", ephemeral=True)


@bot.tree.command(name="delete_roles", description="Delete all deletable roles (except @everyone/managed/above bot).")
async def delete_roles_command(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("Please run this inside a server.", ephemeral=True)
        return
    if not await _is_owner_or_admin(interaction):
        await interaction.response.send_message("Only the server owner or admins can use this command.", ephemeral=True)
        return

    await interaction.response.send_message("Deleting roles (skipping @everyone, managed, and above my role)...", ephemeral=True)
    me = interaction.guild.me or await interaction.guild.fetch_member(bot.user.id)
    my_top_pos = me.top_role.position if me else 0

    roles = await interaction.guild.fetch_roles()
    delete_tasks = []
    for role in roles:
        if role.id == interaction.guild.default_role.id:
            continue
        if role.managed:
            continue
        if role.position >= my_top_pos:
            continue
        delete_tasks.append(role.delete(reason="Requested by /delete_roles"))
    await asyncio.gather(*delete_tasks, return_exceptions=True)
    await interaction.followup.send(f"Delete finished. Roles removed: {len(delete_tasks)}.", ephemeral=True)


def _ensure_template_safe(template: Any) -> None:
    if not template or not isinstance(template, dict) or not isinstance(template.get("categories"), list):
        raise ValueError("Template is not valid.")
    channel_count = sum(len(cat.get("channels", [])) for cat in template.get("categories", []))
    role_count = len(template.get("roles", [])) if isinstance(template.get("roles"), list) else 0
    if channel_count > MAX_CHANNELS:
        raise ValueError(f"Too many channels ({channel_count}). Discord limit is around 500.")
    if role_count > MAX_ROLES:
        raise ValueError(f"Too many roles ({role_count}).")


def _get_dashboard_template(name: str) -> dict:
    name = (name or "").lower()
    staff_roles = [
        {"name": "👑 Admin", "color": 0xF04747, "permissions": 8, "hoist": True, "mentionable": False},
        {"name": "🛡️ Moderator", "color": 0x5865F2, "permissions": 0, "hoist": True, "mentionable": True},
        {"name": "✅ Verified", "color": 0x43B581, "permissions": 0, "hoist": False, "mentionable": True},
    ]
    templates = {
        "gaming": {
            "roles": staff_roles + [{"name": "🎮 Gamer", "color": 0x00FF88, "permissions": 0}],
            "categories": [
                {
                    "name": "📣 ANNOUNCEMENTS",
                    "channels": [
                        {"name": "📢-news", "type": "text", "topic": "Server updates"},
                        {"name": "🎉-events", "type": "text", "topic": "Giveaways and tournaments"},
                    ],
                },
                {
                    "name": "💬 LOBBY",
                    "channels": [
                        {"name": "👋-welcome", "type": "text", "topic": "Introduce yourself"},
                        {"name": "💭-chat", "type": "text", "topic": "General chat"},
                        {"name": "🔊 Squad 1", "type": "voice"},
                    ],
                },
                {
                    "name": "🎮 GAMES",
                    "channels": [
                        {"name": "🥇-ranked", "type": "text", "topic": "Ranked coordination"},
                        {"name": "🤝-lfg", "type": "text", "topic": "Find teammates"},
                        {"name": "🎧 Game Chat", "type": "voice"},
                    ],
                },
            ],
        },
        "community": {
            "roles": staff_roles + [{"name": "🎭 Member", "color": 0x99AAB5, "permissions": 0}],
            "categories": [
                {
                    "name": "📣 INFO",
                    "channels": [
                        {"name": "📢-announcements", "type": "text"},
                        {"name": "📜-rules", "type": "text"},
                    ],
                },
                {
                    "name": "💬 COMMUNITY",
                    "channels": [
                        {"name": "general", "type": "text", "topic": "Chat with everyone"},
                        {"name": "media-share", "type": "text", "topic": "Images and clips"},
                        {"name": "Lounge", "type": "voice"},
                    ],
                },
                {
                    "name": "🎉 EVENTS",
                    "channels": [
                        {"name": "giveaways", "type": "text"},
                        {"name": "polls", "type": "text"},
                    ],
                },
            ],
        },
        "support": {
            "roles": staff_roles + [{"name": "🙋 Customer", "color": 0xFFB347, "permissions": 0}],
            "categories": [
                {
                    "name": "ℹ️ START HERE",
                    "channels": [
                        {"name": "welcome", "type": "text"},
                        {"name": "faq", "type": "text", "topic": "Common questions"},
                    ],
                },
                {
                    "name": "🎟️ SUPPORT",
                    "channels": [
                        {"name": "create-ticket", "type": "text", "topic": "Open support tickets"},
                        {"name": "transcripts", "type": "text", "topic": "Closed ticket logs"},
                        {"name": "Support VC", "type": "voice"},
                    ],
                },
                {
                    "name": "📚 KNOWLEDGE BASE",
                    "channels": [
                        {"name": "guides", "type": "text"},
                        {"name": "updates", "type": "text"},
                    ],
                },
            ],
        },
        "creative": {
            "roles": staff_roles + [{"name": "🎨 Creator", "color": 0xE67E22, "permissions": 0}],
            "categories": [
                {
                    "name": "📣 NEWS",
                    "channels": [
                        {"name": "announcements", "type": "text"},
                        {"name": "roadmap", "type": "text"},
                    ],
                },
                {
                    "name": "🖼️ SHOWCASE",
                    "channels": [
                        {"name": "art-drop", "type": "text", "topic": "Share art"},
                        {"name": "critiques", "type": "text", "topic": "Get feedback"},
                        {"name": "Studio", "type": "voice"},
                    ],
                },
                {
                    "name": "💡 COLLAB",
                    "channels": [
                        {"name": "ideas", "type": "text"},
                        {"name": "work-in-progress", "type": "text"},
                    ],
                },
            ],
        },
    }
    return templates.get(name) or templates["community"]


 


def _build_rules_embed(config: dict) -> discord.Embed:
    embed = discord.Embed(
        title=config.get("titleText", "Server Rules"),
        color=RULES_ACCENT_COLOR,
    )
    welcome = config.get("welcomeTitle", "Welcome to the server!")
    body = config.get("welcomeBody", "")
    desc = config.get("descriptionText", "")
    embed.description = f"**{welcome}**\n\n{body}\n\n{desc}".strip()
    banner_url = config.get("bannerUrl")
    if banner_url and _valid_banner(banner_url):
        embed.set_image(url=str(banner_url))
    footer = config.get("footerText")
    if footer:
        embed.set_footer(text=str(footer)[:120])
    return embed


def _build_rules_detail(choice_index: int, config: dict) -> discord.Embed:
    categories = config.get("categories", [])
    if choice_index < 0 or choice_index >= len(categories):
        return discord.Embed(title="Rules", description="No details available.", color=EMBED_COLOR)
    item = categories[choice_index]
    embed = discord.Embed(color=RULES_ACCENT_COLOR)
    embed.title = item.get("title", "Details")
    embed.description = item.get("description", "")
    footer = config.get("footerText") or "Questions? Ask staff for clarification."
    embed.set_footer(text=str(footer)[:120])
    return embed


def _get_rules_config(guild_id: int | None) -> dict:
    base = RULES_STATE.get(guild_id) if guild_id and guild_id in RULES_STATE else None
    if not base:
        return _sanitize_rules_config({**RULES_DEFAULT})
    merged = _sanitize_rules_config({**RULES_DEFAULT, **base})
    return merged


def _set_rules_config(guild_id: int | None, config: dict) -> None:
    if guild_id is None:
        return
    RULES_STATE[guild_id] = _sanitize_rules_config({**config})


async def _ensure_defer(interaction: discord.Interaction, ephemeral: bool = False) -> None:
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral)
    except Exception:
        return


async def _safe_send(interaction: discord.Interaction, **kwargs) -> None:
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(**kwargs)
        else:
            await interaction.followup.send(**kwargs)
    except Exception:
        return


def _safe_emoji(value: Any):
    if not value:
        return None
    try:
        return discord.PartialEmoji.from_str(str(value))
    except Exception:
        return None


def _sanitize_rules_config(config: dict) -> dict:
    categories = []
    for item in config.get("categories", []):
        emoji_val = _safe_emoji(item.get("emoji"))
        categories.append(
            {
                "emoji": emoji_val,
                "color": item.get("color", "red"),
                "title": str(item.get("title", "Item"))[:100],
                "description": str(item.get("description", ""))[:500],
            }
        )
    config["categories"] = categories
    banner = config.get("bannerUrl")
    config["bannerUrl"] = banner if banner and _valid_banner(str(banner)) else None
    footer = config.get("footerText")
    if footer:
        config["footerText"] = str(footer)[:120]
    else:
        config["footerText"] = None
    return config


def _is_image_link(url: str) -> bool:
    if not url:
        return False
    lowered = url.lower()
    if lowered.startswith("data:image/") and "base64," in lowered:
        return True
    if not lowered.startswith(("http://", "https://")):
        return False
    trimmed = lowered.split("?", 1)[0]
    return trimmed.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))


def _valid_banner(url: str) -> bool:
    if not url:
        return False
    if len(url) > 2048:
        return False
    return _is_image_link(url)


if not TOKEN:
    print("Please set DISCORD_TOKEN inside .env")
    sys.exit(1)

bot.run(TOKEN)












