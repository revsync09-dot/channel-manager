import {
  ActionRowBuilder,
  EmbedBuilder,
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
  ChannelType,
  PermissionFlagsBits,
  StringSelectMenuBuilder
} from 'discord.js';

const TICKET_PARENT_CHANNEL_ID = '1447010961939501242';
const TICKET_PING_ROLE_ID = '1447006097704484915';
const ALLOWED_GUILD_ID = '1446890546214731798';
const EMBED_COLOR = 0x22c55e;

export async function sendTicketPanel(interaction) {
  if (!interaction.guild) {
    return interaction.reply({ content: 'Use this inside a server.', flags: 1 << 6 });
  }
  if (interaction.guild.id !== ALLOWED_GUILD_ID) {
    return interaction.reply({ content: 'Ticket system is only available in the main server.', flags: 1 << 6 });
  }

  const { container, panelChannel } = await resolveTargetChannels(interaction.guild);
  if (!container || !panelChannel) {
    return interaction.reply({ content: 'Ticket channel not found or not text-based.', flags: 1 << 6 });
  }

  const embed = new EmbedBuilder()
    .setTitle('Need Help? Open a Ticket')
    .setColor(EMBED_COLOR)
    .setDescription(
      [
        'Select a category and submit your request. Our team will respond ASAP.',
        '• 🛟 Support — General help and questions',
        '• 🐞 Bug Report — Report an issue',
        '• 💳 Billing — Payments and invoices',
        '• 📌 Other — Anything else'
      ].join('\n')
    )
    .setFooter({ text: 'Channel Manager Tickets' });

  const select = new StringSelectMenuBuilder()
    .setCustomId('ticket-select')
    .setPlaceholder('Choose a ticket category...')
    .addOptions(
      { label: 'Support', value: 'Support', description: 'General help and questions', emoji: '🛟' },
      { label: 'Bug Report', value: 'Bug Report', description: 'Report an issue', emoji: '🐞' },
      { label: 'Billing', value: 'Billing', description: 'Payments and invoices', emoji: '💳' },
      { label: 'Other', value: 'Other', description: 'Anything else', emoji: '📌' }
    );

  const row = new ActionRowBuilder().addComponents(select);

  await panelChannel.send({ embeds: [embed], components: [row] });
  return interaction.reply({ content: `Ticket panel posted in ${panelChannel}.`, flags: 1 << 6 });
}

export async function handleTicketSelect(interaction) {
  if (interaction.customId !== 'ticket-select') return false;
  if (!interaction.guild || interaction.guild.id !== ALLOWED_GUILD_ID) {
    await interaction.reply({ content: 'Ticket system is only available in the main server.', flags: 1 << 6 });
    return true;
  }
  if (!isInTicketArea(interaction)) {
    await interaction.reply({ content: 'Use the designated ticket channel to open tickets.', flags: 1 << 6 });
    return true;
  }

  const selected = interaction.values?.[0] || 'Support';
  const modal = new ModalBuilder().setCustomId(`ticket-modal:${selected}`).setTitle(`New Ticket (${selected})`);
  const description = new TextInputBuilder()
    .setCustomId('ticket_description')
    .setLabel('Describe your request')
    .setStyle(TextInputStyle.Paragraph)
    .setRequired(true)
    .setMaxLength(1000);

  modal.addComponents(new ActionRowBuilder().addComponents(description));
  await interaction.showModal(modal);
  return true;
}

