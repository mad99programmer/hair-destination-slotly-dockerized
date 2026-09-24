import os
import requests
import time
import logging

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("slotly")

ZERNIO_API_KEY = os.getenv("ZERNIO_API_KEY")

TEST_MODE = (
    os.getenv("TEST_MODE", "false").lower() == "true"
)


# ==========================================================
# MAIN MENU
# ==========================================================

def build_main_menu(user_name):

    return {
        "interactive": {
            "type": "list",

            "body": {
                "text": (
                    f"👋 Welcome {user_name}!\n\n"
                    "How can we help you today?"
                )
            },

            "action": {
                "button": "Select Option",

                "sections": [
                    {
                        "title": "Main Menu",

                        "rows": [
                            {
                                "id": "menu_book",
                                "title": "📅 Book Appointment"
                            },
                            {
                                "id": "menu_my_appointments",
                                "title": "📋 Upcoming Appointments"
                            },
                            {
                                "id": "menu_branches",
                                "title": "🕒 Branches & Timings"
                            }
                        ]
                    }
                ]
            }
        }
    }


# ==========================================================
# SEND WHATSAPP MESSAGE USING ZERNIO
# ==========================================================

def send_reply(
    conversation_id: str,
    account_id: str,
    message
):

    if TEST_MODE:

        print("\nBOT REPLY:")
        print(message)

        return True


    # ------------------------------------------------------
    # BUILD REQUEST BODY
    # ------------------------------------------------------

    if isinstance(message, str):

        body = {
            "accountId": account_id,
            "message": message
        }

    else:

        body = {
            "accountId": account_id
        }

        if "message" in message:
            body["message"] = message["message"]

        if "buttons" in message:
            body["buttons"] = message["buttons"]

        if "interactive" in message:
            body["interactive"] = message["interactive"]


    # ------------------------------------------------------
    # ZERNIO MESSAGE ENDPOINT
    # ------------------------------------------------------

    url = (
        "https://zernio.com/api/v1/inbox/conversations/"
        f"{conversation_id}/messages"
    )


    headers = {
        "Authorization": f"Bearer {ZERNIO_API_KEY}",
        "Content-Type": "application/json"
    }


    # ------------------------------------------------------
    # RETRIES
    # ------------------------------------------------------

    max_retries = 3


    for attempt in range(max_retries):

        try:

            response = requests.post(
                url,
                headers=headers,
                json=body,
                timeout=30
            )


            logger.info(
                "[ZERNIO] Attempt %d | status=%s",
                attempt + 1,
                response.status_code
            )


            if response.status_code in [200, 201]:

                logger.info(
                    "[ZERNIO] Message sent successfully"
                )

                return True


            # ------------------------------------------------
            # RETRY TRANSIENT ERRORS
            # ------------------------------------------------

            if response.status_code in [
                500,
                502,
                503,
                504
            ]:

                if attempt < max_retries - 1:

                    wait = 2 ** attempt

                    logger.warning(
                        "[ZERNIO] Transient error | "
                        "retry_in=%d sec",
                        wait
                    )

                    time.sleep(wait)

                    continue


            logger.error(
                "[ZERNIO] Message failed | "
                "status=%s | response=%s",
                response.status_code,
                response.text
            )

            return False


        except requests.exceptions.Timeout:

            logger.error(
                "[ZERNIO] Request timed out | attempt=%d",
                attempt + 1
            )


        except requests.exceptions.ConnectionError:

            logger.error(
                "[ZERNIO] Connection error | attempt=%d",
                attempt + 1
            )


        except requests.exceptions.RequestException as e:

            logger.exception(
                "[ZERNIO] Request exception | error=%s",
                e
            )


        # ----------------------------------------------------
        # RETRY AFTER EXCEPTION
        # ----------------------------------------------------

        if attempt < max_retries - 1:

            wait = 2 ** attempt

            time.sleep(wait)


    logger.error(
        "[ZERNIO] Failed to send message after all retries"
    )

    return False


def send_typing_indicator(conversation_id: str, account_id: str):
    try:
        url = (
            f"https://api.zernio.com/v1/inbox/conversations/"
            f"{conversation_id}/typing"
        )

        headers = {
            "Authorization": f"Bearer {ZERNIO_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "accountId": account_id
        }

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=5
        )

        logger.info(
            "[ZERNIO] Typing indicator | status=%s | response=%s",
            response.status_code,
            response.text
        )

    except Exception:
        logger.exception("[ZERNIO] Typing indicator failed")
