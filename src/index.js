import 'dotenv/config.js';
import {
  Client,
  GatewayIntentBits,
  REST,
  Routes,
  EmbedBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  SlashCommandBuilder,
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
  StringSelectMenuBuilder,
  PermissionsBitField
} from 'discord.js';
import { analyzeImageStub } from './modules/imageAnalyzer.js';
import { parseTextStructure } from './modules/textParser.js';
import { buildServerFromTemplate } from './modules/serverBuilder.js';
import { sendTicketPanel, handleTicketButton, handleTicketModal } from './modules/ticketSystem.js';

const token = process.env.DISCORD_TOKEN;
const clientId = process.env.CLIENT_ID;

if (!token || !clientId) {
  console.error('Please set DISCORD_TOKEN and CLIENT_ID inside .env');
  process.exit(1);
}

const client = new Client({ intents: [GatewayIntentBits.Guilds] });
const MAX_CHANNELS = 500;
const MAX_ROLES = 200;
const EMBED_COLOR = 0x22c55e;
const EMBED_THUMB =
  'https://media.discordapp.net/attachments/1443222738750668952/1446618834638471259/Channel-manager.png?format=webp&quality=lossless';

const commands = [
  new SlashCommandBuilder().setName('setup').setDescription('Open the server builder panel.'),
  new SlashCommandBuilder().setName('health').setDescription('Show bot status.'),
  new SlashCommandBuilder().setName('help').setDescription('Show a short help message.'),
  new SlashCommandBuilder().setName('delete_channel').setDescription('Delete all channels and categories in this server.'),
  new SlashCommandBuilder().setName('delete_roles').setDescription('Delete all deletable roles (except @everyone/managed/above bot).'),
  new SlashCommandBuilder().setName('ticketpanel').setDescription('Post the ticket panel (only allowed in the ticket channel).')
];

async function registerCommands() {
  const rest = new REST({ version: '10' }).setToken(token);
  try {
    await rest.put(Routes.applicationCommands(clientId), { body: commands.map(cmd => cmd.toJSON()) });
    console.log('Slash commands registered.');
  } catch (err) {
    console.error('Could not register commands:', err.message);
  }
}

client.on('ready', () => {
  console.log(`Bot logged in as ${client.user?.tag || 'unknown'}`);
});

client.on('guildCreate', async guild => {
  try {
    const owner = await guild.fetchOwner();
    const embed = new EmbedBuilder()
      .setTitle('Welcome to Channel Manager')
      .setColor(EMBED_COLOR)
      .setThumbnail(EMBED_THUMB)
      .setDescription(
        [
          'Thanks for adding the bot.',
          '1) Run /setup and pick an action (Image, Text, Clone, Roles).',
          '2) Paste your structure and let it build.',
          '3) Discord hard limit is about 500 channels per server.',
          '',
          'Support server link is below.'
        ].join('\n')
      )
      .setFooter({ text: 'Channel Manager - simple server builder' });

    const supportRow = new ActionRowBuilder().addComponents(
      new ButtonBuilder().setLabel('Support Server').setStyle(ButtonStyle.Link).setURL('https://discord.gg/zjr3Umcu')
    );

    await owner.send({ embeds: [embed], components: [supportRow] });
  } catch (err) {
    console.error('Could not DM the owner:', err.message);
  }
});

client.on('interactionCreate', async interaction => {
  if (interaction.isChatInputCommand()) {
    if (interaction.commandName === 'health') {
      return handleHealth(interaction);
    }
    if (interaction.commandName === 'help') {
      return handleHelp(interaction);
    }
    if (interaction.commandName === 'delete_channel') {
      return handleDeleteChannels(interaction);
    }
    if (interaction.commandName === 'delete_roles') {
      return handleDeleteRoles(interaction);
    }
    if (interaction.commandName === 'ticketpanel') {
      return sendTicketPanel(interaction);
    }
    if (interaction.commandName === 'setup') {
      return showSetupPanel(interaction);
    }
  }

  if (interaction.isStringSelectMenu()) {
    return handleSelect(interaction);
  }
  if (interaction.isModalSubmit()) {
    const handled = await handleTicketModal(interaction, client);
    if (handled) return;
    return handleModal(interaction);
  }
  if (interaction.isButton()) {
    const handled = await handleTicketButton(interaction);
    if (handled) return;
  }
});

