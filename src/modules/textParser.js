import { PermissionsBitField } from 'discord.js';

// Reads a simple indented structure with categories, channels, and roles.
export function parseTextStructure(raw) {
  const lines = raw
    .split(/\r?\n/)
    .map(l => normalizeLine(l.trimEnd()))
    .filter(Boolean);

  const template = { categories: [], roles: [] };
  let currentCategory = null;

  for (const line of lines) {
    if (isRoleLine(line)) {
      const role = buildRoleFromLine(line);
      if (role) {
        template.roles.push(role);
      }
      continue;
    }

    const trimmed = normalizeLine(line.trim());
    const isChannel = looksLikeChannel(trimmed);
    const isCategory = isCategoryLine(trimmed) || (!isChannel && !trimmed.startsWith('-'));

    if (isCategory) {
      currentCategory = { name: cleanCategoryName(trimmed), channels: [] };
      template.categories.push(currentCategory);
      continue;
    }

    if (!currentCategory) {
      currentCategory = { name: 'General', channels: [] };
      template.categories.push(currentCategory);
    }

    const channel = buildChannelFromLine(trimmed);
    currentCategory.channels.push(channel);
  }

  let totalChannels = 0;
  for (const cat of template.categories) {
    totalChannels += cat.channels.length;
  }
  template.summary = `${template.categories.length} categories / ${totalChannels} channels`;
  return template;
}

function looksLikeChannel(line) {
  const normalized = normalizeLine(line);
  const hasPipe = normalized.includes('|');
  const hasHash = /#\S+/.test(normalized);
  const hasType = /type:\s*(text|voice)/i.test(normalized);
  const hasVoiceWord = /\bvoice\b/i.test(normalized);
  return hasPipe || hasHash || hasType || hasVoiceWord;
}

