import base64
import os

from dotenv import load_dotenv
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

load_dotenv()

PRIVATE_KEY_PASSWORD = os.getenv("PRIVATE_KEY_PASSWORD")

# Local testing
with open("private.pem", "rb") as f:
    PRIVATE_KEY = serialization.load_pem_private_key(
        f.read(),
        password=PRIVATE_KEY_PASSWORD.encode()
    )

encrypted_aes_key = (
    "qFuiA50mlaACJgDWDKhlg0xuKuAB4ovA3UpVBMts/"
    "iemYM6Gw9w/2xDhINvFivmFQyNAyKZ8yl6Y+epaVwl2/"
    "G/tEzKgcuURdqxsGgcx503Bm94gO6sIhH2JvkhELoxBnijqbi"
    "oviAdUBihE5tCPLf+1MDDUr9TSe9odw8uziAOM52Y6QbGLW1O1Kl1xYPCJy4Xho/vG/"
    "WPO+t2pbynLfAOwHPv7Xd+mqgHvxJftsK1D0vIa36EvjlXJ7zcuMd6gIOumG8rF6vNZdug9yfnb4rIYTu9Ps2wWQKabLV4wL0LzGobi4EHN/RROB4FjnbdR3lsnwCm4kYij8EWsSkC7Vg=="
)

encrypted_key = base64.b64decode(encrypted_aes_key)

print("RSA key size:", PRIVATE_KEY.key_size)
print("Encrypted AES key length:", len(encrypted_key))

try:
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

    print("RSA DECRYPT: SUCCESS")
    print("AES key length:", len(aes_key))

except Exception as e:
    print("RSA DECRYPT: FAILED")
    print(type(e).__name__)
    print(str(e))