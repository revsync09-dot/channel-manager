// Enhanced Dashboard JavaScript

// Section switching
function switchSection(sectionName) {
    // Update sidebar active state
    document.querySelectorAll('.sidebar-item').forEach(item => {
        item.classList.remove('active');
        if (item.dataset.section === sectionName) {
            item.classList.add('active');
        }
    });
    
    // Update section visibility
    document.querySelectorAll('.dashboard-section').forEach(section => {
        section.classList.remove('active');
        section.classList.add('hidden');
    });
    const target = document.getElementById(`${sectionName}-section`);
    if (target) {
        target.classList.remove('hidden');
        target.classList.add('active');
    }
}

// Add event listeners to sidebar items
document.querySelectorAll('.sidebar-item').forEach(item => {
    item.addEventListener('click', () => {
        switchSection(item.dataset.section);
    });
});

// Custom Commands
document.getElementById('create-command-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const name = document.getElementById('cmd-name').value;
    const response = document.getElementById('cmd-response').value;
    const isEmbed = document.getElementById('cmd-embed').checked;
    
    try {
        const res = await fetch(`/api/guild/${guildId}/commands`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, response, is_embed: isEmbed })
        });
        
        if (res.ok) {
            showNotification('Command created successfully!', 'success');
            location.reload();
        } else {
            const error = await res.json();
            showNotification(error.error || 'Failed to create command', 'error');
        }
    } catch (error) {
        showNotification('Failed to create command', 'error');
    }
});

async function deleteCommand(name) {
    if (!confirm(`Delete command "${name}"?`)) return;
    
    try {
        const res = await fetch(`/api/guild/${guildId}/commands/${name}`, {
            method: 'DELETE'
        });
        
        if (res.ok) {
            showNotification('Command deleted successfully!', 'success');
            location.reload();
        } else {
            showNotification('Failed to delete command', 'error');
        }
    } catch (error) {
        showNotification('Failed to delete command', 'error');
    }
}

// Embed Maker
function updateEmbedPreview() {
    const title = document.getElementById('embed-title')?.value || '';
    const description = document.getElementById('embed-description')?.value || '';
    const color = document.getElementById('embed-color')?.value || '#5865F2';
    const timestamp = document.getElementById('embed-timestamp')?.checked || false;
    const authorName = document.getElementById('embed-author-name')?.value || '';
    const authorIcon = document.getElementById('embed-author-icon')?.value || '';
    const thumbnail = document.getElementById('embed-thumbnail')?.value || '';
    const image = document.getElementById('embed-image')?.value || '';
    const footer = document.getElementById('embed-footer')?.value || '';
    const footerIcon = document.getElementById('embed-footer-icon')?.value || '';
    
    const preview = document.getElementById('embed-preview');
    if (!preview) return;
    
    let html = '<div class="discord-embed" style="border-left-color: ' + color + ';">';
    html += '<div class="embed-content">';
    
    // Author
    if (authorName) {
        html += '<div class="embed-author">';
        if (authorIcon) {
            html += `<img src="${authorIcon}" class="embed-author-icon" onerror="this.style.display='none'">`;
        }
        html += `<span class="embed-author-name">${escapeHtml(authorName)}</span>`;
        html += '</div>';
    }
    
    // Title
    if (title) {
        html += `<div class="embed-title">${escapeHtml(title)}</div>`;
    }
    
    // Description
    if (description) {
        html += `<div class="embed-description">${escapeHtml(description)}</div>`;
    }
    
    // Image
    if (image) {
        html += `<img src="${image}" class="embed-image" onerror="this.style.display='none'">`;
    }
    
    // Footer
    if (footer || timestamp) {
        html += '<div class="embed-footer">';
        if (footerIcon) {
            html += `<img src="${footerIcon}" class="embed-footer-icon" onerror="this.style.display='none'">`;
        }
        if (footer) {
            html += `<span>${escapeHtml(footer)}</span>`;
        }
        if (timestamp) {
            const now = new Date().toLocaleString();
            html += footer ? ` • ${now}` : now;
        }
        html += '</div>';
    }
    
    html += '</div>';
    
    // Thumbnail
    if (thumbnail) {
        html += `<img src="${thumbnail}" class="embed-thumbnail" onerror="this.style.display='none'">`;
    }
    
    html += '</div>';
    
    preview.querySelector('.embed-message').innerHTML = html;
}

