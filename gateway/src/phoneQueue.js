const queues = new Map();
const TIMEOUT_MS = 60_000;

export function enqueue(phone, task) {
  const previous = queues.get(phone) || Promise.resolve();
  const current = previous.catch(() => {}).then(() => withTimeout(task(), TIMEOUT_MS));
  queues.set(
    phone,
    current.finally(() => {
      if (queues.get(phone) === current) queues.delete(phone);
    })
  );
  return current;
}

function withTimeout(promise, ms) {
  return Promise.race([
    promise,
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error(`phone queue timeout after ${ms}ms`)), ms)
    ),
  ]);
}
