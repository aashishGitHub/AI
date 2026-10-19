function assertCapacity(capacity: number): void {
  if (!Number.isInteger(capacity) || capacity < 1) throw new RangeError('capacity must be a positive integer');
}

export class LruCache<K, V> {
  readonly #entries = new Map<K, V>();
  readonly #capacity: number;

  constructor(capacity: number) {
    assertCapacity(capacity);
    this.#capacity = capacity;
  }

  get size(): number {
    return this.#entries.size;
  }

  get(key: K): V | undefined {
    const value = this.#entries.get(key);
    if (value === undefined) return undefined;
    this.#entries.delete(key);
    this.#entries.set(key, value);
    return value;
  }

  put(key: K, value: V): void {
    this.#entries.delete(key);
    this.#entries.set(key, value);
    if (this.#entries.size > this.#capacity) {
      const oldest = this.#entries.keys().next();
      if (!oldest.done) this.#entries.delete(oldest.value);
    }
  }

  keys(): K[] {
    return [...this.#entries.keys()];
  }
}

interface Links {
  prev: Links | undefined;
  next: Links | undefined;
}

interface Entry<K, V> extends Links {
  readonly key: K;
  value: V;
}

export class LinkedLruCache<K, V> {
  readonly #byKey = new Map<K, Entry<K, V>>();
  readonly #head: Links = { prev: undefined, next: undefined };
  readonly #tail: Links = { prev: undefined, next: undefined };
  readonly #capacity: number;

  constructor(capacity: number) {
    assertCapacity(capacity);
    this.#capacity = capacity;
    this.#head.next = this.#tail;
    this.#tail.prev = this.#head;
  }

  get size(): number {
    return this.#byKey.size;
  }

  get(key: K): V | undefined {
    const entry = this.#byKey.get(key);
    if (entry === undefined) return undefined;
    this.#unlink(entry);
    this.#pushFront(entry);
    return entry.value;
  }

  put(key: K, value: V): void {
    const existing = this.#byKey.get(key);
    if (existing !== undefined) {
      existing.value = value;
      this.#unlink(existing);
      this.#pushFront(existing);
      return;
    }
    if (this.#byKey.size === this.#capacity) {
      const lru = this.#tail.prev as Entry<K, V>;
      this.#unlink(lru);
      this.#byKey.delete(lru.key);
    }
    const entry: Entry<K, V> = { key, value, prev: undefined, next: undefined };
    this.#byKey.set(key, entry);
    this.#pushFront(entry);
  }

  keys(): K[] {
    const keys: K[] = [];
    for (let node = this.#tail.prev; node !== this.#head; node = node!.prev) keys.push((node as Entry<K, V>).key);
    return keys;
  }

  #unlink(node: Links): void {
    node.prev!.next = node.next;
    node.next!.prev = node.prev;
  }

  #pushFront(node: Links): void {
    node.prev = this.#head;
    node.next = this.#head.next;
    this.#head.next!.prev = node;
    this.#head.next = node;
  }
}
