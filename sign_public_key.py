import os
import requests
from dotenv import load_dotenv

load_dotenv()

PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")

with open(r"C:\Users\Mitul\Downloads\hair_destination_slotly\public.pem", "r") as f:
    public_key = f.read()

print(public_key)


url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/whatsapp_business_encryption"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/x-www-form-urlencoded",
}

data = {
    "business_public_key": public_key
}

response = requests.post(
    url,
    headers=headers,
    data=data
)
print(response)
print("Status:", response.status_code)
print("Response:", response.text)