export async function handleTicketModal(interaction, client) {
  if (!interaction.customId.startsWith('ticket-modal')) return false;
  if (!interaction.guild) {
    await interaction.reply({ content: 'Please use this inside a server.', flags: 1 << 6 });
    return true;
  }
  if (interaction.guild.id !== ALLOWED_GUILD_ID) {
    await interaction.reply({ content: 'Ticket system is only available in the main server.', flags: 1 << 6 });
    return true;
  }
  if (!isInTicketArea(interaction)) {
    await interaction.reply({ content: 'Tickets can only be opened in the designated channel.', flags: 1 << 6 });
    return true;
  }

  const categoryFromId = interaction.customId.split(':')[1] || 'Support';
  const categoryInput = categoryFromId || 'Support';
  const description = interaction.fields.getTextInputValue('ticket_description').trim() || 'No description provided';

  const { container } = await resolveTargetChannels(interaction.guild);
  if (!container) {
    await interaction.reply({ content: 'Ticket channel/category not found or invalid.', flags: 1 << 6 });
    return true;
  }

  const parentId =
    container.type === ChannelType.GuildCategory
      ? container.id
      : container.parentId || (container.isTextBased() ? container.id : null);
  if (!parentId) {
    await interaction.reply({ content: 'No valid ticket category/parent found.', flags: 1 << 6 });
    return true;
  }

  const openerId = interaction.user.id;
  const ownerId = interaction.guild.ownerId;
  const botId = client.user.id;

  const channelName = `ticket-${interaction.user.username}`.toLowerCase().replace(/\s+/g, '-').slice(0, 90);

  const ticketChannel = await interaction.guild.channels.create({
    name: channelName,
    type: ChannelType.GuildText,
    parent: parentId,
    reason: `Ticket by ${interaction.user.tag} - ${categoryInput}`,
    permissionOverwrites: [
      {
        id: interaction.guild.roles.everyone.id,
        deny: [PermissionFlagsBits.ViewChannel]
      },
      {
        id: openerId,
        allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages, PermissionFlagsBits.ReadMessageHistory]
      },
      {
        id: TICKET_PING_ROLE_ID,
        allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages, PermissionFlagsBits.ReadMessageHistory]
      },
      {
        id: ownerId,
        allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages, PermissionFlagsBits.ReadMessageHistory]
      },
      {
        id: botId,
        allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages, PermissionFlagsBits.ReadMessageHistory]
      }
    ]
  });

  const pingRole = `<@&${TICKET_PING_ROLE_ID}>`;
  const embed = new EmbedBuilder()
    .setTitle('New Ticket')
    .setColor(EMBED_COLOR)
    .addFields(
      { name: 'From', value: `${interaction.user} (${interaction.user.tag})`, inline: true },
      { name: 'Category', value: categoryInput, inline: true },
      { name: 'Description', value: description.slice(0, 1024), inline: false }
    )
    .setTimestamp(new Date());

  await ticketChannel.send({ content: `${pingRole} ${interaction.user}`, embeds: [embed] });
  await interaction.reply({ content: `Ticket created: ${ticketChannel}`, flags: 1 << 6 });
  return true;
}

function isInTicketArea(interaction) {
  const channel = interaction.channel;
  if (!channel) return false;
  if (channel.id === TICKET_PARENT_CHANNEL_ID) return true;
  return channel.parentId === TICKET_PARENT_CHANNEL_ID;
}

async function resolveTargetChannels(guild) {
  const container = await guild.channels.fetch(TICKET_PARENT_CHANNEL_ID).catch(() => null);
  if (!container) return { container: null, panelChannel: null };

  if (container.isTextBased() && container.type !== ChannelType.GuildCategory) {
    return { container, panelChannel: container };
  }

  if (container.type === ChannelType.GuildCategory) {
    const children = await guild.channels.fetch();
    let panelChannel = null;
    children.forEach(ch => {
      if (panelChannel) return;
      if (ch?.parentId === container.id && ch.isTextBased() && ch.type !== ChannelType.GuildCategory) {
        panelChannel = ch;
      }
    });
    if (panelChannel) return { container, panelChannel };

    const created = await guild.channels.create({
      name: 'ticket-panel',
      type: ChannelType.GuildText,
      parent: container.id,
      reason: 'Ticket panel channel auto-created'
    });
    return { container, panelChannel: created };
  }

  return { container: null, panelChannel: null };
}
