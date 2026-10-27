from __future__ import annotations

from typing import Any

INVESTIGATOR_SCRIPT: list[dict[str, Any]] = [
    {"tool_calls": [{"name": "list_active_alerts", "arguments": {"tenantId": "streamflix"}}]},
    {"content": "alr-1001 is firing; alr-1002 is suppressed by it."},
]

TRIAGE_SCRIPT: list[dict[str, Any]] = [
    {"tool_calls": [{"name": "ask_investigator", "arguments": {"prompt": "List the active alerts for streamflix."}}]},
    {"content": "Root cause is alr-1001."},
]
