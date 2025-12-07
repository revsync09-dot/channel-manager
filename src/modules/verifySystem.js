import { ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, PermissionsBitField } from 'discord.js';

const VERIFY_ROLE_ID = process.env.VERIFY_ROLE_ID || '1446990501331861577';
const VERIFY_CHANNEL_ID = process.env.VERIFY_CHANNEL_ID || '';
const EMBED_COLOR = 0x22c55e;

export function getVerifyRoleId() {
  return VERIFY_ROLE_ID;
}

export async function sendVerifyPanel(interaction) {
  if (!interaction.guild) {
    return interaction.reply({ content: 'Use this inside a server.', flags: 1 << 6 });
  }

  if (VERIFY_ROLE_ID === 'SET_VERIFY_ROLE_ID') {
    return interaction.reply({ content: 'Verification role not configured (VERIFY_ROLE_ID).', flags: 1 << 6 });
  }

  const embed = new EmbedBuilder()
    .setTitle('🔒 Verify to Access')
    .setColor(EMBED_COLOR)
    .setDescription('Click verify to unlock chat access. This helps keep the server safe from bots and spam.')
    .setFooter({ text: 'Channel Manager Verification' });

  const row = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('verify-accept').setStyle(ButtonStyle.Success).setLabel('✅ Verify')
  );

  await interaction.reply({ embeds: [embed], components: [row] });
}

export async function sendVerifyPanelToChannel(client) {
  if (!VERIFY_CHANNEL_ID) return;
  const channel = await client.channels.fetch(VERIFY_CHANNEL_ID).catch(() => null);
  if (!channel || !channel.isTextBased()) return;

  const embed = new EmbedBuilder()
    .setTitle('🔒 Verify to Access')
    .setColor(EMBED_COLOR)
    .setDescription('Click verify to unlock chat access. This keeps the server safe from spam.')
    .setFooter({ text: 'Channel Manager Verification' })
    .setTimestamp(new Date());

  const row = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('verify-accept').setStyle(ButtonStyle.Success).setLabel('✅ Verify')
  );

  await channel.send({ embeds: [embed], components: [row] }).catch(() => {});
}

export async function handleVerifyButton(interaction) {
  if (interaction.customId !== 'verify-accept') return false;
  if (!interaction.guild) {
    await interaction.reply({ content: 'This button works only in a server.', flags: 1 << 6 });
    return true;
  }

  if (VERIFY_ROLE_ID === 'SET_VERIFY_ROLE_ID') {
    await interaction.reply({ content: 'Verification role not configured (VERIFY_ROLE_ID).', flags: 1 << 6 });
    return true;
  }

  const member = interaction.member;
  if (!member || !member.manageable) {
    await interaction.reply({ content: 'Cannot verify this user here.', flags: 1 << 6 });
    return true;
  }

  const role = await interaction.guild.roles.fetch(VERIFY_ROLE_ID).catch(() => null);
  if (!role) {
    await interaction.reply({ content: 'Verification role not found.', flags: 1 << 6 });
    return true;
  }

  if (member.roles.cache.has(role.id)) {
    await interaction.reply({ content: 'You are already verified.', flags: 1 << 6 });
    return true;
  }

  const botMember = interaction.guild.members.me;
  if (!botMember?.permissions.has(PermissionsBitField.Flags.ManageRoles) || botMember.roles.highest.position <= role.position) {
    await interaction.reply({ content: 'Bot is missing Manage Roles or role hierarchy is too low.', flags: 1 << 6 });
    return true;
  }

  await member.roles.add(role, 'User verified via verify button').catch(() => {});
  await interaction.reply({ content: 'Verification successful. Welcome!', flags: 1 << 6 });
  return true;
}
