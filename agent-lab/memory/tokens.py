from __future__ import annotations

import json
import math

from agent.types import Message

CHARS_PER_TOKEN = 4
MESSAGE_OVERHEAD_TOKENS = 4


def estimate_tokens(text: str) -> int:
    """APPROXIMATION: ceil(chars / 4). Real tokenizers differ per model, language and content (JSON, code)."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def message_tokens(message: Message) -> int:
    calls = sum(estimate_tokens(c.name + json.dumps(c.arguments, default=str)) for c in message.tool_calls)
    return MESSAGE_OVERHEAD_TOKENS + estimate_tokens(message.content) + calls
