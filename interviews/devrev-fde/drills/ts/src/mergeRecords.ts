export function mergeLatest<T>(
  records: Iterable<T>,
  key: (record: T) => string,
  version: (record: T) => number,
): T[] {
  const winners = new Map<string, T>();
  for (const record of records) {
    const k = key(record);
    const current = winners.get(k);
    if (current === undefined || version(record) >= version(current)) winners.set(k, record);
  }
  return [...winners.values()];
}
