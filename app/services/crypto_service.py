"""Simple encryption for credential storage using Fernet (AES-128-CBC + HMAC)."""
import os
from cryptography.fernet import Fernet, InvalidToken

_fernet = None


def _get_fernet():
    """Lazy-load Fernet cipher from ENCRYPTION_KEY env var."""
    global _fernet
    if _fernet is None:
        key = os.environ.get("ENCRYPTION_KEY")
        if not key:
            raise ValueError("ENCRYPTION_KEY not set. Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'")
        _fernet = Fernet(key.encode())
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns empty string if input is empty."""
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a string. Returns empty string if input is empty."""
    if not ciphertext:
        return ""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError("Decryption failed - wrong key or corrupted data")
