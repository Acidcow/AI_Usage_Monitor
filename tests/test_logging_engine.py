import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.diagnostics.logging_engine import DiagnosticsEngine, redact_sensitive_text, ErrorCategory

class TestLoggingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = DiagnosticsEngine()
        self.engine.clear_errors()

    def test_redact_anthropic_api_key(self):
        text = "Failed to authenticate with key sk-ant-api03-ABCdef123456789xyz and session sk-ant-sid01-abcdef987654321"
        redacted = redact_sensitive_text(text)
        self.assertNotIn("ABCdef123456789xyz", redacted)
        self.assertNotIn("abcdef987654321", redacted)
        self.assertIn("sk-ant-***", redacted)

    def test_redact_bearer_token_and_openai(self):
        text = "Authorization: Bearer my-secret-jwt-token-string and sk-proj-1234567890abcdef"
        redacted = redact_sensitive_text(text)
        self.assertNotIn("my-secret-jwt-token-string", redacted)
        self.assertNotIn("1234567890abcdef", redacted)
        self.assertIn("Bearer ***", redacted)
        self.assertIn("sk-***", redacted)

    def test_redact_windows_user_path(self):
        text = "File error at C:\\Users\\JamesEckhardt\\AppData\\Local\\config.json"
        redacted = redact_sensitive_text(text)
        self.assertNotIn("JamesEckhardt", redacted)
        self.assertIn("<REDACTED_USER>", redacted)

    def test_record_error_event_and_retrieve(self):
        self.engine.record_error(
            category=ErrorCategory.AUTH_FAILURE,
            provider="claude",
            message="Invalid API Key provided: sk-ant-api03-secret12345",
            details={"status_code": 401}
        )

        errors = self.engine.get_recent_errors()
        self.assertEqual(len(errors), 1)
        err = errors[0]
        self.assertEqual(err["category"], "AUTH_FAILURE")
        self.assertEqual(err["provider"], "claude")
        self.assertNotIn("secret12345", err["message"])
        self.assertIn("sk-ant-***", err["message"])

    def test_export_diagnostic_bundle(self):
        self.engine.record_error(
            category=ErrorCategory.RATE_LIMIT_EXCEEDED,
            provider="claude",
            message="Rate limit 429 reached for token quota",
            details={"retry_after": 60}
        )

        bundle = self.engine.export_diagnostic_bundle()
        self.assertIn("system_info", bundle)
        self.assertIn("recent_errors", bundle)
        self.assertIn("provider_health", bundle)
        self.assertEqual(len(bundle["recent_errors"]), 1)

if __name__ == "__main__":
    unittest.main()
