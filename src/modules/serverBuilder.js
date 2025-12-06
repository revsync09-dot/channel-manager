import { ChannelType, PermissionsBitField } from 'discord.js';

// Create categories, channels, and roles from a template.
export async function buildServerFromTemplate(guild, template) {
  const roleIdMap = await ensureRoles(guild, template.roles || []);

  for (const category of template.categories) {
    const categoryName = sanitizeName(category.name || 'Category');
    const categoryChannel = await guild.channels.create({
      name: categoryName,
      type: ChannelType.GuildCategory
    });

    for (const ch of category.channels || []) {
      const name = sanitizeName(ch.name || 'channel');
      const isVoice = isVoiceType(ch.type);
      const payload = {
        name,
        type: isVoice ? ChannelType.GuildVoice : ChannelType.GuildText,
        parent: categoryChannel.id
      };

      if (!isVoice) {
        payload.topic = ch.topic ? ch.topic.slice(0, 1024) : undefined;
        payload.nsfw = Boolean(ch.nsfw);
        payload.rateLimitPerUser = ch.slowmode || 0;
      }

      const channel = await createChannelSafe(guild, payload);

      if (Array.isArray(ch.overwrites)) {
        for (const ow of ch.overwrites) {
          const mappedRoleId = roleIdMap.get(ow.roleRefId);
          if (!mappedRoleId) continue;
          await channel.permissionOverwrites.create(mappedRoleId, {
            allow: normalizePermValue(ow.allow),
            deny: normalizePermValue(ow.deny)
          });
        }
      }
    }
  }
}

async function ensureRoles(guild, roleTemplates) {
  const map = new Map();
  map.set('everyone', guild.roles.everyone.id);

  for (const tpl of roleTemplates) {
    if (tpl.isEveryone || tpl.refId === guild.roles.everyone.id) {
      map.set(tpl.refId, guild.roles.everyone.id);
      continue;
    }
    const role = await guild.roles.create({
      name: tpl.name,
      color: tpl.color,
      hoist: tpl.hoist,
      mentionable: tpl.mentionable,
      permissions: normalizePermValue(tpl.permissions)
    });
    map.set(tpl.refId, role.id);
  }
  return map;
}

function sanitizeName(name) {
  const trimmed = (name || '').trim();
  if (!trimmed) return 'channel';
  return trimmed.slice(0, 90);
}

function isVoiceType(type) {
  if (typeof type === 'number') {
    return type === ChannelType.GuildVoice;
  }
  return String(type).toLowerCase() === 'voice';
}

async function createChannelSafe(guild, payload) {
  try {
    return await guild.channels.create(payload);
  } catch (err) {
    const topicInvalid = err?.rawError?.errors?.topic || err?.code === 50035;
    if (topicInvalid && payload.topic) {
      const clone = { ...payload };
      delete clone.topic;
      return await guild.channels.create(clone);
    }
    throw err;
  }
}

function normalizePermValue(val) {
  if (val instanceof PermissionsBitField) {
    return val;
  }
  if (val && typeof val === 'object' && val.bitfield !== undefined) {
    try {
      return new PermissionsBitField(BigInt(val.bitfield));
    } catch {
      return new PermissionsBitField(0n);
    }
  }
  if (val !== undefined && val !== null) {
    try {
      return new PermissionsBitField(BigInt(val));
    } catch {
      return new PermissionsBitField(val);
    }
  }
  return new PermissionsBitField(0n);
}
