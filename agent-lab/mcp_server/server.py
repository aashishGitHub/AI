from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from mcp_server import descriptions, views
from mcp_server.store import FixtureStore
from mcp_server.validation import InvalidToolInput

log = logging.getLogger("mcp_server")

INTERNAL_ERROR = "internal error: the tool failed; see the server log on stderr"

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

TenantId = Annotated[str, Field(description=descriptions.TENANT_ID)]
TitleId = Annotated[str | None, Field(description=descriptions.TITLE_ID)]
AlertId = Annotated[str, Field(description=descriptions.ALERT_ID)]
IssueKey = Annotated[str, Field(description=descriptions.ISSUE_KEY)]
Note = Annotated[str | None, Field(description=descriptions.NOTE)]


def _text_result(text: str, *, is_error: bool, structured: dict[str, Any] | None = None) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text)], structured_content=structured, is_error=is_error
    )


def _run(tool: str, body: Callable[[], dict[str, Any]]) -> CallToolResult:
    # Never raises: an exception's text may carry backend or tenant data that must not reach a model.
    try:
        view = body()
        return _text_result(json.dumps(view), is_error=False, structured=view)
    except InvalidToolInput as exc:
        return _text_result(str(exc), is_error=True)
    except Exception as exc:
        log.error("%s: unexpected %s", tool, type(exc).__name__)
        return _text_result(INTERNAL_ERROR, is_error=True)


def build_server(store: FixtureStore) -> MCPServer:
    server = MCPServer("streampulse-py")

    @server.tool(name="get_live_metrics", title="Live metrics", description=descriptions.GET_LIVE_METRICS, annotations=READ_ONLY)
    def get_live_metrics(tenantId: TenantId, titleId: TitleId = None) -> CallToolResult:
        return _run("get_live_metrics", lambda: views.get_live_metrics(store, tenantId, titleId))

    @server.tool(name="list_active_alerts", title="Active alerts", description=descriptions.LIST_ACTIVE_ALERTS, annotations=READ_ONLY)
    def list_active_alerts(tenantId: TenantId) -> CallToolResult:
        return _run("list_active_alerts", lambda: views.list_active_alerts(store, tenantId))

    @server.tool(name="explain_alert", title="Explain an alert", description=descriptions.EXPLAIN_ALERT, annotations=READ_ONLY)
    def explain_alert(tenantId: TenantId, alertId: AlertId) -> CallToolResult:
        return _run("explain_alert", lambda: views.explain_alert(store, tenantId, alertId))

    @server.tool(name="acknowledge_alert", title="Acknowledge an alert", description=descriptions.ACKNOWLEDGE_ALERT, annotations=WRITE)
    def acknowledge_alert(tenantId: TenantId, alertId: AlertId, note: Note = None) -> CallToolResult:
        return _run("acknowledge_alert", lambda: views.acknowledge_alert(store, tenantId, alertId, note))

    @server.tool(name="link_issue", title="Link an issue", description=descriptions.LINK_ISSUE, annotations=WRITE)
    def link_issue(tenantId: TenantId, alertId: AlertId, issueKey: IssueKey) -> CallToolResult:
        return _run("link_issue", lambda: views.link_issue(store, tenantId, alertId, issueKey))

    return server