async function sendEmbed() {
    const channelId = document.getElementById('embed-channel').value;
    if (!channelId) {
        showNotification('Please enter a channel ID', 'error');
        return;
    }
    
    const embedData = {
        title: document.getElementById('embed-title').value,
        description: document.getElementById('embed-description').value,
        color: parseInt(document.getElementById('embed-color').value.replace('#', ''), 16),
        timestamp: document.getElementById('embed-timestamp').checked,
        author: {
            name: document.getElementById('embed-author-name').value,
            icon_url: document.getElementById('embed-author-icon').value
        },
        thumbnail: { url: document.getElementById('embed-thumbnail').value },
        image: { url: document.getElementById('embed-image').value },
        footer: {
            text: document.getElementById('embed-footer').value,
            icon_url: document.getElementById('embed-footer-icon').value
        }
    };
    
    try {
        const res = await fetch(`/api/guild/${guildId}/send-embed`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel_id: channelId, embed: embedData })
        });
        
        if (res.ok) {
            showNotification('Embed sent successfully!', 'success');
        } else {
            const error = await res.json();
            showNotification(error.error || 'Failed to send embed', 'error');
        }
    } catch (error) {
        showNotification('Failed to send embed', 'error');
    }
}

function exportEmbedJSON() {
    const embedData = {
        title: document.getElementById('embed-title').value,
        description: document.getElementById('embed-description').value,
        color: parseInt(document.getElementById('embed-color').value.replace('#', ''), 16),
        timestamp: document.getElementById('embed-timestamp').checked ? new Date().toISOString() : null,
        author: {
            name: document.getElementById('embed-author-name').value,
            icon_url: document.getElementById('embed-author-icon').value
        },
        thumbnail: { url: document.getElementById('embed-thumbnail').value },
        image: { url: document.getElementById('embed-image').value },
        footer: {
            text: document.getElementById('embed-footer').value,
            icon_url: document.getElementById('embed-footer-icon').value
        }
    };
    
    const json = JSON.stringify(embedData, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'embed.json';
    a.click();
    URL.revokeObjectURL(url);
}

// Announcements
document.getElementById('announcement-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const channelId = document.getElementById('announcement-channel').value;
    const type = document.getElementById('announcement-type').value;
    const content = document.getElementById('announcement-content').value;
    const mentionEveryone = document.getElementById('announcement-mention-everyone').checked;
    
    try {
        const res = await fetch(`/api/guild/${guildId}/announcement`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                channel_id: channelId,
                type,
                content,
                mention_everyone: mentionEveryone
            })
        });
        
        if (res.ok) {
            showNotification('Announcement sent successfully!', 'success');
            document.getElementById('announcement-form').reset();
        } else {
            const error = await res.json();
            showNotification(error.error || 'Failed to send announcement', 'error');
        }
    } catch (error) {
        showNotification('Failed to send announcement', 'error');
    }
});

// Role Manager
document.getElementById('create-role-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const name = document.getElementById('role-name').value;
    const color = document.getElementById('role-color').value;
    const hoist = document.getElementById('role-hoist').checked;
    const mentionable = document.getElementById('role-mentionable').checked;
    
    const permissions = [];
    document.querySelectorAll('.role-perm:checked').forEach(checkbox => {
        permissions.push(checkbox.value);
    });
    
    try {
        const res = await fetch(`/api/guild/${guildId}/roles`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                color,
                hoist,
                mentionable,
                permissions
            })
        });
        
        if (res.ok) {
            showNotification('Role created successfully!', 'success');
            document.getElementById('create-role-form').reset();
        } else {
            const error = await res.json();
            showNotification(error.error || 'Failed to create role', 'error');
        }
    } catch (error) {
        showNotification('Failed to create role', 'error');
    }
});

async function createBulkRoles() {
    const textarea = document.getElementById('bulk-roles');
    const roleNames = textarea.value.split('\n').filter(name => name.trim());
    
    if (roleNames.length === 0) {
        showNotification('Please enter at least one role name', 'error');
        return;
    }
    
    try {
        const res = await fetch(`/api/guild/${guildId}/roles/bulk`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role_names: roleNames })
        });
        
        if (res.ok) {
            const result = await res.json();
            showNotification(`Created ${result.created} roles successfully!`, 'success');
            textarea.value = '';
        } else {
            const error = await res.json();
            showNotification(error.error || 'Failed to create roles', 'error');
        }
    } catch (error) {
        showNotification('Failed to create roles', 'error');
    }
}

