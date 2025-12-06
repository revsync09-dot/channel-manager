import Tesseract from 'tesseract.js';
import Jimp from 'jimp';

// Very simple OCR helper: load image, clean it a bit, read text, build a loose template.
export async function analyzeImageStub(imageUrl) {
  try {
    const buffer = await fetchImage(imageUrl);
    const cleaned = await preprocessImage(buffer);
    const text = await runOcr(cleaned);
    const template = buildTemplateFromText(text);
    let channelTotal = 0;
    for (const cat of template.categories) {
      channelTotal += cat.channels ? cat.channels.length : 0;
    }
    template.summary = `${template.categories.length} categories / ${channelTotal} channels (OCR)`;
    return template;
  } catch (err) {
    console.error('OCR failed, using fallback:', err.message);
    return fallbackTemplate();
  }
}

async function fetchImage(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Could not load image (${res.status})`);
  }
  const arrayBuffer = await res.arrayBuffer();
  return Buffer.from(arrayBuffer);
}

async function preprocessImage(buffer) {
  const img = await Jimp.read(buffer);
  if (img.getWidth() > 1400) {
    img.resize(1400, Jimp.AUTO);
  }
  img.grayscale();
  img.contrast(0.3);
  img.normalize();
  return img.getBufferAsync(Jimp.MIME_PNG);
}

async function runOcr(buffer) {
  const worker = await Tesseract.createWorker('eng', 1, { logger: () => {} });
  const { data } = await worker.recognize(buffer);
  await worker.terminate();
  return data.text || '';
}

function buildTemplateFromText(rawText) {
  const lines = rawText
    .split(/\r?\n/)
    .map(line => cleanLine(line))
    .filter(Boolean);

  const template = { categories: [] };
  let currentCategory = null;

  for (const line of lines) {
    if (looksLikeCategory(line)) {
      currentCategory = { name: normalizeName(line), channels: [] };
      template.categories.push(currentCategory);
      continue;
    }

    if (looksLikeChannel(line)) {
      if (!currentCategory) {
        currentCategory = { name: 'general', channels: [] };
        template.categories.push(currentCategory);
      }
      currentCategory.channels.push(parseChannel(line));
    }
  }

  if (!template.categories.length) {
    return fallbackTemplate();
  }
  return template;
}

function looksLikeChannel(line) {
  const lower = line.toLowerCase();
  return lower.startsWith('#') || lower.includes(' #') || lower.includes('voice') || lower.startsWith('- #');
}

function looksLikeCategory(line) {
  const lower = line.toLowerCase();
  if (!lower) return false;
  if (looksLikeChannel(line)) return false;
  return lower.length < 80;
}

function parseChannel(line) {
  const lower = line.toLowerCase();
  const isVoice = lower.includes('voice');
  const stripped = line.replace(/^[-\s]*/, '').replace(/^#+\s*/, '');
  const name = normalizeName(stripped);
  return {
    name,
    type: isVoice ? 'voice' : 'text',
    topic: suggestDescription(name, isVoice),
    private: false
  };
}

function cleanLine(str) {
  if (!str) return '';
  return str.replace(/\s{2,}/g, ' ').trim();
}

function normalizeName(str) {
  const trimmed = (str || '').trim();
  if (!trimmed) return 'channel';
  return trimmed.replace(/\s+/g, '-').toLowerCase();
}

function suggestDescription(name, isVoice) {
  const lower = name.toLowerCase();
  if (lower.includes('welcome')) return 'Welcome channel with info.';
  if (lower.includes('rules')) return 'Server rules.';
  if (lower.includes('announce')) return 'Announcements.';
  if (isVoice) return 'Simple voice channel.';
  return 'Auto description from OCR.';
}

function fallbackTemplate() {
  return {
    categories: [
      {
        name: 'from-image',
        channels: [
          { name: 'welcome', type: 'text', topic: 'Welcome channel with info.', private: false },
          { name: 'rules', type: 'text', topic: 'Server rules.', private: false },
          { name: 'hangout', type: 'voice', topic: 'Simple voice channel.', private: false }
        ]
      }
    ],
    summary: 'Fallback template from image'
  };
}
