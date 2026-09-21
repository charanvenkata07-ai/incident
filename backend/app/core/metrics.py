"""
Prometheus Metrics for IncidentFlow Realtime & Operational Workflows.
Implements the required counters and gauges specified in Section 32.
"""
from typing import Dict
from threading import Lock

class PrometheusMetrics:
    def __init__(self):
        self._lock = Lock()
        self._counters: Dict[str, int] = {
            "websocket_connections": 0,
            "websocket_reconnects": 0,
            "websocket_events_published": 0,
            "websocket_events_failed": 0,
            "chat_messages": 0,
            "notification_delivery": 0,
            "notification_failures": 0,
            "group_notices": 0,
            "assignments": 0,
            "assignment_failures": 0,
            "servicenow_sync_success": 0,
            "servicenow_sync_failure": 0,
            "live_pilot_assignments": 0,
            "live_pilot_rejections": 0,
        }
        self._gauges: Dict[str, float] = {
            "active_websocket_connections": 0.0,
            "active_pilot_assignments": 0.0,
        }

    def inc(self, name: str, value: int = 1):
        with self._lock:
            if name in self._counters:
                self._counters[name] += value
            else:
                self._counters[name] = value

    def set_gauge(self, name: str, value: float):
        with self._lock:
            self._gauges[name] = float(value)

    def get_metrics_text(self) -> str:
        lines = []
        with self._lock:
            for k, v in self._counters.items():
                lines.append(f"# TYPE {k} counter")
                lines.append(f"{k} {v}")
            for k, v in self._gauges.items():
                lines.append(f"# TYPE {k} gauge")
                lines.append(f"{k} {v}")
        return "\n".join(lines) + "\n"

    def get_metrics_dict(self) -> dict:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
            }

metrics = PrometheusMetrics()
