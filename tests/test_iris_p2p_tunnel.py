import unittest
import os
import sys
import tempfile
import time
import socket
import json
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.discovery.p2p_tunnel import (
    TLSCertificateManager,
    P2PBeacon,
    P2PTunnelServer,
    P2PTunnelClient,
    DEFAULT_CLUSTER_SECRET
)

def find_free_port() -> int:
    """Finds an unused TCP port on localhost for test isolation."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

class TestIrisP2PTunnel(unittest.TestCase):
    """
    TDD Test Suite for IRIS P2P Tunneling, Anti-Snooping TLS, and LAN Discovery.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cert_dir = Path(self.temp_dir.name) / "certs"
        self.db_path = str(Path(self.temp_dir.name) / "test_p2p.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.test_port = find_free_port()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_certificate_generation_and_fingerprint(self):
        cert_mgr = TLSCertificateManager(cert_dir=self.cert_dir)
        cert_path, key_path = cert_mgr.ensure_certificate(common_name="IRIS-Test-Node")
        self.assertTrue(cert_path.exists())
        self.assertTrue(key_path.exists())

        fingerprint = cert_mgr.get_fingerprint()
        self.assertIsInstance(fingerprint, str)
        self.assertEqual(len(fingerprint), 64, "SHA-256 fingerprint should be 64 hex characters")

    def test_02_beacon_signature_signing_and_verification(self):
        beacon = P2PBeacon(
            node_id="node-test-1",
            alias="workstation-alpha",
            tunnel_port=8767,
            cluster_secret="test-secret-key"
        )
        payload = {
            "node_id": "node-test-1",
            "alias": "workstation-alpha",
            "tunnel_port": 8767,
            "timestamp": int(time.time())
        }
        sig = beacon._sign_payload(payload)
        self.assertTrue(isinstance(sig, str) and len(sig) == 64)

        payload["signature"] = sig
        self.assertTrue(beacon._verify_signature(payload))

        # Tampered payload fails verification
        tampered = dict(payload)
        tampered["alias"] = "hacker-workstation"
        self.assertFalse(beacon._verify_signature(tampered))

    def test_03_tunnel_server_health_ping_authenticated(self):
        cert_mgr = TLSCertificateManager(cert_dir=self.cert_dir)
        server = P2PTunnelServer(
            node_id="node-srv-1",
            alias="workstation-target",
            port=self.test_port,
            cluster_secret=DEFAULT_CLUSTER_SECRET,
            database=self.db,
            cert_manager=cert_mgr
        )
        server.start()
        time.sleep(0.3)

        client = P2PTunnelClient(cluster_secret=DEFAULT_CLUSTER_SECRET, my_alias="workstation-client")
        peer_url = f"https://127.0.0.1:{self.test_port}"

        try:
            res = client.ping_peer(peer_url)
            self.assertEqual(res.get("status"), "ONLINE")
            self.assertEqual(res.get("alias"), "workstation-target")
            self.assertEqual(res.get("node_id"), "node-srv-1")
        finally:
            server.stop()

    def test_04_tunnel_server_rejects_unauthorized_token(self):
        cert_mgr = TLSCertificateManager(cert_dir=self.cert_dir)
        server = P2PTunnelServer(
            node_id="node-srv-2",
            alias="workstation-secure",
            port=self.test_port,
            cluster_secret="super-secret-cluster-key",
            database=self.db,
            cert_manager=cert_mgr
        )
        server.start()
        time.sleep(0.3)

        # Client with WRONG secret
        client = P2PTunnelClient(cluster_secret="wrong-secret-token", my_alias="workstation-intruder")
        peer_url = f"https://127.0.0.1:{self.test_port}"

        try:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                client.ping_peer(peer_url)
            self.assertEqual(ctx.exception.code, 401)
        finally:
            server.stop()

    def test_05_delegated_inference_execution_and_telemetry(self):
        cert_mgr = TLSCertificateManager(cert_dir=self.cert_dir)
        server = P2PTunnelServer(
            node_id="node-srv-3",
            alias="workstation-gpu-rig",
            port=self.test_port,
            cluster_secret=DEFAULT_CLUSTER_SECRET,
            database=self.db,
            cert_manager=cert_mgr
        )
        server.start()
        time.sleep(0.3)

        client = P2PTunnelClient(cluster_secret=DEFAULT_CLUSTER_SECRET, my_alias="dev-laptop")
        peer_url = f"https://127.0.0.1:{self.test_port}"

        try:
            res = client.delegate_inference(
                peer_url=peer_url,
                model="deepseek-r1:32b",
                prompt="Optimize this SQL query for high concurrency"
            )
            self.assertEqual(res.get("status"), "SUCCESS")
            self.assertEqual(res.get("model"), "deepseek-r1:32b")
            self.assertEqual(res.get("executor_alias"), "workstation-gpu-rig")

            # Check that telemetry event was logged in the executor's SQLite database
            events = self.db.get_recent_events(limit=5)
            self.assertGreaterEqual(len(events), 1)
            e = events[0]
            self.assertEqual(e["provider"], "iris_p2p")
            self.assertEqual(e["source"], "p2p_delegated")
            self.assertEqual(e["model"], "deepseek-r1:32b")
            self.assertEqual(e["client_alias"], "dev-laptop")
        finally:
            server.stop()

    def test_06_beacon_peer_discovery_and_expiration(self):
        beacon = P2PBeacon(
            node_id="node-local",
            alias="local-node",
            database=self.db,
            cluster_secret=DEFAULT_CLUSTER_SECRET
        )
        # Directly simulate receiving a valid peer beacon
        peer_payload = {
            "node_id": "remote-node-99",
            "alias": "ai-compute-box",
            "tunnel_port": 8767,
            "models": ["llama3.3:70b", "qwen2.5-coder"],
            "timestamp": int(time.time()),
            "platform": "win32"
        }
        peer_payload["signature"] = beacon._sign_payload(peer_payload)

        # Add to discovered peers
        beacon.discovered_peers["remote-node-99"] = {
            "node_id": "remote-node-99",
            "alias": "ai-compute-box",
            "ip": "192.168.1.150",
            "tunnel_port": 8767,
            "models": ["llama3.3:70b"],
            "last_seen": time.time() - 30.0, # older than 20s
            "status": "ONLINE"
        }

        # Stale peer should be marked OFFLINE
        beacon._prune_stale_peers(timeout_seconds=20.0)
        self.assertEqual(beacon.discovered_peers["remote-node-99"]["status"], "OFFLINE")

if __name__ == "__main__":
    unittest.main()
