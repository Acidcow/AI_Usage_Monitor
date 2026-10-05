import abc
from typing import Dict, Any, Optional
from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine

class BaseProvider(abc.ABC):
    """
    Canonical Interface for AI Usage Providers (DRY standard).
    """

    def __init__(
        self,
        database: UsageDatabase,
        vault: DPAPIVault,
        diagnostics: DiagnosticsEngine
    ):
        self.db = database
        self.vault = vault
        self.diagnostics = diagnostics

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        pass

    @property
    @abc.abstractmethod
    def display_name(self) -> str:
        pass

    @property
    def is_configured(self) -> bool:
        cred = self.vault.get_credential(self.provider_name, "default")
        return bool(cred)

    @property
    def status(self) -> str:
        snapshots = self.db.get_provider_snapshots()
        if self.provider_name in snapshots:
            return snapshots[self.provider_name].get("status", "UNKNOWN")
        return "CONFIGURED" if self.is_configured else "NOT_CONFIGURED"

    @abc.abstractmethod
    def sync_usage(self) -> Dict[str, Any]:
        """Polls or ingests latest usage data."""
        pass

    def get_snapshot(self) -> Dict[str, Any]:
        snapshots = self.db.get_provider_snapshots()
        if self.provider_name in snapshots:
            return snapshots[self.provider_name]
        return {
            "provider": self.provider_name,
            "display_name": self.display_name,
            "status": self.status,
            "plan_type": "Unknown",
            "tokens_remaining": None,
            "requests_remaining": None,
            "reset_epoch": None,
            "last_sync": None
        }
