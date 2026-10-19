from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from mcp_server.fixtures import ALERTS, NOW, SERIES, TENANTS, Alert, SeriesSample

LOOKBACK_MINUTES = 15
HISTORY_WINDOWS = 5
WINDOW = timedelta(minutes=1)


@dataclass(frozen=True)
class MetricWindow:
    title_id: str
    region: str
    metric: str
    window_start: datetime
    value: float
    sample_count: int

    @property
    def window_end(self) -> datetime:
        return self.window_start + WINDOW


class FixtureStore:
    def __init__(
        self,
        alerts: Sequence[Alert] = ALERTS,
        series: Sequence[SeriesSample] = SERIES,
        tenants: Sequence[str] = TENANTS,
        now: datetime = NOW,
        state_path: Path | None = None,
    ) -> None:
        self._alerts = tuple(alerts)
        self._series = tuple(series)
        self._tenants = frozenset(tenants)
        self.now = now
        self._state_path = state_path
        self._acknowledged: dict[str, dict[str, str]] = {}
        self._links: list[dict[str, str]] = []

    def knows_tenant(self, tenant_id: str) -> bool:
        return tenant_id in self._tenants

    def active_alerts(self, tenant_id: str) -> list[Alert]:
        return [a for a in self._alerts if a.tenant_id == tenant_id]

    def find_alert(self, tenant_id: str, alert_id: str) -> Alert | None:
        return next((a for a in self.active_alerts(tenant_id) if a.alert_id == alert_id), None)

    def is_acknowledged(self, alert_id: str) -> bool:
        return alert_id in self._acknowledged

    def live_windows(self, tenant_id: str, title_id: str | None) -> list[MetricWindow]:
        return [
            self._windows(s)[0]
            for s in self._series
            if s.tenant_id == tenant_id
            and s.age_minutes <= LOOKBACK_MINUTES
            and (title_id is None or s.title_id == title_id)
        ]

    def recent_windows(self, tenant_id: str, series_label: str) -> list[MetricWindow]:
        title, region, metric = series_label.split(":")
        windows = [
            w
            for s in self._series
            if s.tenant_id == tenant_id
            and s.metric == metric
            and (title == "*" or s.title_id == title)
            and (region == "*" or s.region == region)
            for w in self._windows(s)
        ]
        return sorted(windows, key=lambda w: w.window_start, reverse=True)

    def _windows(self, sample: SeriesSample) -> list[MetricWindow]:
        return [
            MetricWindow(
                sample.title_id,
                sample.region,
                sample.metric,
                self.now - timedelta(minutes=sample.age_minutes + k),
                round(sample.latest_value * (1 - 0.03 * k), 6),
                sample.sample_count,
            )
            for k in range(HISTORY_WINDOWS)
        ]

    def acknowledge(self, tenant_id: str, alert_id: str, note: str | None) -> bool:
        already = alert_id in self._acknowledged
        if not already:
            self._acknowledged[alert_id] = {"tenantId": tenant_id, "note": note or ""}
            self._persist()
        return already

    def link_issue(self, tenant_id: str, alert_id: str, issue_key: str) -> bool:
        link = {"tenantId": tenant_id, "alertId": alert_id, "issueKey": issue_key}
        already = link in self._links
        if not already:
            self._links.append(link)
            self._persist()
        return already

    def state(self) -> dict[str, object]:
        return {"acknowledged": dict(self._acknowledged), "links": list(self._links)}

    def _persist(self) -> None:
        if self._state_path is None:
            return
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state(), indent=2))
        os.replace(tmp, self._state_path)
