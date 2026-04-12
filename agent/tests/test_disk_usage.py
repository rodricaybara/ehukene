import importlib.util
import subprocess
from pathlib import Path


_PLUGIN_PATH = Path(__file__).resolve().parents[1] / "plugins" / "disk_usage.py"


def _load_plugin_module():
    spec = importlib.util.spec_from_file_location("test_disk_usage_plugin", _PLUGIN_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_run_wmi_returns_normalized_disks(monkeypatch):
    module = _load_plugin_module()

    class Completed:
        stdout = (
            '[{"DeviceID":"D:","VolumeName":"","FileSystem":"NTFS","Size":"53687091200","FreeSpace":"10737418240"},'
            '{"DeviceID":"C:","VolumeName":"System","FileSystem":"NTFS","Size":"107374182400","FreeSpace":"42949672960"}]'
        )

    def fake_run(*args, **kwargs):
        return Completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module._run_wmi()

    assert result == [
        {
            "disk_source": "wmi",
            "drive_letter": "C:",
            "volume_name": "System",
            "filesystem": "NTFS",
            "total_capacity_gb": 100.0,
            "free_capacity_gb": 40.0,
            "used_capacity_gb": 60.0,
            "used_percent": 60.0,
        },
        {
            "disk_source": "wmi",
            "drive_letter": "D:",
            "volume_name": None,
            "filesystem": "NTFS",
            "total_capacity_gb": 50.0,
            "free_capacity_gb": 10.0,
            "used_capacity_gb": 40.0,
            "used_percent": 80.0,
        },
    ]


def test_run_wmi_returns_empty_list_when_no_local_disks(monkeypatch):
    module = _load_plugin_module()

    class Completed:
        stdout = "NO_LOCAL_DISKS"

    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: Completed())

    assert module._run_wmi() == []


def test_run_wmi_returns_none_on_timeout(monkeypatch):
    module = _load_plugin_module()

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="powershell", timeout=15)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._run_wmi() is None


def test_collect_never_propagates_exceptions(monkeypatch):
    module = _load_plugin_module()

    def boom():
        raise RuntimeError("unexpected")

    monkeypatch.setattr(module, "_run_wmi", boom)

    assert module.collect() is None
