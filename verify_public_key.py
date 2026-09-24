import os
import requests
from dotenv import load_dotenv
from cryptography.hazmat.primitives import serialization

load_dotenv()

PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")

url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/whatsapp_business_encryption"

response = requests.get(
    url,
    headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}
)

print("Status:", response.status_code)
print("Response:", response.text)

if response.status_code != 200:
    exit()

data = response.json().get("data", [])

if not data:
    print("❌ No public key found on Meta")
    exit()

# Meta public key
meta_public_key = data[0]["business_public_key"]

# Load Meta key
meta_key = serialization.load_pem_public_key(
    meta_public_key.encode()
)

# Load local key
with open("public.pem", "rb") as f:
    local_key = serialization.load_pem_public_key(f.read())

# Convert both to same canonical DER format
meta_der = meta_key.public_bytes(
    serialization.Encoding.DER,
    serialization.PublicFormat.SubjectPublicKeyInfo
)

local_der = local_key.public_bytes(
    serialization.Encoding.DER,
    serialization.PublicFormat.SubjectPublicKeyInfo
)

print("\nMETA KEY SHA256:")
import hashlib
print(hashlib.sha256(meta_der).hexdigest())

print("\nLOCAL KEY SHA256:")
print(hashlib.sha256(local_der).hexdigest())

print("\nMATHEMATICAL KEY MATCH:", meta_der == local_der)