import os
import firebase_admin
from firebase_admin import credentials, messaging
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("hair-destination-slotly")


def init_firebase():
    if firebase_admin._apps:
        return firebase_admin.get_app()

    credential_path = "/etc/secrets/firebase-service-account.json"

    if not os.path.exists(credential_path):
        raise RuntimeError(
            f"Firebase service account file not found: {credential_path}"
        )

    cred = credentials.Certificate(credential_path)

    return firebase_admin.initialize_app(cred)


def send_admin_notification(
    token,
    appointment_id,
    user_name,
    service_name,
    branch_name,
    appointment_date,
    start_time
):
    try:
        if not token:
            return

        init_firebase()

        message = messaging.Message(
            token=token,
            notification=messaging.Notification(
                title="New Appointment Booked",
                body=(
                    f"{user_name} • {service_name} • {branch_name} • "
                    f"{appointment_date} "
                    f"{start_time}"
                )
            ),
            data={
                "type": "new_appointment",
                "appointment_id": str(appointment_id),
            }
        )

        messaging.send(message)

        logger.info(
            "[FCM] Notification sent | appointment_id=%s",
            appointment_id
        )

    except Exception:
        logger.exception(
            "[FCM] Background notification failed"
        )