// Server Setup Templates
async function applyTemplate(templateName) {
    if (!confirm(`Apply the ${templateName} template? This will create channels, roles, and categories.`)) {
        return;
    }
    
    try {
        const res = await fetch(`/api/guild/${guildId}/template`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ template: templateName })
        });
        
        if (res.ok) {
            showNotification('Template applied successfully!', 'success');
        } else {
            const error = await res.json();
            showNotification(error.error || 'Failed to apply template', 'error');
        }
    } catch (error) {
        showNotification('Failed to apply template', 'error');
    }
}

function openCustomSetup() {
    showNotification('Custom setup coming soon!', 'info');
}

// Moderation Settings
document.getElementById('modlog-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const channelId = document.getElementById('modlog-channel').value;
    
    try {
        const res = await fetch(`/api/guild/${guildId}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ modlog_channel_id: channelId })
        });
        
        if (res.ok) {
            showNotification('Modlog channel updated!', 'success');
        } else {
            showNotification('Failed to update modlog channel', 'error');
        }
    } catch (error) {
        showNotification('Failed to update modlog channel', 'error');
    }
});

// Welcome/Leave Settings
document.getElementById('welcome-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const channelId = document.getElementById('welcome-channel').value;
    const message = document.getElementById('welcome-message').value;
    
    try {
        const res = await fetch(`/api/guild/${guildId}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                welcome_channel_id: channelId,
                welcome_message: message
            })
        });
        
        if (res.ok) {
            showNotification('Welcome settings updated!', 'success');
        } else {
            showNotification('Failed to update welcome settings', 'error');
        }
    } catch (error) {
        showNotification('Failed to update welcome settings', 'error');
    }
});

document.getElementById('leave-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const message = document.getElementById('leave-message').value;
    
    try {
        const res = await fetch(`/api/guild/${guildId}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ leave_message: message })
        });
        
        if (res.ok) {
            showNotification('Leave message updated!', 'success');
        } else {
            showNotification('Failed to update leave message', 'error');
        }
    } catch (error) {
        showNotification('Failed to update leave message', 'error');
    }
});

// General Settings
document.getElementById('settings-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const prefix = document.getElementById('prefix').value;
    const autoRoleId = document.getElementById('auto-role').value;
    
    try {
        const res = await fetch(`/api/guild/${guildId}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prefix: prefix,
                auto_role_id: autoRoleId
            })
        });
        
        if (res.ok) {
            showNotification('Settings updated!', 'success');
        } else {
            showNotification('Failed to update settings', 'error');
        }
    } catch (error) {
        showNotification('Failed to update settings', 'error');
    }
});

// Economy Settings
document.getElementById('economy-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const currencyName = document.getElementById('currency-name').value;
    const currencyEmoji = document.getElementById('currency-emoji').value;
    const dailyAmount = parseInt(document.getElementById('daily-amount').value);
    
    try {
        const res = await fetch(`/api/guild/${guildId}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                currency_name: currencyName,
                currency_emoji: currencyEmoji,
                daily_amount: dailyAmount
            })
        });
        
        if (res.ok) {
            showNotification('Economy settings updated!', 'success');
        } else {
            showNotification('Failed to update economy settings', 'error');
        }
    } catch (error) {
        showNotification('Failed to update economy settings', 'error');
    }
});

// Leveling Quick Setup
document.getElementById('leveling-quick-setup-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const milestones = document.getElementById('level-milestones').value;
    const createInfo = document.getElementById('create-info-channel').checked;
    const createRules = document.getElementById('create-rules-channel').checked;
    
    if (!confirm('This will create roles and channels in your server. Continue?')) {
        return;
    }
    
    try {
        const res = await fetch(`/api/guild/${guildId}/leveling-setup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                milestones: milestones,
                create_info_channel: createInfo,
                create_rules_channel: createRules
            })
        });
        
        const data = await res.json();
        
        if (res.ok) {
            showNotification(data.message || 'Leveling system setup complete!', 'success');
            setTimeout(() => location.reload(), 2000);
        } else {
            showNotification(data.error || 'Failed to setup leveling system', 'error');
        }
    } catch (error) {
        showNotification('Failed to setup leveling system', 'error');
        console.error(error);
    }
});

