from collections import OrderedDict


def _check_capacity(capacity: int) -> None:
    if not isinstance(capacity, int) or capacity < 1:
        raise ValueError("capacity must be a positive integer")


class LruCache[K, V]:
    def __init__(self, capacity: int) -> None:
        _check_capacity(capacity)
        self._capacity = capacity
        self._entries: OrderedDict[K, V] = OrderedDict()

    @property
    def size(self) -> int:
        return len(self._entries)

    def get(self, key: K) -> V | None:
        if key not in self._entries:
            return None
        self._entries.move_to_end(key)
        return self._entries[key]

    def put(self, key: K, value: V) -> None:
        self._entries[key] = value
        self._entries.move_to_end(key)
        if len(self._entries) > self._capacity:
            self._entries.popitem(last=False)

    def keys(self) -> list[K]:
        return list(self._entries)


class _Node[K, V]:
    __slots__ = ("key", "value", "prev", "next")

    def __init__(self, key: K | None = None, value: V | None = None) -> None:
        self.key = key
        self.value = value
        self.prev: _Node[K, V] | None = None
        self.next: _Node[K, V] | None = None


class LinkedLruCache[K, V]:
    def __init__(self, capacity: int) -> None:
        _check_capacity(capacity)
        self._capacity = capacity
        self._by_key: dict[K, _Node[K, V]] = {}
        self._head: _Node[K, V] = _Node()
        self._tail: _Node[K, V] = _Node()
        self._head.next = self._tail
        self._tail.prev = self._head

    @property
    def size(self) -> int:
        return len(self._by_key)

    def get(self, key: K) -> V | None:
        node = self._by_key.get(key)
        if node is None:
            return None
        self._unlink(node)
        self._push_front(node)
        return node.value

    def put(self, key: K, value: V) -> None:
        node = self._by_key.get(key)
        if node is not None:
            node.value = value
            self._unlink(node)
            self._push_front(node)
            return
        if len(self._by_key) == self._capacity:
            lru = self._tail.prev
            self._unlink(lru)
            del self._by_key[lru.key]
        node = _Node(key, value)
        self._by_key[key] = node
        self._push_front(node)

    def keys(self) -> list[K]:
        keys: list[K] = []
        node = self._tail.prev
        while node is not self._head:
            keys.append(node.key)
            node = node.prev
        return keys

    def _unlink(self, node: _Node[K, V]) -> None:
        node.prev.next = node.next
        node.next.prev = node.prev

    def _push_front(self, node: _Node[K, V]) -> None:
        node.prev = self._head
        node.next = self._head.next
        self._head.next.prev = node
        self._head.next = node
