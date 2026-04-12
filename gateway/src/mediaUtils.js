const FORGET_REGEX = /\b(apagar?|apaga|delete?r?)\s+(meus\s+)?(dados|informa[çc][õo]es)\b/i;

export function isForgetCommand(text) {
  if (!text) return false;
  const normalized = text.trim().toLowerCase();
  return FORGET_REGEX.test(normalized);
}

export function classifyMessage(msg) {
  if (msg.type === 'chat') return 'text';
  if (msg.type === 'ptt' || msg.type === 'audio') return 'audio';
  return 'unsupported';
}

export function unsupportedReply() {
  return 'Oi! Por enquanto eu só entendo áudio ou texto. Manda assim que eu te ajudo!';
}

export function errorReply() {
  return 'Tô com um problema aqui agora, tenta daqui a uns minutinhos?';
}