function buildChannelFromLine(line) {
  const normalized = normalizeLine(line);
  const isVoice = /type:\s*voice/i.test(normalized) || /\bvoice\b/i.test(normalized);
  const withoutPrefix = normalized.replace(/^[-\s|]+/, '');
  const hashMatch = normalized.match(/#([\w-]+)/);
  let namePart = hashMatch ? hashMatch[1] : withoutPrefix.split('|')[0].replace(/^#/, '').trim();
  if (!namePart) {
    namePart = withoutPrefix.split(/\s+/)[0];
  }
  const safeName = slugifyPreserve(namePart);
  const topic = extractTopic(normalized) || suggestDescription(safeName, isVoice);
  const perms = extractPermissions(normalized);
  const allowBits = perms.length > 0 ? permissionsToBitfield(perms).bitfield.toString() : undefined;
  const overwrites =
    allowBits !== undefined
      ? [
          {
            roleRefId: 'everyone',
            allow: allowBits,
            deny: '0'
          }
        ]
      : undefined;

  return {
    name: safeName || 'channel',
    type: isVoice ? 'voice' : 'text',
    topic,
    private: false,
    overwrites
  };
}

function cleanCategoryName(name) {
  const normalized = normalizeLine(name).replace(/\(category\)/i, '');
  const noEmoji = normalized.replace(/[^\p{L}\p{N}\s-]/gu, ' ').replace(/\s{2,}/g, ' ');
  const clean = noEmoji.trim();
  return clean || 'Category';
}

function slugifyPreserve(str) {
  if (!str) return 'channel';
  const normalized = normalizeLine(str).replace(/[^\p{L}\p{N}\s_-]/gu, ' ');
  const safe = normalized.replace(/\s+/g, '-').replace(/-+/g, '-').replace(/^-+|-+$/g, '');
  return safe.toLowerCase() || 'channel';
}

function suggestDescription(name, isVoice) {
  const key = name.toLowerCase();
  if (key.includes('welcome')) return 'Welcome channel with server info.';
  if (key.includes('rules')) return 'Server rules.';
  if (key.includes('announce') || key.includes('news')) return 'Announcements.';
  if (key.includes('chat') || key.includes('general')) return 'General chat.';
  if (key.includes('support')) return 'Support channel.';
  if (isVoice) return 'A voice channel for talking.';
  return 'Auto generated description.';
}

function isRoleLine(line) {
  return /color:\s*#/i.test(line);
}

function buildRoleFromLine(line) {
  const colorMatch = line.match(/color:\s*(#[0-9a-fA-F]{6})/i);
  if (!colorMatch) return null;
  const color = parseInt(colorMatch[1].replace('#', ''), 16);
  const perms = extractPermissions(line);
  const namePart = line.replace(colorMatch[0], '').replace(/Permissions:\s*\[[^\]]*\]/i, '').trim();
  const cleanName = namePart.replace(/\s{2,}/g, ' ').trim();
  if (!cleanName) return null;

  return {
    refId: `role-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`,
    name: cleanName,
    color,
    hoist: false,
    mentionable: true,
    permissions: permissionsToBitfield(perms).bitfield.toString(),
    isEveryone: false
  };
}

function extractPermissions(line) {
  const permMatch = line.match(/permissions:\s*\[([^\]]*)\]/i);
  if (!permMatch) return [];
  return permMatch[1]
    .split(',')
    .map(p => p.trim())
    .filter(Boolean);
}

function permissionsToBitfield(perms) {
  const mapped = [];
  for (const p of perms) {
    const norm = p.replace(/\(.*?\)/g, '').trim().toLowerCase();
    switch (norm) {
      case 'administrator':
      case 'manage server':
        mapped.push('Administrator');
        break;
      case 'manage roles':
        mapped.push('ManageRoles');
        break;
      case 'manage channels':
        mapped.push('ManageChannels');
        break;
      case 'manage webhooks':
        mapped.push('ManageWebhooks');
        break;
      case 'manage emojis':
      case 'manage emojis and stickers':
        mapped.push('ManageEmojisAndStickers');
        break;
      case 'ban members':
        mapped.push('BanMembers');
        break;
      case 'kick members':
        mapped.push('KickMembers');
        break;
      case 'view audit log':
        mapped.push('ViewAuditLog');
        break;
      case 'manage messages':
        mapped.push('ManageMessages');
        break;
      case 'manage threads':
        mapped.push('ManageThreads');
        break;
      case 'mention everyone':
        mapped.push('MentionEveryone');
        break;
      case 'timeout members':
      case 'moderate members':
      case 'mute members':
        mapped.push('ModerateMembers');
        break;
      case 'priority speaker':
        mapped.push('PrioritySpeaker');
        break;
      case 'send messages':
        mapped.push('SendMessages');
        break;
      case 'read message history':
        mapped.push('ReadMessageHistory');
        break;
      case 'view channel':
      case 'read channels':
        mapped.push('ViewChannel');
        break;
      case 'connect':
        mapped.push('Connect');
        break;
      case 'speak':
        mapped.push('Speak');
        break;
      case 'stream':
        mapped.push('Stream');
        break;
      case 'use voice activity':
        mapped.push('UseVAD');
        break;
      case 'embed links':
        mapped.push('EmbedLinks');
        break;
      case 'attach files':
        mapped.push('AttachFiles');
        break;
      case 'use external emojis':
        mapped.push('UseExternalEmojis');
        break;
      case 'use external stickers':
        mapped.push('UseExternalStickers');
        break;
      case 'use application commands':
        mapped.push('UseApplicationCommands');
        break;
      case 'add reactions':
        mapped.push('AddReactions');
        break;
      case 'manage events':
        mapped.push('ManageEvents');
        break;
      case 'change nickname':
        mapped.push('ChangeNickname');
        break;
      case 'move members':
        mapped.push('MoveMembers');
        break;
      default:
        break;
    }
  }
  return new PermissionsBitField(mapped);
}

function normalizeLine(str) {
  return str
    .replace(/\ufeff/g, '')
    .replace(/\u200b/g, '')
    .replace(/\u00a0/g, ' ')
    .replace(/[│┃┆┊┇┋｜¦]/g, '|')
    .replace(/[–—]/g, '-');
}

function extractTopic(line) {
  const dashMatch = line.match(/-\s+(.+)/);
  if (dashMatch) {
    return dashMatch[1].trim();
  }
  return null;
}

function isCategoryLine(line) {
  return /\(category\)/i.test(line);
}
