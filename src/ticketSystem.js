import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  EmbedBuilder,
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
  ChannelType,
  PermissionFlagsBits
} from 'discord.js';

const TICKET_PARENT_CHANNEL_ID = '1447010961939501242';
const TICKET_PING_ROLE_ID = '1447006097704484915';
const EMBED_COLOR = 0x22c55e;

const CATEGORY_HINT = 'Support | Bug Report | Other';

export async function sendTicketPanel(interaction) {
  if (!interaction.guild || interaction.channelId !== TICKET_PARENT_CHANNEL_ID) {
    return interaction.reply({
      content: 'Ticket panel kann nur im vorgesehenen Ticket-Channel erstellt werden.',
      flags: 1 << 6
    });
  }

  const embed = new EmbedBuilder()
    .setTitle('Ticket Support')
    .setColor(EMBED_COLOR)
    .setDescription(
      [
        'Öffne ein Ticket und schildere dein Anliegen.',
        '- Kategorien: Support, Bug Report, Billing, Other',
        '- Unser Team meldet sich so schnell wie möglich.'
      ].join('\n')
    );

  const row = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('ticket-open').setStyle(ButtonStyle.Primary).setLabel('🎫 Ticket öffnen')
  );

  return interaction.reply({ embeds: [embed], components: [row] });
}

export async function handleTicketButton(interaction) {
  if (interaction.customId !== 'ticket-open') return false;
  if (!interaction.guild || interaction.channelId !== TICKET_PARENT_CHANNEL_ID) {
    await interaction.reply({ content: 'Tickets können nur im vorgesehenen Channel eröffnet werden.', flags: 1 << 6 });
    return true;
  }

  const modal = new ModalBuilder().setCustomId('ticket-modal').setTitle('Neues Ticket');
  const category = new TextInputBuilder()
    .setCustomId('ticket_category')
    .setLabel(`Kategorie (${CATEGORY_HINT})`)
    .setStyle(TextInputStyle.Short)
    .setRequired(true)
    .setMaxLength(50);
  const description = new TextInputBuilder()
    .setCustomId('ticket_description')
    .setLabel('Kurzbeschreibung')
    .setStyle(TextInputStyle.Paragraph)
    .setRequired(true)
    .setMaxLength(1000);

  modal.addComponents(
    new ActionRowBuilder().addComponents(category),
    new ActionRowBuilder().addComponents(description)
  );
  await interaction.showModal(modal);
  return true;
}

export async function handleTicketModal(interaction, client) {
  if (interaction.customId !== 'ticket-modal') return false;
  if (!interaction.guild) {
    await interaction.reply({ content: 'Bitte in einem Server verwenden.', flags: 1 << 6 });
    return true;
  }
  if (interaction.channelId !== TICKET_PARENT_CHANNEL_ID) {
    await interaction.reply({ content: 'Tickets können nur im vorgesehenen Channel eröffnet werden.', flags: 1 << 6 });
    return true;
  }

  const categoryInput = interaction.fields.getTextInputValue('ticket_category').trim() || 'Support';
  const description = interaction.fields.getTextInputValue('ticket_description').trim() || 'Keine Beschreibung';

  const parentChannel = await interaction.guild.channels.fetch(TICKET_PARENT_CHANNEL_ID).catch(() => null);
  if (!parentChannel) {
    await interaction.reply({ content: 'Ticket-Channel/Category nicht gefunden oder ungültig.', flags: 1 << 6 });
    return true;
  }

  const parentId =
    parentChannel.type === ChannelType.GuildCategory
      ? parentChannel.id
      : parentChannel.parentId || (parentChannel.type === ChannelType.GuildText ? parentChannel.id : null);
  if (!parentId) {
    await interaction.reply({ content: 'Kein gültiger Ticket-Category/Parent gefunden.', flags: 1 << 6 });
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
    reason: `Ticket von ${interaction.user.tag} - ${categoryInput}`,
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
    .setTitle('Neues Ticket')
    .setColor(EMBED_COLOR)
    .addFields(
      { name: 'Von', value: `${interaction.user} (${interaction.user.tag})`, inline: true },
      { name: 'Kategorie', value: categoryInput, inline: true },
      { name: 'Beschreibung', value: description.slice(0, 1024), inline: false }
    )
    .setTimestamp(new Date());

  await ticketChannel.send({ content: `${pingRole} ${interaction.user}`, embeds: [embed] });
  await interaction.reply({ content: `Ticket erstellt: ${ticketChannel}`, flags: 1 << 6 });
  return true;
}
