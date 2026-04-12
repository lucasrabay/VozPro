import { enqueue } from './phoneQueue.js';
import { sendMessageToBrain, forgetAtBrain } from './brainClient.js';
import {
  classifyMessage,
  isForgetCommand,
  unsupportedReply,
  errorReply,
} from './mediaUtils.js';

const PDF_DIR = process.env.PDF_DIR || '/app/pdfs';

export async function handleMessage(client, msg, MessageMedia) {
  if (msg.fromMe) return;
  if (msg.isStatus) return;

  const phone = msg.from;

  await enqueue(phone, async () => {
    const kind = classifyMessage(msg);

    if (kind === 'text' && isForgetCommand(msg.body)) {
      try {
        await forgetAtBrain(phone);
        await client.sendMessage(
          phone,
          'Pronto! Apaguei tudo. Se quiser começar de novo, é só mandar um oi.'
        );
      } catch (err) {
        console.error('[handler] forget failed:', err);
        await client.sendMessage(phone, errorReply());
      }
      return;
    }

    if (kind === 'unsupported') {
      await client.sendMessage(phone, unsupportedReply());
      return;
    }

    let payload;
    try {
      if (kind === 'audio') {
        const media = await msg.downloadMedia();
        if (!media || !media.data) {
          await client.sendMessage(phone, unsupportedReply());
          return;
        }
        payload = {
          phone,
          kind: 'audio',
          content: media.data,
          mime: media.mimetype || 'audio/ogg',
        };
      } else {
        payload = {
          phone,
          kind: 'text',
          content: msg.body || '',
          mime: null,
        };
      }
    } catch (err) {
      console.error('[handler] media download failed:', err);
      await client.sendMessage(phone, errorReply());
      return;
    }

    let reply;
    try {
      reply = await sendMessageToBrain(payload);
    } catch (err) {
      console.error('[handler] brain call failed:', err);
      await client.sendMessage(phone, errorReply());
      return;
    }

    await sendReply(client, MessageMedia, phone, reply);
  });
}

async function sendReply(client, MessageMedia, phone, reply) {
  if (reply.audio_b64) {
    try {
      const audioMedia = new MessageMedia('audio/wav', reply.audio_b64, 'biu.wav');
      await client.sendMessage(phone, audioMedia, { sendAudioAsVoice: true });
    } catch (err) {
      console.error('[handler] send audio failed:', err);
    }
  }

  if (reply.pdf_path) {
    try {
      const pdfMedia = MessageMedia.fromFilePath(
        resolvePdfPath(reply.pdf_path)
      );
      await client.sendMessage(phone, pdfMedia, {
        caption: 'Seu currículo!',
        sendMediaAsDocument: true,
      });
    } catch (err) {
      console.error('[handler] send pdf failed:', err);
    }
  }

  if (reply.text && reply.type !== 'curriculo') {
    try {
      await client.sendMessage(phone, reply.text);
    } catch (err) {
      console.error('[handler] send text failed:', err);
    }
  }
}

function resolvePdfPath(brainPath) {
  const marker = '/data/pdfs/';
  const idx = brainPath.indexOf(marker);
  if (idx >= 0) {
    return PDF_DIR + brainPath.substring(idx + marker.length - 1);
  }
  const name = brainPath.split(/[\\/]/).pop();
  return `${PDF_DIR}/${name}`;
}
