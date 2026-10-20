from __future__ import annotations

from agent.audit import AuditLog
from promptreg.models import PromptRef


def record_prompt_ref(audit: AuditLog, ref: PromptRef) -> None:
    audit.record("prompt_resolved", name=ref.name, version=ref.version, sha256=ref.sha256, reason=ref.reason)
