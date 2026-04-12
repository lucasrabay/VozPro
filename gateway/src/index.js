import pkg from 'whatsapp-web.js';
const { Client, LocalAuth, MessageMedia } = pkg;
import qrcode from 'qrcode-terminal';
import { rmSync } from 'fs';
import { handleMessage } from './handler.js';

const PUPPETEER_EXECUTABLE_PATH = process.env.PUPPETEER_EXECUTABLE_PATH || undefined;

for (const f of ['SingletonLock', 'SingletonCookie', 'SingletonSocket']) {
  try { rmSync(`/app/.wwebjs_auth/session/${f}`); } catch {}
}

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: '/app/.wwebjs_auth' }),
  puppeteer: {
    headless: true,
    executablePath: PUPPETEER_EXECUTABLE_PATH,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-accelerated-2d-canvas',
      '--no-first-run',
      '--no-zygote',
      '--disable-gpu',
    ],
  },
});

client.on('qr', (qr) => {
  console.log('[gateway] scan this QR code with the WhatsApp app:');
  qrcode.generate(qr, { small: true });
});

client.on('ready', () => {
  console.log('[gateway] ready — connected to WhatsApp');
});

client.on('authenticated', () => {
  console.log('[gateway] authenticated');
});

client.on('auth_failure', (msg) => {
  console.error('[gateway] auth failure:', msg);
});

client.on('disconnected', (reason) => {
  console.warn('[gateway] disconnected:', reason);
});

client.on('message', async (msg) => {
  try {
    await handleMessage(client, msg, MessageMedia);
  } catch (err) {
    console.error('[gateway] handler error:', err);
  }
});

client.initialize();

process.on('SIGINT', async () => {
  console.log('[gateway] shutting down...');
  await client.destroy();
  process.exit(0);
});
