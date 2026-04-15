import importlib.util
from pathlib import Path


_PLUGIN_PATH = Path(__file__).resolve().parents[1] / "plugins" / "health_monitor.py"


def _load_plugin_module():
    spec = importlib.util.spec_from_file_location("test_health_monitor_plugin", _PLUGIN_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_boot_time_status_ranges():
    module = _load_plugin_module()
    thresholds = {"optimal": 60, "normal": 120, "degraded": 180}

    assert module._get_boot_time_status(None, thresholds) == "unknown"
    assert module._get_boot_time_status(30, thresholds) == "optimal"
    assert module._get_boot_time_status(60, thresholds) == "ok"
    assert module._get_boot_time_status(145, thresholds) == "degraded"
    assert module._get_boot_time_status(180, thresholds) == "critical"


def test_service_status_rules():
    module = _load_plugin_module()

    assert module._get_service_status("Running", "Automatic", 1) == "ok"
    assert module._get_service_status("Stopped", "Disabled", 3) == "ok"
    assert module._get_service_status("Stopped", "Automatic", 1) == "critical"
    assert module._get_service_status("Stopped", "Automatic", 2) == "warning"
    assert module._get_service_status("Stopped", "Manual", 1) == "warning"
    assert module._get_service_status("Stopped", "Manual", 3) == "ok"


def test_load_config_creates_default_when_missing(tmp_path, monkeypatch):
    module = _load_plugin_module()
    config_path = tmp_path / "config" / "health_monitor_config.json"
    monkeypatch.setattr(module, "_CONFIG_PATH", config_path)

    config = module._load_config()

    assert config["version"] == "1.1"
    assert config_path.exists()


def test_boot_time_metric_uses_wmi_fallback(monkeypatch):
    module = _load_plugin_module()
    config = module._default_config()

    monkeypatch.setattr(module, "_get_boot_time_from_event_log", lambda: None)
    monkeypatch.setattr(
        module,
        "_get_boot_time_from_wmi",
        lambda: {
            "last_boot_time": "2026-04-10T10:00:00",
            "boot_duration_seconds": None,
            "source": "wmi",
        },
    )

    result = module._get_boot_time_metric(config)

    assert result == {
        "last_boot_time": "2026-04-10T10:00:00",
        "boot_duration_seconds": None,
        "source": "wmi",
        "status": "unknown",
    }


def test_collect_builds_full_payload_and_counts_successes(monkeypatch):
    module = _load_plugin_module()
    config = module._default_config()

    monkeypatch.setattr(module, "_load_config", lambda: config)
    monkeypatch.setattr(module, "_get_host", lambda: "HOST-01")
    monkeypatch.setattr(module, "_get_domain_name", lambda: "CORP.LOCAL")
    monkeypatch.setattr(module, "_utc_now", lambda: "2026-04-14T08:00:00Z")
    monkeypatch.setattr(module, "_get_cpu_metric", lambda _: {"load_percentage": 10, "status": "ok"})
    monkeypatch.setattr(module, "_get_memory_metric", lambda _: {"total_kb": 1, "free_kb": 1, "usage_pct": 0.0, "status": "ok"})
    monkeypatch.setattr(module, "_get_disk_metric", lambda _: {"drive": "C:", "total_gb": 100.0, "free_gb": 50.0, "free_pct": 50.0, "status": "ok"})
    monkeypatch.setattr(module, "_get_events_metric", lambda _: {"critical_count": 0, "error_count": 0, "filtered_count": 0, "top_sources": [], "sample_events": [], "status": "error"})
    monkeypatch.setattr(module, "_get_domain_metric", lambda: {"secure_channel": False, "status": "not_in_domain"})
    monkeypatch.setattr(module, "_get_uptime_metric", lambda _: {"last_boot": "2026-04-10T08:00:00Z", "days": 4.0, "status": "ok"})
    monkeypatch.setattr(module, "_get_boot_time_metric", lambda _: {"last_boot_time": "2026-04-10T10:00:00", "boot_duration_seconds": None, "source": "wmi", "status": "unknown"})
    monkeypatch.setattr(module, "_get_services_metric", lambda _: [{"name": "Spooler", "display_name": "Print Spooler", "state": "Stopped", "startup_type": "Disabled", "tier": 3, "status": "ok"}])

    result = module.collect()

    assert result is not None
    assert result["plugin_version"] == "1.1.0"
    assert result["host"] == "HOST-01"
    assert result["domain"] == "CORP.LOCAL"
    assert result["timestamp"] == "2026-04-14T08:00:00Z"
    assert result["execution"]["metrics_attempted"] == 8
    assert result["execution"]["metrics_successful"] == 7
    assert set(result["metrics"].keys()) == {
        "cpu",
        "memory",
        "disk",
        "events",
        "domain",
        "uptime",
        "boot_time",
        "services",
    }


def test_collect_never_propagates_exceptions(monkeypatch):
    module = _load_plugin_module()
    monkeypatch.setattr(module, "_load_config", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    assert module.collect() is None