function showSetupPanel(interaction) {
  const embed = new EmbedBuilder()
    .setTitle('Channel Manager Panel')
    .setColor(EMBED_COLOR)
    .setThumbnail(EMBED_THUMB)
    .setDescription(
      [
        'Pick one option below:',
        '- Image OCR: give a screenshot URL and build.',
        '- Text Import: paste a text list.',
        '- Clone: copy a server the bot is in.',
        '- Roles Import: create roles from text.'
      ].join('\n')
    )
    .setFooter({ text: 'Channel Manager - basic panel' });

  const menu = new StringSelectMenuBuilder()
    .setCustomId('setup-select')
    .setPlaceholder('Choose an action...')
    .addOptions(
      { label: 'Image OCR', description: 'Enter an image URL', value: 'setup-image' },
      { label: 'Text Import', description: 'Paste a text structure', value: 'setup-text' },
      { label: 'Clone Server', description: 'Read a server and build it here', value: 'setup-clone' },
      { label: 'Roles Import', description: 'Make roles from text', value: 'setup-roles' }
    );

  const row = new ActionRowBuilder().addComponents(menu);
  return interaction.reply({ embeds: [embed], components: [row], flags: 1 << 6 });
}

async function handleSelect(interaction) {
  try {
    const selected = interaction.values[0];

    if (selected === 'setup-image') {
      const modal = new ModalBuilder().setCustomId('modal-image').setTitle('Image OCR');
      const imageUrl = new TextInputBuilder()
        .setCustomId('image_url')
        .setLabel('Image URL (public)')
        .setStyle(TextInputStyle.Short)
        .setRequired(true);
      modal.addComponents(new ActionRowBuilder().addComponents(imageUrl));
      return interaction.showModal(modal);
    }

    if (selected === 'setup-text') {
      const modal = new ModalBuilder().setCustomId('modal-text').setTitle('Text Import');
      const textArea = new TextInputBuilder()
        .setCustomId('text_structure')
        .setLabel('Structure (indented)')
        .setStyle(TextInputStyle.Paragraph)
        .setRequired(true)
        .setValue('INFORMATION\n  #rules | Type: text | Permissions: [View Channel, Read Message History]');
      modal.addComponents(new ActionRowBuilder().addComponents(textArea));
      return interaction.showModal(modal);
    }

    if (selected === 'setup-clone') {
      const modal = new ModalBuilder().setCustomId('modal-clone').setTitle('Clone Server');
      const guildId = new TextInputBuilder()
        .setCustomId('source_guild_id')
        .setLabel('Server ID (bot must be in it)')
        .setStyle(TextInputStyle.Short)
        .setRequired(true);
      modal.addComponents(new ActionRowBuilder().addComponents(guildId));
      return interaction.showModal(modal);
    }

    if (selected === 'setup-roles') {
      const modal = new ModalBuilder().setCustomId('modal-roles').setTitle('Roles Import');
      const rolesText = new TextInputBuilder()
        .setCustomId('roles_structure')
        .setLabel('Roles (one per line, with Color + Permissions)')
        .setStyle(TextInputStyle.Paragraph)
        .setRequired(true)
        .setValue('Owner | Color: #ff0000 | Permissions: [Administrator, Manage Roles]');
      modal.addComponents(new ActionRowBuilder().addComponents(rolesText));
      return interaction.showModal(modal);
    }
  } catch (err) {
    console.error('Select handler error:', err);
    if (interaction.deferred || interaction.replied) {
      return interaction.editReply({ content: 'Error: ' + err.message });
    }
    return interaction.reply({ content: 'Error: ' + err.message, flags: 1 << 6 });
  }
}

