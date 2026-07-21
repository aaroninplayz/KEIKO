import hmac
import hashlib
import base64
import json
import time
import os

# NOTE: Auth is bypassed (see dependencies.py). This secret is only used for
# legacy JWT token signing and is never a real secret.  Set JWT_SECRET_KEY in
# your .env file if you re-enable authentication.
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-placeholder-not-a-real-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 86400  # 24 hours

def hash_password(password: str) -> str:
    """
    Zero-dependency password hashing using standard library pbkdf2_hmac.
    Returns: formatted as iterations$salt_hex$key_hex
    """
    iterations = 100000
    salt = os.urandom(16)
    salt_hex = salt.hex()
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    key_hex = key.hex()
    return f"{iterations}${salt_hex}${key_hex}"

def verify_password(password: str, hashed_password: str) -> bool:
    """
    Zero-dependency password verification.
    """
    try:
        parts = hashed_password.split('$')
        if len(parts) != 3:
            return False
        iterations = int(parts[0])
        salt = bytes.fromhex(parts[1])
        key_hex = parts[2]
        key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        return hmac.compare_digest(key.hex(), key_hex)
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: int = ACCESS_TOKEN_EXPIRE_SECONDS) -> str:
    """
    Creates an access token using standard library HMACS.
    """
    to_encode = data.copy()
    expire = int(time.time()) + expires_delta
    to_encode.update({"exp": expire})
    
    header = {"alg": ALGORITHM, "typ": "JWT"}
    
    header_json = json.dumps(header, separators=(',', ':')).encode('utf-8')
    payload_json = json.dumps(to_encode, separators=(',', ':')).encode('utf-8')
    
    header_b64 = base64.urlsafe_b64encode(header_json).rstrip(b'=').decode('utf-8')
    payload_b64 = base64.urlsafe_b64encode(payload_json).rstrip(b'=').decode('utf-8')
    
    signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    signature = hmac.new(SECRET_KEY.encode('utf-8'), signing_input, hashlib.sha256).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b'=').decode('utf-8')
    
    return f"{header_b64}.{payload_b64}.{signature_b64}"

def decode_access_token(token: str) -> dict:
    """
    Decodes and verifies a JWT token. Returns the payload dict or raises ValueError.
    """
    try:
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid token format")
        header_b64, payload_b64, signature_b64 = parts
        
        # Verify signature
        signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
        expected_signature = hmac.new(SECRET_KEY.encode('utf-8'), signing_input, hashlib.sha256).digest()
        expected_signature_b64 = base64.urlsafe_b64encode(expected_signature).rstrip(b'=').decode('utf-8')
        
        if not hmac.compare_digest(signature_b64, expected_signature_b64):
            raise ValueError("Signature verification failed")
        
        # Decode payload
        payload_pad = payload_b64 + "=" * (4 - (len(payload_b64) % 4))
        payload_json = base64.urlsafe_b64decode(payload_pad.encode('utf-8')).decode('utf-8')
        payload = json.loads(payload_json)
        
        # Check expiration
        exp = payload.get("exp")
        if exp is None or int(time.time()) > exp:
            raise ValueError("Token has expired")
            
        return payload
    except Exception as e:
        raise ValueError(f"Invalid token: {e}")
