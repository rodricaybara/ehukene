import asyncio
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.device import Device
from app.schemas.telemetry import TelemetryPayload
from app.services.ingest import insert_health_monitor, insert_raw


def _build_payload() -> dict:
    return {
        "device_id": "HOST-001",
        "timestamp": "2026-04-15T08:00:00Z",
        "agent_version": "1.2.3",
        "username": "usuario",
        "metrics": {
            "health_monitor": {
                "plugin_version": "1.1.0",
                "host": "HOST-001",
                "domain": "CORP.LOCAL",
                "timestamp": "2026-04-15T08:00:00Z",
                "execution": {
                    "duration_ms": 1234,
                    "metrics_attempted": 8,
                    "metrics_successful": 8,
                },
                "metrics": {
                    "cpu": {
                        "load_percentage": 12,
                        "status": "ok",
                    },
                    "memory": {
                        "total_kb": 8264704,
                        "free_kb": 1514588,
                        "usage_pct": 81.67,
                        "status": "warning",
                    },
                    "disk": {
                        "drive": "C:",
                        "total_gb": 238.06,
                        "free_gb": 15.60,
                        "free_pct": 6.55,
                        "status": "critical",
                    },
                    "events": {
                        "critical_count": 0,
                        "error_count": 4,
                        "filtered_count": 25,
                        "top_sources": [
                            {"provider": "Disk", "count": 3},
                        ],
                        "sample_events": [
                            {
                                "event_id": 7001,
                                "provider": "Service Control Manager",
                                "level": "Error",
                                "time_created": "2026-04-15T06:23:15Z",
                            }
                        ],
                        "status": "ok",
                    },
                    "domain": {
                        "secure_channel": True,
                        "status": "ok",
                    },
                    "uptime": {
                        "last_boot": "2026-04-14T07:23:42Z",
                        "days": 0.3,
                        "status": "ok",
                    },
                    "boot_time": {
                        "last_boot_time": "2026-04-14T09:23:57",
                        "boot_duration_seconds": 115,
                        "source": "event_log",
                        "status": "ok",
                    },
                    "services": [
                        {
                            "name": "SepMasterService",
                            "display_name": "Symantec Endpoint Protection",
                            "state": "Running",
                            "startup_type": "Automatic",
                            "tier": 1,
                            "status": "ok",
                        },
                        {
                            "name": "wuauserv",
                            "display_name": "Windows Update",
                            "state": "Stopped",
                            "startup_type": "Automatic",
                            "tier": 2,
                            "status": "warning",
                        },
                    ],
                },
            }
        },
    }


class FakeSession:
    def __init__(self):
        self.items = []

    def add(self, item):
        self.items.append(item)


def test_health_monitor_payload_validation_accepts_valid_payload():
    payload = TelemetryPayload.model_validate(_build_payload())

    assert payload.metrics.health_monitor is not None
    assert payload.metrics.health_monitor.execution.metrics_attempted == 8
    assert payload.metrics.health_monitor.metrics["boot_time"].source == "event_log"
    assert len(payload.metrics.health_monitor.metrics["services"]) == 2


def test_insert_health_monitor_creates_typed_records():
    payload = TelemetryPayload.model_validate(_build_payload())
    device = Device(
        id=uuid.uuid4(),
        hostname="HOST-001",
        api_key_hash="a" * 64,
        active=True,
    )
    db = FakeSession()

    asyncio.run(insert_health_monitor(device, payload, db))

    assert len(db.items) == 9
    assert sum(1 for item in db.items if item.__class__.__name__ == "HealthServiceMetric") == 2
    assert any(item.__class__.__name__ == "HealthCpuMetric" for item in db.items)
    assert any(item.__class__.__name__ == "HealthBootTimeMetric" for item in db.items)


def test_insert_raw_persists_agent_timestamp_from_payload():
    payload = TelemetryPayload.model_validate(_build_payload())
    device = Device(
        id=uuid.uuid4(),
        hostname="HOST-001",
        api_key_hash="a" * 64,
        active=True,
    )
    db = FakeSession()

    asyncio.run(insert_raw(device, payload, payload.model_dump(mode="json"), db))

    assert len(db.items) == 1
    raw = db.items[0]
    assert raw.__class__.__name__ == "TelemetryRaw"
    assert raw.agent_timestamp == datetime(2026, 4, 15, 8, 0, 0)
