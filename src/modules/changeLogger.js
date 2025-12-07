import chokidar from 'chokidar';
import path from 'path';
import { EmbedBuilder } from 'discord.js';

const LOG_CHANNEL_ID = '1447010974652694750';
const EMBED_COLOR = 0x22c55e;
const DEBOUNCE_MS = 7000;
const TYPE_LABELS = {
  js: 'Code updates',
  ts: 'Code updates',
  json: 'Config changes',
  config: 'Config changes',
  docs: 'Docs/content',
  misc: 'Other work'
};

export function startChangeLogger(client, rootDir = process.cwd()) {
  const watcher = chokidar.watch(rootDir, {
    ignored: [
      /(^|[\\/])\../,
      '**/node_modules/**',
      '**/.git/**',
      '**/package-lock.json',
      '**/yarn.lock',
      '**/pnpm-lock.yaml',
      '**/logs/**'
    ],
    ignoreInitial: true,
    persistent: true,
    depth: 6
  });

  let queue = [];
  let timer = null;

  const summarize = events => {
    const counts = events.reduce(
      (acc, e) => {
        acc[e.type] = (acc[e.type] || 0) + 1;
        const ext = normalizeExt(e.file);
        acc.ext[ext] = (acc.ext[ext] || 0) + 1;
        acc.files[e.type].push(e.file);
        return acc;
      },
      { add: 0, change: 0, unlink: 0, ext: {}, files: { add: [], change: [], unlink: [] } }
    );

    const total = counts.add + counts.change + counts.unlink;
    const actions = [];
    if (counts.add) actions.push(`added ${counts.add}`);
    if (counts.change) actions.push(`updated ${counts.change}`);
    if (counts.unlink) actions.push(`removed ${counts.unlink}`);

    const topExts = Object.entries(counts.ext)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([ext, num]) => {
        const label = TYPE_LABELS[ext] || ext;
        return `${label}: ${num}`;
      })
      .join(', ');

    const headline = total
      ? `Workspace touched ${total} item${total === 1 ? '' : 's'} (${actions.join(', ')}).`
      : 'No recent changes logged.';

    return { counts, headline, topExts, files: counts.files };
  };

  const flush = async () => {
    timer = null;
    if (!queue.length) return;
    const events = queue;
    queue = [];

    const channel = await client.channels.fetch(LOG_CHANNEL_ID).catch(() => null);
    if (!channel || !channel.isTextBased()) return;

    const { counts, headline, topExts, files } = summarize(events);

    const formatList = arr => {
      if (!arr.length) return '—';
      const sliced = arr.slice(0, 8);
      const more = arr.length > 8 ? `\n… +${arr.length - 8} more` : '';
      return sliced.map(f => `• \`${f}\``).join('\n') + more;
    };

    const fields = [
      { name: '🟢 Added', value: formatList(files.add), inline: false },
      { name: '🟠 Updated', value: formatList(files.change), inline: false },
      { name: '🔴 Removed', value: formatList(files.unlink), inline: false }
    ];

    const embed = new EmbedBuilder()
      .setTitle('🛰️ Workspace Update')
      .setColor(EMBED_COLOR)
      .setDescription([headline, topExts ? `Highlights: ${topExts}.` : null].filter(Boolean).join('\n'))
      .addFields(fields)
      .setFooter({ text: 'Automated change log • Channel Manager' })
      .setTimestamp(new Date());

    await channel.send({ embeds: [embed] }).catch(() => null);
  };

  const enqueue = (type, filePath) => {
    const rel = path.relative(rootDir, filePath);
    if (!rel || rel.startsWith('..')) return;
    queue.push({ type, file: rel.replace(/\\/g, '/') });
    if (!timer) {
      timer = setTimeout(flush, DEBOUNCE_MS);
    }
  };

  watcher
    .on('add', fp => enqueue('add', fp))
    .on('change', fp => enqueue('change', fp))
    .on('unlink', fp => enqueue('unlink', fp))
    .on('addDir', fp => enqueue('add', fp))
    .on('unlinkDir', fp => enqueue('unlink', fp))
    .on('error', () => {});

  return watcher;
}

function normalizeExt(filePath) {
  const ext = path.extname(filePath).replace('.', '').toLowerCase();
  if (!ext) return 'misc';
  if (['js', 'cjs', 'mjs'].includes(ext)) return 'js';
  if (['ts', 'mts', 'cts'].includes(ext)) return 'ts';
  if (['json'].includes(ext)) return 'json';
  if (['md', 'markdown'].includes(ext)) return 'docs';
  if (['yml', 'yaml'].includes(ext)) return 'config';
  return ext;
}
