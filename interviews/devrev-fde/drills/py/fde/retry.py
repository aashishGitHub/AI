import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.utils import parsedate_to_datetime


class HttpError(Exception):
    def __init__(self, status: int, headers: Mapping[str, str] | None = None) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status
        self.headers = {name.lower(): value for name, value in (headers or {}).items()}


class NetworkError(Exception):
    pass


@dataclass(frozen=True)
class RetryOptions:
    method: str
    max_attempts: int
    base_ms: int
    cap_ms: int
    sleep: Callable[[int], None]
    rng: Callable[[], float]
    now_ms: Callable[[], int]
    idempotency_key: str | None = None


_IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE", "PUT", "DELETE"}
_IMF_FIXDATE = re.compile(r"[A-Za-z]{3}, [0-9]{2} [A-Za-z]{3} [0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2} GMT")


def parse_retry_after(value: str | None, now_ms: int) -> int | None:
    if value is None:
        return None
    if re.fullmatch(r"[0-9]{1,9}", value):
        return int(value) * 1000
    if not _IMF_FIXDATE.fullmatch(value):
        return None
    try:
        at = parsedate_to_datetime(value)
    except ValueError:
        return None
    return max(0, int(at.timestamp()) * 1000 - now_ms)


def _is_retryable(err: Exception) -> bool:
    if isinstance(err, NetworkError):
        return True
    return isinstance(err, HttpError) and (err.status == 429 or 500 <= err.status <= 599)


def retry[T](op: Callable[[int], T], o: RetryOptions) -> T:
    safe_to_repeat = o.method.upper() in _IDEMPOTENT_METHODS or o.idempotency_key is not None

    attempt = 1
    while True:
        try:
            return op(attempt)
        except Exception as err:
            if not safe_to_repeat or not _is_retryable(err) or attempt >= o.max_attempts:
                raise

            ceiling = min(o.cap_ms, o.base_ms * 2 ** (attempt - 1))
            jittered = int(o.rng() * ceiling)
            hinted = 0
            if isinstance(err, HttpError):
                hinted = parse_retry_after(err.headers.get("retry-after"), o.now_ms()) or 0
            o.sleep(max(jittered, hinted))
            attempt += 1
