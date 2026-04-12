const BRAIN_URL = process.env.BRAIN_URL || 'http://brain:8000';

export async function sendMessageToBrain({ phone, kind, content, mime }) {
  const res = await fetch(`${BRAIN_URL}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone, kind, content, mime: mime || null }),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`brain /message ${res.status}: ${body}`);
  }
  return res.json();
}

export async function forgetAtBrain(phone) {
  const res = await fetch(`${BRAIN_URL}/forget`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone }),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`brain /forget ${res.status}: ${body}`);
  }
  return res.json();
}
