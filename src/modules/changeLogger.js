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
        return acc;
      },
      { add: 0, change: 0, unlink: 0, ext: {} }
    );

    const total = counts.add + counts.change + counts.unlink;
    const actions = [];
    if (counts.add) actions.push(`${counts.add} new item${counts.add === 1 ? '' : 's'} added`);
    if (counts.change) actions.push(`${counts.change} item${counts.change === 1 ? '' : 's'} updated`);
    if (counts.unlink) actions.push(`${counts.unlink} item${counts.unlink === 1 ? '' : 's'} removed`);

    const topExts = Object.entries(counts.ext)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([ext, num]) => {
        const label = TYPE_LABELS[ext] || ext;
        return `${label}: ${num}`;
      })
      .join(', ');

    const sentenceParts = [];
    sentenceParts.push(total ? `Workspace touched ${total} item${total === 1 ? '' : 's'}.` : 'No recent changes logged.');
    if (actions.length) sentenceParts.push(actions.join(', ') + '.');
    if (topExts) sentenceParts.push(`Highlights: ${topExts}.`);

    const description = sentenceParts.join(' ');

    return { counts, description };
  };

  const flush = async () => {
    timer = null;
    if (!queue.length) return;
    const events = queue;
    queue = [];

    const channel = await client.channels.fetch(LOG_CHANNEL_ID).catch(() => null);
    if (!channel || !channel.isTextBased()) return;

    const { counts, description } = summarize(events);

    const embed = new EmbedBuilder()
      .setTitle('Workspace update')
      .setColor(EMBED_COLOR)
      .setDescription(description)
      .addFields(
        { name: 'Added', value: String(counts.add || 0), inline: true },
        { name: 'Updated', value: String(counts.change || 0), inline: true },
        { name: 'Removed', value: String(counts.unlink || 0), inline: true }
      )
      .setFooter({ text: 'Auto change log' })
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
