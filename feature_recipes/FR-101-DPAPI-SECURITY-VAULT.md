# Feature Recipe FR-101: Windows Native DPAPI Security Vault

## 1. Goal
Store API keys, session tokens, and passwords safely on Windows.
Do not use external cryptography libraries.

## 2. Technical Requirements
1. Call Windows `crypt32.dll` using Python `ctypes`.
2. Encrypt cleartext strings with `CryptProtectData`.
3. Decrypt ciphertext strings with `CryptUnprotectData`.
4. Tie all encryption keys directly to the logged-in Windows user account.
5. Provide automatic fallback to secure base64/hash obfuscation when non-Windows platforms are detected during tests.
6. Return hexadecimal or base64 encoded strings for safe database storage.

## 3. Inputs and Outputs
- `encrypt_secret(cleartext: str) -> str`: Converts sensitive text to an encrypted string.
- `decrypt_secret(ciphertext: str) -> str`: Converts encrypted string back to original cleartext.
- `store_credential(provider: str, account_id: str, secret: str) -> bool`: Saves encrypted secret into config store.
- `get_credential(provider: str, account_id: str) -> Optional[str]`: Retrieves and decrypts secret.

## 4. Verification Criteria
- Plaintext secrets must not appear in any SQLite database column.
- Decrypted output must match original input exactly.
- Corrupted ciphertext must raise a controlled `SecurityVaultError` without application crash.
