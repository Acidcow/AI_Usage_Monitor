import os
import sys
import json
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List

from backend.config import CREDENTIALS_FILE

class VaultError(Exception):
    """Raised when encryption or decryption fails."""
    pass

class DPAPIVault:
    """
    Native Windows DPAPI (Data Protection API) Credential Vault.
    Uses crypt32.dll directly via ctypes on Windows.
    Provides graceful portable fallback for test environments.
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = Path(storage_path or CREDENTIALS_FILE)
        self.is_windows = sys.platform == "win32"
        if self.is_windows:
            import ctypes
            from ctypes import wintypes
            self._ctypes = ctypes
            self._wintypes = wintypes

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [
                    ('cbData', wintypes.DWORD),
                    ('pbData', ctypes.POINTER(ctypes.c_char))
                ]
            self._DATA_BLOB = DATA_BLOB
            self._crypt32 = ctypes.windll.crypt32
            self._kernel32 = ctypes.windll.kernel32

        self._store: Dict[str, Dict[str, str]] = self._load_store()

    def encrypt(self, cleartext: str) -> str:
        """Encrypts cleartext string and returns hex-encoded ciphertext."""
        if not cleartext:
            return ""

        raw_bytes = cleartext.encode("utf-8")

        if self.is_windows:
            try:
                ctypes = self._ctypes
                p_in = self._DATA_BLOB(
                    len(raw_bytes),
                    ctypes.cast(ctypes.create_string_buffer(raw_bytes), ctypes.POINTER(ctypes.c_char))
                )
                p_out = self._DATA_BLOB()
                # 0x01 = CRYPTPROTECT_UI_FORBIDDEN
                res = self._crypt32.CryptProtectData(
                    ctypes.byref(p_in),
                    "AI_Usage_Monitor_Secret",
                    None,
                    None,
                    None,
                    0x01,
                    ctypes.byref(p_out)
                )
                if not res:
                    raise VaultError("CryptProtectData failed to encrypt secret.")

                ciphertext = ctypes.string_at(p_out.pbData, p_out.cbData)
                self._kernel32.LocalFree(p_out.pbData)
                return ciphertext.hex()
            except Exception as e:
                if isinstance(e, VaultError):
                    raise
                raise VaultError(f"DPAPI encryption failed: {e}")
        else:
            # Fallback for non-windows / test container
            encoded = base64.b64encode(raw_bytes).decode("ascii")
            return f"fallback:{encoded}"

    def decrypt(self, ciphertext: str) -> str:
        """Decrypts hex-encoded ciphertext back to cleartext string."""
        if not ciphertext:
            return ""

        if ciphertext.startswith("fallback:"):
            try:
                raw_b64 = ciphertext[len("fallback:"):]
                return base64.b64decode(raw_b64.encode("ascii")).decode("utf-8")
            except Exception as e:
                raise VaultError(f"Fallback decryption failed: {e}")

        try:
            raw_bytes = bytes.fromhex(ciphertext)
        except ValueError as e:
            raise VaultError(f"Invalid ciphertext format (not hex): {e}")

        if self.is_windows:
            try:
                ctypes = self._ctypes
                p_in = self._DATA_BLOB(
                    len(raw_bytes),
                    ctypes.cast(ctypes.create_string_buffer(raw_bytes), ctypes.POINTER(ctypes.c_char))
                )
                p_out = self._DATA_BLOB()
                res = self._crypt32.CryptUnprotectData(
                    ctypes.byref(p_in),
                    None,
                    None,
                    None,
                    None,
                    0x01,
                    ctypes.byref(p_out)
                )
                if not res:
                    raise VaultError("CryptUnprotectData failed to decrypt secret.")

                plaintext_bytes = ctypes.string_at(p_out.pbData, p_out.cbData)
                self._kernel32.LocalFree(p_out.pbData)
                return plaintext_bytes.decode("utf-8")
            except Exception as e:
                if isinstance(e, VaultError):
                    raise
                raise VaultError(f"DPAPI decryption failed: {e}")
        else:
            raise VaultError("Windows DPAPI not available to decrypt native payload.")

    def set_credential(self, provider: str, account_id: str, secret: str):
        """Stores encrypted credential."""
        encrypted = self.encrypt(secret)
        if provider not in self._store:
            self._store[provider] = {}
        self._store[provider][account_id] = encrypted
        self._save_store()

    def get_credential(self, provider: str, account_id: str) -> Optional[str]:
        """Retrieves and decrypts credential."""
        if provider in self._store and account_id in self._store[provider]:
            encrypted = self._store[provider][account_id]
            return self.decrypt(encrypted)
        return None

    def delete_credential(self, provider: str, account_id: str):
        """Removes a stored credential."""
        if provider in self._store and account_id in self._store[provider]:
            del self._store[provider][account_id]
            if not self._store[provider]:
                del self._store[provider]
            self._save_store()

    def list_configured_providers(self) -> List[Dict[str, Any]]:
        """Returns list of configured providers and their accounts (without secrets)."""
        result = []
        for prov, accounts in self._store.items():
            result.append({
                "provider": prov,
                "accounts": list(accounts.keys()),
                "has_credentials": len(accounts) > 0
            })
        return result

    def _load_store(self) -> Dict[str, Dict[str, str]]:
        if not self.storage_path.exists():
            return {}
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_store(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self._store, f, indent=2)
