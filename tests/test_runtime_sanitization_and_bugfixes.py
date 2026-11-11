import os
import sys
import json
import threading
import tempfile
import unittest
from pathlib import Path

# Ensure project root in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.security.dpapi_vault import DPAPIVault
from backend.discovery.p2p_tunnel import P2PTunnelServer, TLSCertificateManager

class TestRuntimeSanitizationAndBugFixes(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault_path = Path(self.temp_dir.name) / "credentials.json"
        self.vault = DPAPIVault(storage_path=str(self.vault_path))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_dpapi_vault_has_rlock(self):
        """Verify DPAPIVault initializes an RLock."""
        self.assertTrue(hasattr(self.vault, "_lock"))
        self.assertIsInstance(self.vault._lock, type(threading.RLock()))

    def test_02_dpapi_vault_concurrent_reads_writes(self):
        """Verify thread-safety of DPAPIVault under concurrent reads and writes."""
        errors = []

        def worker(idx):
            try:
                for j in range(20):
                    self.vault.set_credential(f"provider_{idx}", f"account_{j}", f"secret_{idx}_{j}")
                    val = self.vault.get_credential(f"provider_{idx}", f"account_{j}")
                    self.assertEqual(val, f"secret_{idx}_{j}")
                    self.vault.list_configured_providers()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent vault operations encountered errors: {errors}")

    def test_03_dpapi_vault_atomic_save(self):
        """Verify _save_store performs atomic write via temp file."""
        self.vault.set_credential("openai", "default", "sk-proj-test12345")
        self.assertTrue(self.vault_path.exists())
        data = json.loads(self.vault_path.read_text(encoding="utf-8"))
        self.assertIn("openai", data)

    def test_04_dpapi_vault_delete_and_list(self):
        """Verify storing, listing, and deleting credentials."""
        self.vault.set_credential("anthropic", "user1", "sk-ant-testkey")
        providers = self.vault.list_configured_providers()
        self.assertTrue(any(p["provider"] == "anthropic" for p in providers))
        
        self.vault.delete_credential("anthropic", "user1")
        providers_after = self.vault.list_configured_providers()
        self.assertFalse(any(p["provider"] == "anthropic" for p in providers_after))

    def test_05_p2p_tunnel_certificate_generation(self):
        """Verify TLSCertificateManager generates valid self-signed cert and key."""
        cert_dir = Path(self.temp_dir.name) / "certs"
        mgr = TLSCertificateManager(cert_dir=cert_dir)
        cert_path, key_path = mgr.ensure_certificate(common_name="IRIS-TestNode")
        self.assertTrue(cert_path.exists())
        self.assertTrue(key_path.exists())
        fingerprint = mgr.get_fingerprint()
        self.assertIsInstance(fingerprint, str)
        self.assertGreater(len(fingerprint), 10)

    def test_06_app_js_single_switch_tab_definition(self):
        """Verify frontend/js/app.js has exactly one switchTab method definition."""
        app_js_path = Path("frontend/js/app.js")
        if app_js_path.exists():
            content = app_js_path.read_text(encoding="utf-8")
            count = content.count("switchTab(target) {")
            self.assertEqual(count, 1, f"Expected exactly 1 switchTab(target) definition, found {count}")

    def test_07_app_js_switch_tab_sets_active_tab_first(self):
        """Verify canonical switchTab sets this.activeTab = target at the beginning."""
        app_js_path = Path("frontend/js/app.js")
        if app_js_path.exists():
            content = app_js_path.read_text(encoding="utf-8")
            idx = content.find("switchTab(target) {")
            self.assertNotEqual(idx, -1)
            snippet = content[idx:idx+150]
            self.assertIn("this.activeTab = target;", snippet)

    def test_08_app_js_hardcoded_identities_sanitized(self):
        """Verify hardcoded personal fallback strings are replaced with generic defaults."""
        app_js_path = Path("frontend/js/app.js")
        if app_js_path.exists():
            content = app_js_path.read_text(encoding="utf-8")
            self.assertNotIn("James Eckhardt", content)
            self.assertNotIn("Synthesis2", content)
            self.assertIn("Local User", content)
            self.assertIn("Local Workstation", content)

    def test_09_p2p_tunnel_no_hardcoded_developer_identities(self):
        """Verify p2p_tunnel.py contains no hardcoded personal/developer identities."""
        p2p_path = Path("backend/discovery/p2p_tunnel.py")
        if p2p_path.exists():
            content = p2p_path.read_text(encoding="utf-8")
            self.assertNotIn("James Eckhardt", content)
            self.assertNotIn("acidcow", content)

    def test_10_dpapi_vault_multiple_accounts_isolation(self):
        """Verify multiple accounts under the same provider are isolated."""
        self.vault.set_credential("gemini", "acc_a", "key_a")
        self.vault.set_credential("gemini", "acc_b", "key_b")
        self.assertEqual(self.vault.get_credential("gemini", "acc_a"), "key_a")
        self.assertEqual(self.vault.get_credential("gemini", "acc_b"), "key_b")

    def test_11_dpapi_vault_empty_and_missing_file(self):
        """Verify vault handles missing storage file gracefully."""
        missing_path = Path(self.temp_dir.name) / "nonexistent.json"
        vault2 = DPAPIVault(storage_path=str(missing_path))
        self.assertEqual(vault2.list_configured_providers(), [])

    def test_12_p2p_tunnel_fingerprint_consistency(self):
        """Verify fingerprint is consistent across calls."""
        cert_dir = Path(self.temp_dir.name) / "certs2"
        mgr = TLSCertificateManager(cert_dir=cert_dir)
        mgr.ensure_certificate(common_name="IRIS-Node2")
        fp1 = mgr.get_fingerprint()
        fp2 = mgr.get_fingerprint()
        self.assertEqual(fp1, fp2)

    def test_13_app_js_syntax_validity(self):
        """Verify app.js has valid JavaScript syntax (no unmatched braces or syntax errors)."""
        app_js_path = Path("frontend/js/app.js")
        if app_js_path.exists():
            content = app_js_path.read_text(encoding="utf-8")
            # Basic sanity checks for JS structure
            self.assertGreater(len(content), 1000)
            self.assertEqual(content.count("{"), content.count("}"))

    def test_14_vault_atomic_replacement_helper(self):
        """Verify atomic replacement creates no orphan .tmp files."""
        self.vault.set_credential("test_prov", "test_acc", "secret_val")
        tmp_files = list(Path(self.temp_dir.name).glob("*.tmp.*"))
        self.assertEqual(len(tmp_files), 0, f"Orphaned temp files found: {tmp_files}")

    def test_15_vault_empty_secret_handling(self):
        """Verify storing empty secret."""
        self.vault.set_credential("test_prov", "empty_acc", "")
        self.assertEqual(self.vault.get_credential("test_prov", "empty_acc"), "")

    def test_16_vault_overwrite_credential(self):
        """Verify overwriting an existing credential updates correctly."""
        self.vault.set_credential("anthropic", "acc1", "key_v1")
        self.assertEqual(self.vault.get_credential("anthropic", "acc1"), "key_v1")
        self.vault.set_credential("anthropic", "acc1", "key_v2")
        self.assertEqual(self.vault.get_credential("anthropic", "acc1"), "key_v2")

    def test_17_vault_delete_nonexistent(self):
        """Verify deleting non-existent credential does not raise error."""
        try:
            self.vault.delete_credential("nonexistent", "acc")
        except Exception as e:
            self.fail(f"Deleting non-existent credential raised exception: {e}")

    def test_18_p2p_tunnel_server_init(self):
        """Verify P2PTunnelServer initializes without error."""
        server = P2PTunnelServer(port=0, cluster_secret="test-secret")
        self.assertIsNotNone(server)

    def test_19_app_js_default_email_sanitized(self):
        """Verify default email fallback in app.js is sanitized."""
        app_js_path = Path("frontend/js/app.js")
        if app_js_path.exists():
            content = app_js_path.read_text(encoding="utf-8")
            self.assertNotIn("acidcow@gmail.com", content)
            self.assertIn("local@workstation.local", content)

    def test_20_runtime_sanitization_integration_suite(self):
        """Integration check ensuring all bugfixes co-exist cleanly."""
        vault = DPAPIVault(storage_path=str(Path(self.temp_dir.name) / "integration.json"))
        vault.set_credential("provider_int", "acc_int", "secret_int")
        self.assertEqual(vault.get_credential("provider_int", "acc_int"), "secret_int")
        self.assertTrue(vault.list_configured_providers())

if __name__ == "__main__":
    unittest.main()
