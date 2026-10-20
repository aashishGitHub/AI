from __future__ import annotations

from datetime import timedelta

from agent.loop import RunResult
from memory.records import DEFAULT_TTL, MemoryRecord, Provenance
from memory.store import MemoryStore


def summarize_run(result: RunResult, max_answer_chars: int = 300) -> str:
    tools = ", ".join(record.call.name for record in result.tool_records) or "none"
    answer = " ".join(result.final_text.split())[:max_answer_chars]
    return f"stop={result.stop_reason}; steps={result.steps}; tools={tools}; answer={answer}"


def record_run_summary(
    store: MemoryStore,
    tenant_id: str,
    run_id: str,
    result: RunResult,
    ttl: timedelta | None = DEFAULT_TTL["episodic"],
) -> MemoryRecord:
    provenance = Provenance(source="system:run_summary", run_id=run_id, written_by="system")
    return store.add(tenant_id, "episodic", summarize_run(result), provenance, ttl)
