import os
import base64
import json

from dotenv import load_dotenv

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


# ==========================================================
# LOAD ENVIRONMENT
# ==========================================================

load_dotenv()

PRIVATE_KEY_PASSWORD = os.getenv("PRIVATE_KEY_PASSWORD")


# ==========================================================
# LOAD RSA PRIVATE KEY
# ==========================================================

with open("/etc/secrets/private.pem", "rb") as f:

    PRIVATE_KEY = serialization.load_pem_private_key(
        f.read(),
        password=(
            PRIVATE_KEY_PASSWORD.encode()
            if PRIVATE_KEY_PASSWORD
            else None
        )
    )

print("Private key loaded successfully.")
print("RSA key size:", PRIVATE_KEY.key_size)
import hashlib

public_key = PRIVATE_KEY.public_key()

public_der = public_key.public_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)

print(hashlib.sha256(public_der).hexdigest())
# ==========================================================
# DECRYPT AES KEY
# ==========================================================

def decrypt_aes_key(
    encrypted_aes_key: str
) -> bytes:

    encrypted_key = base64.b64decode(
        encrypted_aes_key
    )

    aes_key = PRIVATE_KEY.decrypt(
        encrypted_key,

        padding.OAEP(
            mgf=padding.MGF1(
                algorithm=hashes.SHA256()
            ),

            algorithm=hashes.SHA256(),

            label=None
        )
    )

    return aes_key


# ==========================================================
# DECRYPT FLOW DATA
# ==========================================================

def decrypt_flow_data(
    encrypted_flow_data: str,
    aes_key: bytes,
    iv: bytes
) -> dict:

    encrypted_data = base64.b64decode(
        encrypted_flow_data
    )

    # Last 16 bytes = AES-GCM authentication tag
    ciphertext = encrypted_data[:-16]

    auth_tag = encrypted_data[-16:]


    decryptor = Cipher(
        algorithms.AES(aes_key),
        modes.GCM(
            iv,
            auth_tag
        )
    ).decryptor()


    decrypted = (
        decryptor.update(ciphertext)
        + decryptor.finalize()
    )


    return json.loads(
        decrypted.decode("utf-8")
    )


# ==========================================================
# ENCRYPT RESPONSE
# ==========================================================

def encrypt_response(
    response_data: dict,
    aes_key: bytes,
    request_iv: bytes
) -> str:

    # Meta requires response IV to be
    # request IV XOR 0xFF
    response_iv = bytes(
        byte ^ 0xFF
        for byte in request_iv
    )


    plaintext = json.dumps(
        response_data,
        separators=(",", ":")
    ).encode("utf-8")


    encryptor = Cipher(
        algorithms.AES(aes_key),
        modes.GCM(response_iv)
    ).encryptor()


    ciphertext = (
        encryptor.update(plaintext)
        + encryptor.finalize()
    )


    # Append authentication tag
    encrypted_data = (
        ciphertext
        + encryptor.tag
    )


    return base64.b64encode(
        encrypted_data
    ).decode("utf-8")