import base64
import hashlib
import os
from typing import Optional

try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None

def _get_default_fernet() -> Optional['Fernet']:
    """Get Fernet instance using AGENTOS_MASTER_KEY from environment."""
    if not Fernet:
        return None
        
    master_key = os.environ.get("AGENTOS_MASTER_KEY")
    if not master_key:
        return None
        
    # Fernet requires a 32-byte url-safe base64-encoded key.
    # We hash the user-provided master key to ensure it fits the format.
    hasher = hashlib.sha256()
    hasher.update(master_key.encode('utf-8'))
    key = base64.urlsafe_b64encode(hasher.digest())
    return Fernet(key)

def is_encrypted(value: str) -> bool:
    """Check if the string starts with the ENC[ header."""
    if not value or not isinstance(value, str):
        return False
    return value.startswith("ENC[") and value.endswith("]")

def encrypt_value(plaintext: str, password: Optional[str] = None) -> str:
    """
    Encrypt a plaintext string.
    Returns format: ENC[encrypted_base64_string]
    If cryptography is not installed or password is not available, returns plaintext.
    """
    if not plaintext:
        return plaintext
        
    if not Fernet:
        return plaintext

    try:
        if password:
            hasher = hashlib.sha256()
            hasher.update(password.encode('utf-8'))
            key = base64.urlsafe_b64encode(hasher.digest())
            f = Fernet(key)
        else:
            f = _get_default_fernet()
            
        if not f:
            return plaintext
            
        token = f.encrypt(plaintext.encode('utf-8'))
        return f"ENC[{token.decode('utf-8')}]"
    except Exception:
        return plaintext

def decrypt_value(ciphertext: str, password: Optional[str] = None) -> str:
    """
    Decrypt an ENC[...] string.
    Returns plaintext, or original string if decryption fails.
    """
    if not is_encrypted(ciphertext):
        return ciphertext
        
    if not Fernet:
        return ciphertext
        
    # Extract the actual token inside ENC[...]
    token = ciphertext[4:-1].encode('utf-8')

    try:
        if password:
            hasher = hashlib.sha256()
            hasher.update(password.encode('utf-8'))
            key = base64.urlsafe_b64encode(hasher.digest())
            f = Fernet(key)
        else:
            f = _get_default_fernet()
            
        if not f:
            return ciphertext
            
        return f.decrypt(token).decode('utf-8')
    except Exception:
        # Decryption failed (wrong key, bad format)
        return ciphertext