// Leveling Settings
document.getElementById('leveling-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const levelingEnabled = document.getElementById('leveling-enabled').checked;
    const xpMin = parseInt(document.getElementById('xp-min').value);
    const xpMax = parseInt(document.getElementById('xp-max').value);
    const levelUpChannel = document.getElementById('level-up-channel').value;
    
    try {
        const res = await fetch(`/api/guild/${guildId}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                leveling_enabled: levelingEnabled,
                xp_min: xpMin,
                xp_max: xpMax,
                level_up_channel_id: levelUpChannel
            })
        });
        
        if (res.ok) {
            showNotification('Leveling settings updated!', 'success');
        } else {
            showNotification('Failed to update leveling settings', 'error');
        }
    } catch (error) {
        showNotification('Failed to update leveling settings', 'error');
    }
});

// Level Role Rewards
document.getElementById('level-role-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const level = parseInt(document.getElementById('level-number').value);
    const roleId = document.getElementById('level-role-id').value;
    
    try {
        const res = await fetch(`/api/guild/${guildId}/level-roles`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ level, role_id: roleId })
        });
        
        if (res.ok) {
            showNotification(`Level ${level} role reward added!`, 'success');
            document.getElementById('level-role-form').reset();
        } else {
            const error = await res.json();
            showNotification(error.error || 'Failed to add level role', 'error');
        }
    } catch (error) {
        showNotification('Failed to add level role', 'error');
    }
});

// Giveaway Creation
document.getElementById('giveaway-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const channelId = document.getElementById('giveaway-channel').value;
    const prize = document.getElementById('giveaway-prize').value;
    const description = document.getElementById('giveaway-description').value;
    const duration = parseInt(document.getElementById('giveaway-duration').value);
    const winners = parseInt(document.getElementById('giveaway-winners').value);
    
    try {
        const res = await fetch(`/api/guild/${guildId}/giveaway`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                channel_id: channelId,
                prize,
                description,
                duration_minutes: duration,
                winner_count: winners
            })
        });
        
        if (res.ok) {
            showNotification('Giveaway started successfully!', 'success');
            document.getElementById('giveaway-form').reset();
        } else {
            const error = await res.json();
            showNotification(error.error || 'Failed to start giveaway', 'error');
        }
    } catch (error) {
        showNotification('Failed to start giveaway', 'error');
    }
});

// Utility Functions
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    // Style notification
    Object.assign(notification.style, {
        position: 'fixed',
        top: '20px',
        right: '20px',
        padding: '1rem 1.5rem',
        borderRadius: '8px',
        color: 'white',
        fontWeight: '600',
        zIndex: '1000',
        animation: 'slideIn 0.3s ease',
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)'
    });
    
    // Set background color based on type
    const colors = {
        success: '#57F287',
        error: '#ED4245',
        info: '#5865F2',
        warning: '#FEE75C'
    };
    notification.style.background = colors[type] || colors.info;
    
    // Add to DOM
    document.body.appendChild(notification);
    
    // Remove after 3 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Role color picker sync
document.getElementById('role-color')?.addEventListener('input', (e) => {
    const hex = e.target.value;
    document.getElementById('role-color-hex').value = hex;
    document.getElementById('role-color-preview').style.background = hex;
});

document.getElementById('role-color-hex')?.addEventListener('input', (e) => {
    const hex = e.target.value;
    if (/^#[0-9A-F]{6}$/i.test(hex)) {
        document.getElementById('role-color').value = hex;
        document.getElementById('role-color-preview').style.background = hex;
    }
});

// Role templates
const roleTemplates = {
    gaming: [
        { name: "Gaming", color: "#00ff88" },
        { name: "Streamer", color: "#9146ff" },
        { name: "Content Creator", color: "#ff006e" },
        { name: "Pro Player", color: "#ffd700" },
        { name: "Casual Gamer", color: "#3a86ff" }
    ],
    staff: [
        { name: "Owner", color: "#ff0000" },
        { name: "Admin", color: "#ff4500" },
        { name: "Moderator", color: "#4169e1" },
        { name: "Helper", color: "#32cd32" },
        { name: "Bot", color: "#7289da" }
    ],
    community: [
        { name: "VIP", color: "#ffd700" },
        { name: "Premium", color: "#00ffff" },
        { name: "Member", color: "#99aab5" },
        { name: "Newcomer", color: "#95a5a6" },
        { name: "Verified", color: "#43b581" }
    ],
    colors: [
        { name: "Red", color: "#e74c3c" },
        { name: "Orange", color: "#e67e22" },
        { name: "Yellow", color: "#f1c40f" },
        { name: "Green", color: "#2ecc71" },
        { name: "Blue", color: "#3498db" },
        { name: "Purple", color: "#9b59b6" },
        { name: "Brown", color: "#a0826d" },
        { name: "Black", color: "#2c3e50" }
    ]
};

async function applyRoleTemplate(templateName) {
    const template = roleTemplates[templateName];
    if (!template) return;
    
    if (!confirm(`Create ${template.length} roles for the ${templateName} template?`)) return;
    
    showNotification(`Creating ${template.length} roles...`, 'info');
    
    for (const role of template) {
        try {
            const res = await fetch(`/api/guild/${guildId}/roles`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: role.name,
                    color: role.color,
                    permissions: []
                })
            });
            
            if (!res.ok) {
                console.error(`Failed to create role: ${role.name}`);
            }
        } catch (error) {
            console.error(`Error creating role ${role.name}:`, error);
        }
    }
    
    showNotification('Roles created successfully!', 'success');
    setTimeout(() => location.reload(), 2000);
}

// Bulk role creator
async function createBulkRoles() {
    const textarea = document.getElementById('bulk-roles');
    const roleNames = textarea.value.split('\\n').filter(n => n.trim());
    
    if (roleNames.length === 0) {
        showNotification('Enter at least one role name', 'error');
        return;
    }
    
    if (!confirm(`Create ${roleNames.length} roles?`)) return;
    
    showNotification(`Creating ${roleNames.length} roles...`, 'info');
    
    for (const name of roleNames) {
        try {
            await fetch(`/api/guild/${guildId}/roles`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name.trim(), color: '#99AAB5', permissions: [] })
            });
        } catch (error) {
            console.error(`Error creating role ${name}:`, error);
        }
    }
    
    showNotification('Roles created successfully!', 'success');
    setTimeout(() => location.reload(), 2000);
}

// Theme application
async function applyTheme(themeName) {
    showNotification(`Applying ${themeName} theme...`, 'info');
    // Theme is visual only - could store preference in config
    showNotification('Theme applied! (Visual only)', 'success');
}

// Ticket category management
function addTicketCategory() {
    const list = document.getElementById('ticket-categories-list');
    const item = document.createElement('div');
    item.className = 'ticket-category-item';
    item.innerHTML = `
        <input type="text" placeholder="Category Name" style="flex: 1;">
        <input type="text" placeholder="🎫" style="width: 60px;">
        <button type="button" class="btn-icon" onclick="this.parentElement.remove()">❌</button>
    `;
    list.appendChild(item);
}

// Load server roles
async function loadServerRoles() {
    try {
        const res = await fetch(`/api/guild/${guildId}/roles`);
        if (res.ok) {
            const data = await res.json();
            const rolesList = document.getElementById('roles-list');
            if (rolesList && data.roles) {
                rolesList.innerHTML = data.roles.map(role => `
                    <div style="display: flex; align-items: center; padding: 10px; border-bottom: 1px solid var(--border); gap: 10px;">
                        <div style="width: 20px; height: 20px; border-radius: 50%; background: ${role.color || '#99aab5'};"></div>
                        <span style="flex: 1;">${role.name}</span>
                        <span style="color: #72767d; font-size: 12px;">${role.member_count || 0} members</span>
                    </div>
                `).join('');
            }
        }
    } catch (error) {
        console.error('Failed to load roles:', error);
    }
}

// Load roles on page load
if (document.getElementById('roles-section')) {
    loadServerRoles();
}

// Add CSS for notifications
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
    
    .ticket-category-item {
        display: flex;
        gap: 10px;
        margin-bottom: 10px;
        align-items: center;
    }
    
    .ticket-category-item input {
        background: var(--bg-secondary);
        border: 1px solid var(--border);
        color: var(--text);
        padding: 10px;
        border-radius: 5px;
    }
    
    .btn-icon {
        background: none;
        border: none;
        cursor: pointer;
        font-size: 18px;
        padding: 5px;
    }
    
    .theme-card {
        cursor: pointer;
        padding: 15px;
        border: 2px solid var(--border);
        border-radius: 8px;
        transition: all 0.2s;
    }
    
    .theme-card:hover {
        border-color: var(--accent);
        transform: translateY(-2px);
    }
    
    .theme-card h4 {
        margin: 5px 0;
        color: var(--text);
    }
    
    .theme-card p {
        margin: 0;
        color: #72767d;
        font-size: 14px;
    }
`;
document.head.appendChild(style);