async function handleHealth(interaction) {
  const statusMap = ['READY', 'CONNECTING', 'RECONNECTING', 'IDLE', 'NEARLY', 'DISCONNECTED'];
  const status = statusMap[client.ws.status] ?? String(client.ws.status);
  const ping = Math.max(0, Math.round(client.ws.ping));
  const guildCount = client.guilds.cache.size;
  const channelCount = client.channels.cache?.size ?? 0;
  const uptimeMs = Date.now() - (client.readyTimestamp ?? Date.now());
  const mem = process.memoryUsage();
  const formatUptime = ms => {
    const totalSec = Math.floor(ms / 1000);
    const d = Math.floor(totalSec / 86400);
    const h = Math.floor((totalSec % 86400) / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    return `${d}d ${h}h ${m}m ${s}s`;
  };

  const embed = new EmbedBuilder()
    .setTitle('Channel Manager Health')
    .setColor(EMBED_COLOR)
    .setThumbnail(EMBED_THUMB)
    .addFields(
      { name: 'Status', value: status, inline: true },
      { name: 'Ping', value: `${ping} ms`, inline: true },
      { name: 'Uptime', value: formatUptime(uptimeMs), inline: true },
      { name: 'Servers', value: `${guildCount}`, inline: true },
      { name: 'Channels (cached)', value: `${channelCount}`, inline: true },
      { name: 'Memory', value: `${Math.round(mem.rss / 1024 / 1024)} MB RSS`, inline: true },
      { name: 'Runtime', value: `Node ${process.version} | discord.js 14`, inline: false }
    )
    .setFooter({ text: 'Channel Manager - system health' })
    .setTimestamp(new Date());

  return interaction.reply({ embeds: [embed], flags: 1 << 6 });
}

async function handleHelp(interaction) {
  const channelExample = [
    '📌 INFORMATION (category)',
    '  📢│#announcements',
    '  📜│#bot-info',
    '',
    '🎫 SUPPORT (category)',
    '  🎫│#create-ticket',
    '  ❓│#help',
    '  🐞│#bug-report',
    '',
    '💡 COMMUNITY (category)',
    '  💭│#general',
    '  ⭐│#showcase',
    '',
    '📊 LOGS (staff only) (category)',
    '  📝│#ticket-log',
    '  🤖│#bot-log'
  ].join('\n');

  const rolesBlock = [
    'STAFF & ADMIN (roles)',
    '  Owner | Color: #ff0000 | Permissions: [Administrator, Manage Server, Manage Roles]',
    '  Moderator | Color: #ff944d | Permissions: [Kick Members, Ban Members, Timeout Members, Manage Messages]'
  ].join('\n');

  const embed = new EmbedBuilder()
    .setTitle('Channel Builder Help')
    .setColor(EMBED_COLOR)
    .setThumbnail(EMBED_THUMB)
    .setDescription(
      [
        '1) Run /setup and pick what you need.',
        '2) For text import, paste something like this:',
        '```',
        channelExample,
        '```',
        '3) Roles import example:',
        '```',
        rolesBlock,
        '```',
        'Notes:',
        '- Bot must be in the source server to clone.',
        '- Max around 500 channels per server.',
        '- Bot needs Manage Channels and Manage Roles permissions.'
      ].join('\n')
    )
    .setFooter({ text: 'Channel Manager - simple help' });

  return interaction.reply({ embeds: [embed], flags: 1 << 6 });
}

async function handleDeleteChannels(interaction) {
  if (!interaction.guild) {
    return interaction.reply({ content: 'Please run this inside a server.', flags: 1 << 6 });
  }

  await interaction.reply({ content: 'Deleting all channels and categories...', flags: 1 << 6 });

  const guild = interaction.guild;

  const channels = await guild.channels.fetch();
  let channelsDeleted = 0;
  const channelDeletes = [];
  channels.forEach(ch => {
    if (!ch) return;
    if (ch.deletable) {
      channelDeletes.push(
        ch.delete('Requested by /delete').then(() => {
          channelsDeleted += 1;
        })
      );
    }
  });

  await Promise.allSettled(channelDeletes);
  await interaction.editReply({ content: `Delete finished. Channels/categories removed: ${channelsDeleted}.` });
}

async function handleDeleteRoles(interaction) {
  if (!interaction.guild) {
    return interaction.reply({ content: 'Please run this inside a server.', flags: 1 << 6 });
  }

  await interaction.reply({ content: 'Deleting roles (skipping @everyone, managed, and above my role)...', flags: 1 << 6 });

  const guild = interaction.guild;
  const me = guild.members.me ?? (await guild.members.fetchMe());
  const myTopPos = me?.roles.highest?.position ?? 0;

  const roles = await guild.roles.fetch();
  let rolesDeleted = 0;
  const roleDeletes = [];
  roles.forEach(role => {
    if (!role) return;
    if (role.id === guild.roles.everyone.id) return;
    if (role.managed) return;
    if (role.position >= myTopPos) return;
    roleDeletes.push(
      role.delete('Requested by /delete_roles').then(() => {
        rolesDeleted += 1;
      })
    );
  });

  await Promise.allSettled(roleDeletes);
  await interaction.editReply({ content: `Delete finished. Roles removed: ${rolesDeleted}.` });
}

async function handleModal(interaction) {
  try {
    if (interaction.customId === 'modal-image') {
      const imageUrl = interaction.fields.getTextInputValue('image_url');
      await interaction.reply({ content: 'Reading image...', flags: 1 << 6 });
      const template = await analyzeImageStub(imageUrl);
      ensureTemplateSafe(template);
      if (!interaction.guild) {
        await interaction.editReply({ content: 'Template ready. Please run this in a server.' });
        return;
      }
      try {
        await buildServerFromTemplate(interaction.guild, template);
        await interaction.editReply({ content: 'Server built from image OCR.' });
      } catch (err) {
        await interaction.editReply({ content: 'Build failed: ' + err.message });
      }
      return;
    }

    if (interaction.customId === 'modal-text') {
      const structure = interaction.fields.getTextInputValue('text_structure');
      if (!interaction.guild) {
        await interaction.reply({ content: 'Please run this inside a server.', flags: 1 << 6 });
        return;
      }
      await interaction.reply({ content: 'Reading structure...', flags: 1 << 6 });
      const template = parseTextStructure(structure);
      ensureTemplateSafe(template);
      try {
        await buildServerFromTemplate(interaction.guild, template);
        await interaction.editReply({ content: 'Server built.' });
      } catch (err) {
        await interaction.editReply({ content: 'Build failed: ' + err.message });
      }
      return;
    }

    if (interaction.customId === 'modal-clone') {
      const sourceGuildId = interaction.fields.getTextInputValue('source_guild_id');
      await interaction.reply({ content: 'Cloning server...', flags: 1 << 6 });
      try {
        const sourceGuild = await client.guilds.fetch(sourceGuildId);
        const template = await fromGuild(sourceGuild);
        ensureTemplateSafe(template);
        if (!interaction.guild) {
          await interaction.editReply({ content: 'Template saved. Please run this in a server.' });
          return;
        }
        await buildServerFromTemplate(interaction.guild, template);
        await interaction.editReply({ content: 'Server cloned and built.' });
      } catch (err) {
        const msg = err?.code === 10004 ? 'Server not found or bot not in it.' : err.message;
        await interaction.editReply({ content: 'Clone failed: ' + msg });
      }
      return;
    }

    if (interaction.customId === 'modal-roles') {
      if (!interaction.guild) {
        await interaction.reply({ content: 'Please run this inside a server.', flags: 1 << 6 });
        return;
      }
      const rolesText = interaction.fields.getTextInputValue('roles_structure');
      await interaction.reply({ content: 'Creating roles...', flags: 1 << 6 });
      try {
        const parsed = parseTextStructure(rolesText);
        const created = await createRoles(interaction.guild, parsed.roles || []);
        await interaction.editReply({ content: `Created ${created.length} roles.` });
      } catch (err) {
        await interaction.editReply({ content: 'Could not create roles: ' + err.message });
      }
    }
  } catch (err) {
    console.error('Modal error:', err);
    if (interaction.deferred || interaction.replied) {
      await interaction.editReply({ content: 'Error: ' + err.message });
    } else {
      await interaction.reply({ content: 'Error: ' + err.message, flags: 1 << 6 });
    }
  }
}

async function createRoles(guild, roles) {
  const created = [];
  for (const roleData of roles) {
    const perms = normalizePermissionsInput(roleData.permissions);
    const role = await guild.roles.create({
      name: roleData.name,
      color: roleData.color,
      hoist: roleData.hoist ?? false,
      mentionable: roleData.mentionable ?? true,
      permissions: perms
    });
    created.push(role);
  }
  return created;
}

function normalizePermissionsInput(input) {
  if (!input) {
    return new PermissionsBitField(0n);
  }
  if (input instanceof PermissionsBitField) {
    return input;
  }
  if (typeof input === 'object' && input.bitfield !== undefined) {
    try {
      return new PermissionsBitField(BigInt(input.bitfield));
    } catch {
      return new PermissionsBitField(0n);
    }
  }
  try {
    const asBigInt = BigInt(input);
    return new PermissionsBitField(asBigInt);
  } catch {
    return new PermissionsBitField(input);
  }
}

async function fromGuild(guild) {
  const categories = [];
  const channels = await guild.channels.fetch();
  const roles = await guild.roles.fetch();

  const roleTemplates = [];
  roles
    .sort((a, b) => a.rawPosition - b.rawPosition)
    .forEach(role => {
      roleTemplates.push({
        refId: role.id,
        name: role.name,
        color: role.color,
        hoist: role.hoist,
        mentionable: role.mentionable,
        permissions: role.permissions.bitfield.toString(),
        position: role.rawPosition,
        isEveryone: role.id === guild.roles.everyone.id
      });
    });

  const categoryMap = new Map();
  channels
    .filter(ch => ch.type === 4)
    .sort((a, b) => a.rawPosition - b.rawPosition)
    .forEach(cat => {
      categoryMap.set(cat.id, { name: cat.name, channels: [] });
    });

  channels
    .filter(ch => ch.parentId)
    .sort((a, b) => a.rawPosition - b.rawPosition)
    .forEach(ch => {
      const parent = categoryMap.get(ch.parentId);
      if (!parent) return;
      parent.channels.push({
        name: ch.name,
        type: ch.type === 2 ? 'voice' : 'text',
        topic: ch.topic,
        nsfw: ch.nsfw,
        slowmode: ch.rateLimitPerUser,
        overwrites: ch.permissionOverwrites.cache
          .filter(ow => ow.type === 0)
          .map(ow => ({
            roleRefId: ow.id,
            allow: ow.allow.bitfield.toString(),
            deny: ow.deny.bitfield.toString()
          }))
      });
    });

  categoryMap.forEach(cat => categories.push(cat));
  return {
    roles: roleTemplates,
    categories,
    summary: `${categories.length} categories copied`
  };
}

function ensureTemplateSafe(template) {
  if (!template || !Array.isArray(template.categories)) {
    throw new Error('Template is not valid.');
  }
  let channelCount = 0;
  for (const cat of template.categories) {
    channelCount += cat.channels ? cat.channels.length : 0;
  }
  const roleCount = Array.isArray(template.roles) ? template.roles.length : 0;
  if (channelCount > MAX_CHANNELS) {
    throw new Error(`Too many channels (${channelCount}). Discord limit is around 500.`);
  }
  if (roleCount > MAX_ROLES) {
    throw new Error(`Too many roles (${roleCount}).`);
  }
}

registerCommands().catch(console.error);
client.login(token);
