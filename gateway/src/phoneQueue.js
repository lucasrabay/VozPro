const queues = new Map();
const TIMEOUT_MS = 60_000;

export function enqueue(phone, task) {
  const previous = queues.get(phone) || Promise.resolve();
  const ctrl = new AbortController();
  const current = previous
    .catch(() => {})
    .then(() => withTimeout(task(ctrl.signal), TIMEOUT_MS, ctrl));
  queues.set(
    phone,
    current.finally(() => {
      if (queues.get(phone) === current) queues.delete(phone);
    })
  );
  return current;
}

function withTimeout(promise, ms, ctrl) {
  const timer = setTimeout(
    () => ctrl.abort(new Error(`phone queue timeout after ${ms}ms`)),
    ms
  );
  const timeout = new Promise((_, reject) => {
    ctrl.signal.addEventListener('abort', () => reject(ctrl.signal.reason));
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}
