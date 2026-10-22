import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend.system.windows_service import (
    WindowsServiceManager,
    RotatingFileStream,
    setup_daemon_logging,
)
from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.server.http_server import AppHTTPServer
from backend.tray.windows_tray import WindowsTrayManager
import run_monitor


class TestWindowsAutoStartAndService(unittest.TestCase):
    """
    Comprehensive Test Suite for Ticket AIUM-901:
    Windows Auto-Start Registration, Single-Instance PID Locks, Crash-Recovery Daemon,
    CLI Lifecycle Flags, HTTP Endpoints, System Tray Toggle, and Settings UI.
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="aium_svc_test_"))
        self.data_dir = self.temp_dir / "data"
        self.logs_dir = self.temp_dir / "logs"
        # Use an isolated HKCU subkey for real winreg testing without altering actual Run key
        self.test_run_key = r"Software\AIUsageMonitor_UnitTest_Run"
        self.test_value_name = "AIUsageMonitorTestEntry"

        self.svc = WindowsServiceManager(
            data_dir=self.data_dir,
            logs_dir=self.logs_dir,
            run_key_path=self.test_run_key,
            registry_value_name=self.test_value_name,
            task_name="AIUsageMonitorService_UnitTest",
        )

    def tearDown(self):
        # Clean up isolated test registry key on Windows
        if sys.platform == "win32":
            try:
                import winreg
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, self.test_run_key)
            except Exception:
                pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_resolve_pythonw_and_console(self):
        """Verify pythonw.exe resolution on Windows and console fallback."""
        pythonw = WindowsServiceManager.resolve_pythonw()
        self.assertTrue(len(pythonw) > 0)
        if sys.platform == "win32":
            self.assertTrue(
                pythonw.lower().endswith("pythonw.exe") or pythonw.lower().endswith("python.exe")
            )
        console_py = WindowsServiceManager.resolve_python_console(pythonw)
        self.assertTrue(console_py.lower().endswith("python.exe") or len(console_py) > 0)

    def test_02_build_startup_command_default_and_widget(self):
        """Verify startup command quotes paths and appends --daemon and --widget."""
        cmd_basic = self.svc.build_startup_command(launch_widget=False)
        self.assertIn("run_monitor.py", cmd_basic)
        self.assertIn("--daemon", cmd_basic)
        self.assertNotIn("--widget", cmd_basic)

        cmd_widget = self.svc.build_startup_command(
            launch_widget=True, extra_args=["--port", "8765"]
        )
        self.assertIn("--daemon", cmd_widget)
        self.assertIn("--widget", cmd_widget)
        self.assertIn("--port", cmd_widget)

    def test_03_persistent_config_load_and_save(self):
        """Verify service_config.json persistence and defaults."""
        initial = self.svc.load_config()
        self.assertFalse(initial["auto_start_enabled"])
        self.assertEqual(initial["auto_start_method"], "registry")

        updated = self.svc.save_config(
            {"auto_start_enabled": True, "launch_widget_on_startup": True}
        )
        self.assertTrue(updated["auto_start_enabled"])
        self.assertTrue(updated["launch_widget_on_startup"])
        self.assertIsNotNone(updated["updated_at"])

        reloaded = self.svc.load_config()
        self.assertTrue(reloaded["auto_start_enabled"])
        self.assertTrue(reloaded["launch_widget_on_startup"])

    def test_04_registry_startup_install_status_and_uninstall(self):
        """Verify Windows Registry HKCU Run installation, query, and removal."""
        status_before = self.svc.get_registry_startup_status()
        self.assertFalse(status_before["enabled"])

        install_res = self.svc.install_registry_startup(launch_widget=True)
        self.assertTrue(install_res["success"])
        self.assertTrue(install_res["enabled"])
        self.assertIn("--widget", install_res["command"])

        status_active = self.svc.get_registry_startup_status()
        self.assertTrue(status_active["enabled"])
        self.assertTrue(status_active["launch_widget"])
        self.assertIn("--daemon", status_active["command"])

        uninstall_res = self.svc.uninstall_registry_startup()
        self.assertTrue(uninstall_res["success"])
        self.assertFalse(uninstall_res["enabled"])

        status_after = self.svc.get_registry_startup_status()
        self.assertFalse(status_after["enabled"])

    def test_05_unified_startup_install_and_toggle(self):
        """Verify unified install_startup, is_startup_enabled, and toggle_startup."""
        self.assertFalse(self.svc.is_startup_enabled())

        # Toggle ON
        res_on = self.svc.toggle_startup(launch_widget=True)
        self.assertTrue(res_on["enabled"])
        self.assertTrue(self.svc.is_startup_enabled())

        # Toggle OFF
        res_off = self.svc.toggle_startup()
        self.assertFalse(res_off["enabled"])
        self.assertFalse(self.svc.is_startup_enabled())

    def test_06_scheduled_task_mock_integration(self):
        """Verify Task Scheduler (schtasks.exe) command generation and fallback."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="SUCCESS", stderr="")
            res = self.svc.install_scheduled_task(launch_widget=True)
            if sys.platform == "win32":
                self.assertTrue(res["success"])
                self.assertEqual(res["method"], "task_scheduler")

            del_res = self.svc.uninstall_scheduled_task()
            self.assertTrue(del_res["success"])

    def test_07_win32_is_pid_running_detection(self):
        """Verify Win32 OpenProcess / GetExitCodeProcess liveness detection."""
        self.assertTrue(WindowsServiceManager.is_pid_running(os.getpid()))
        self.assertFalse(WindowsServiceManager.is_pid_running(0))
        self.assertFalse(WindowsServiceManager.is_pid_running(-5))
        self.assertFalse(WindowsServiceManager.is_pid_running(99999999))

    def test_08_pid_lock_acquire_heartbeat_and_release(self):
        """Verify PID lock creation, heartbeat updates, and clean release."""
        state = self.svc.acquire_pid_lock(
            pid=os.getpid(),
            mode="daemon",
            host="127.0.0.1",
            port=8765,
            proxy_port=8766,
            ollama_port=8989,
        )
        self.assertEqual(state["pid"], os.getpid())
        self.assertTrue(self.svc.pid_file.exists())
        self.assertTrue(self.svc.state_file.exists())

        hb = self.svc.update_heartbeat(custom_metric=42)
        self.assertEqual(hb["custom_metric"], 42)
        self.assertTrue(hb["running"])

        released = self.svc.release_pid_lock(pid=os.getpid())
        self.assertTrue(released)
        self.assertFalse(self.svc.pid_file.exists())

    def test_09_pid_lock_ownership_protection(self):
        """Verify release_pid_lock refuses to delete a lock owned by a different PID."""
        self.svc.acquire_pid_lock(pid=os.getpid(), mode="daemon")
        wrong_release = self.svc.release_pid_lock(pid=os.getpid() + 100)
        self.assertFalse(wrong_release)
        self.assertTrue(self.svc.pid_file.exists())

        right_release = self.svc.release_pid_lock(pid=os.getpid())
        self.assertTrue(right_release)

    def test_10_stale_pid_cleanup_in_service_status(self):
        """Verify stale dead PIDs are automatically cleaned up when querying status."""
        self.svc.acquire_pid_lock(pid=99999998, mode="daemon")
        self.assertTrue(self.svc.pid_file.exists())

        status = self.svc.get_service_status()
        self.assertFalse(status["running"])
        self.assertIsNone(status["pid"])
        self.assertFalse(self.svc.pid_file.exists())

    def test_11_active_service_status_and_uptime(self):
        """Verify get_service_status reports running=True and uptime when PID is alive."""
        self.svc.acquire_pid_lock(pid=os.getpid(), mode="daemon", port=8765)
        status = self.svc.get_service_status(include_logs=True)
        self.assertTrue(status["running"])
        self.assertEqual(status["pid"], os.getpid())
        self.assertEqual(status["mode"], "daemon")
        self.assertGreaterEqual(status["uptime_seconds"], 0)
        self.assertIn("startup", status)

    def test_12_rotating_file_stream_and_log_rotation(self):
        """Verify RotatingFileStream writes and rotates files when max_bytes is exceeded."""
        log_path = self.logs_dir / "service.log"
        stream = RotatingFileStream(log_path=log_path, max_bytes=1024, backup_count=2)

        for i in range(60):
            stream.write(f"Line {i}: " + ("X" * 40) + "\n")
        stream.flush()

        self.assertTrue(log_path.exists())
        backup_1 = self.logs_dir / "service.log.1"
        self.assertTrue(backup_1.exists())

        recent = self.svc.get_recent_logs(max_lines=10)
        self.assertLessEqual(len(recent), 10)
        self.assertGreater(len(recent), 0)

        clear_res = self.svc.clear_service_logs()
        self.assertTrue(clear_res["success"])
        self.assertEqual(len(self.svc.get_recent_logs()), 0)

    def test_13_supervised_daemon_clean_exit(self):
        """Verify run_supervised_daemon exits cleanly after normal worker completion."""
        calls = []
        orig_stdout, orig_stderr = sys.stdout, sys.stderr
        try:
            rc = self.svc.run_supervised_daemon(
                worker_callable=lambda: calls.append("ran_once")
            )
        finally:
            sys.stdout, sys.stderr = orig_stdout, orig_stderr

        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 1)

    def test_14_supervised_daemon_crash_recovery_and_backoff(self):
        """Verify run_supervised_daemon retries crashed workers up to max_crash_restarts."""
        self.svc.save_config({"auto_restart_on_crash": True, "max_crash_restarts": 2})
        attempts = {"count": 0}

        def flaky_worker():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("Simulated worker crash")

        orig_stdout, orig_stderr = sys.stdout, sys.stderr
        try:
            with patch("time.sleep"):
                rc = self.svc.run_supervised_daemon(worker_callable=flaky_worker)
        finally:
            sys.stdout, sys.stderr = orig_stdout, orig_stderr

        self.assertEqual(rc, 0)
        self.assertEqual(attempts["count"], 3)

    def test_15_supervised_daemon_respects_graceful_stop(self):
        """Verify run_supervised_daemon does not restart when stop_requested is True."""
        attempts = {"count": 0}

        def stopping_worker():
            attempts["count"] += 1
            self.svc.request_graceful_stop()
            raise RuntimeError("Exit after stop request")

        orig_stdout, orig_stderr = sys.stdout, sys.stderr
        try:
            rc = self.svc.run_supervised_daemon(worker_callable=stopping_worker)
        finally:
            sys.stdout, sys.stderr = orig_stdout, orig_stderr

        self.assertEqual(rc, 0)
        self.assertEqual(attempts["count"], 1)

    def test_16_cli_parse_args_lifecycle_flags(self):
        """Verify run_monitor.parse_args supports all AIUM-901 CLI flags."""
        args1 = run_monitor.parse_args(["--install-startup", "--widget", "--startup-method", "both"])
        self.assertTrue(args1.install_startup)
        self.assertTrue(args1.widget)
        self.assertEqual(args1.startup_method, "both")

        args2 = run_monitor.parse_args(["--service-status"])
        self.assertTrue(args2.service_status)

        args3 = run_monitor.parse_args(["--daemon", "--port", "9000"])
        self.assertTrue(args3.daemon)
        self.assertEqual(args3.port, 9000)

    def test_17_http_api_system_startup_and_service_endpoints(self):
        """Verify GET/POST /api/system/startup and POST /api/system/service endpoints."""
        db = UsageDatabase(db_path=self.temp_dir / "test.db")
        vault = DPAPIVault(storage_path=str(self.temp_dir / "vault.json"))
        diag = DiagnosticsEngine()
        server = AppHTTPServer(
            database=db,
            vault=vault,
            diagnostics=diag,
            providers={},
            host="127.0.0.1",
            port=0,
            service_manager=self.svc,
        )
        server.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"

            # 1. GET /api/system/startup
            with urllib.request.urlopen(f"{base_url}/api/system/startup") as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data["running"])
                self.assertFalse(data["startup"]["enabled"])

            # 2. POST /api/system/startup (enable)
            req_enable = urllib.request.Request(
                f"{base_url}/api/system/startup",
                data=json.dumps({"enabled": True, "launch_widget": True, "method": "registry"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req_enable) as resp:
                res_enable = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(res_enable["enabled"])
                self.assertTrue(res_enable["launch_widget"])

            # 3. POST /api/system/startup (toggle off)
            req_toggle = urllib.request.Request(
                f"{base_url}/api/system/startup",
                data=json.dumps({"action": "toggle"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req_toggle) as resp:
                res_toggle = json.loads(resp.read().decode("utf-8"))
                self.assertFalse(res_toggle["enabled"])

            # 4. POST /api/system/service (status & clear_logs)
            req_svc = urllib.request.Request(
                f"{base_url}/api/system/service",
                data=json.dumps({"action": "clear_logs"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req_svc) as resp:
                res_svc = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(res_svc["success"])
        finally:
            server.stop()

    def test_18_windows_tray_manager_startup_callbacks(self):
        """Verify WindowsTrayManager accepts and wires on_toggle_startup and is_startup_enabled."""
        toggled = {"called": False}
        tray = WindowsTrayManager(
            app_name="Test Monitor",
            on_toggle_startup=lambda: toggled.update({"called": True}),
            is_startup_enabled=self.svc.is_startup_enabled,
        )
        self.assertIsNotNone(tray.on_toggle_startup)
        self.assertFalse(tray.is_startup_enabled())
        tray.on_toggle_startup()
        self.assertTrue(toggled["called"])

    def test_19_settings_panel_html_contains_autostart_controls(self):
        """Verify frontend/components/settings_panel.html includes AIUM-901 controls."""
        html_path = Path(__file__).resolve().parent.parent / "frontend" / "components" / "settings_panel.html"
        content = html_path.read_text(encoding="utf-8")
        self.assertIn("windows-service-settings-card", content)
        self.assertIn("cfg-win-autostart-enabled", content)
        self.assertIn("cfg-win-autostart-widget", content)
        self.assertIn("cfg-win-autostart-method", content)
        self.assertIn("applyWindowsStartupConfig", content)

    def test_20_start_background_service_idempotent_when_running(self):
        """Verify start_background_service does not spawn duplicate process when already running."""
        self.svc.acquire_pid_lock(pid=os.getpid(), mode="daemon")
        res = self.svc.start_background_service()
        self.assertTrue(res["success"])
        self.assertTrue(res.get("already_running"))
        self.assertEqual(res["pid"], os.getpid())


if __name__ == "__main__":
    unittest.main()
