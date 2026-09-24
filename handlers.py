import os
import logging
import requests
import uuid
from models import (
    User,
    FlowSession,
    Appointment,
    Branch,
    Service
)
from messaging import send_reply, send_typing_indicator,build_main_menu
from datetime import date,datetime
from zoneinfo import ZoneInfo
from sqlalchemy import or_, and_
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
logger = logging.getLogger("hair-destination-slotly")


# ==========================================================
# ZERNIO CONFIG
# ==========================================================

ZERNIO_API_KEY = os.getenv("ZERNIO_API_KEY")

ZERNIO_FLOW_ID = os.getenv(
    "ZERNIO_FLOW_ID",
    "1037382505772012"
)

ZERNIO_FLOW_SEND_URL = (
    "https://zernio.com/api/v1/whatsapp/flows/send"
)
BUSINESS_ID = int(os.getenv("BUSINESS_ID", "1"))

# ==========================================================
# GREETINGS
# ==========================================================

GREETING_WORDS = {
    "hi",
    "hie",
    "hello",
    "hey",
    "start",
    "menu"
}

def send_booking_confirmation(
    user_number,
    appointment,
    branch,
    service,
    account_id
):
    date_text = appointment.appointment_date.strftime("%d %B %Y")
    start_text = appointment.start_time.strftime("%I:%M %p").lstrip("0")
    end_text = appointment.end_time.strftime("%I:%M %p").lstrip("0")

    message = (
        "✅ *Appointment Booked Successfully!*\n\n"
        f"📋 Appointment ID: #{appointment.id}\n"
        f"📅 Date: {date_text}\n"
        f"🕒 Time: {start_text} - {end_text}\n"
        f"📍 Branch: {branch.name}\n"
        f"💇 Service: {service.name}\n\n"
        "Thank you for choosing Hair Destination Studio! 💙"
    )

    try:
        send_reply(
            user_number,
            account_id,
            message
        )

        logger.info(
            "[BOOKING CONFIRMATION] Sent | "
            "appointment_id=%s | phone=%s",
            appointment.id,
            user_number
        )

    except Exception:
        logger.exception(
            "[BOOKING CONFIRMATION] Failed | "
            "appointment_id=%s",
            appointment.id
        )
# ==========================================================
# EXTRACT LIST SELECTION
# ==========================================================

def get_selected_option(message: dict):
    """
    Extract the selected list option ID from the
    incoming Zernio webhook payload.
    """

    for key in (
        "selectedId",
        "selected_id",
        "replyId",
        "reply_id"
    ):
        value = message.get(key)

        if value:
            return str(value)

    interactive = message.get("interactive") or {}

    if isinstance(interactive, dict):

        for key in (
            "id",
            "selectedId",
            "selected_id"
        ):
            value = interactive.get(key)

            if value:
                return str(value)

        list_reply = interactive.get("list_reply") or {}

        if isinstance(list_reply, dict):

            value = list_reply.get("id")

            if value:
                return str(value)

    for key in (
        "list_reply",
        "listReply",
        "reply"
    ):
        value = message.get(key)

        if isinstance(value, dict):

            selected_id = value.get("id")

            if selected_id:
                return str(selected_id)

    return None


# ==========================================================
# SEND META FLOW THROUGH ZERNIO
# ==========================================================

def send_booking_flow(
    user_number: str,
    account_id: str,
    db
):
    """
    Sends the published Meta Flow through Zernio.
    """

    if not ZERNIO_API_KEY:

        logger.error(
            "ZERNIO_API_KEY is not configured."
        )

        return False
    
    session_id = uuid.uuid4().hex

    flow_session = (
        db.query(FlowSession)
        .filter(
            FlowSession.phone_number == user_number,
            FlowSession.flow_id == ZERNIO_FLOW_ID,
            FlowSession.completed == False
        )
        .first()
    )

    if flow_session:
        # Reuse existing incomplete session
        session_id = flow_session.session_id

        logger.info(
            "[FLOW SESSION] Reusing existing incomplete session | "
            "session_id=%s | phone=%s",
            session_id,
            user_number
        )

    else:
        # Delete old completed sessions
        db.query(FlowSession).filter(
            FlowSession.phone_number == user_number,
            FlowSession.flow_id == ZERNIO_FLOW_ID,
            FlowSession.completed == True
        ).delete(synchronize_session=False)

        db.commit()

        # Create new session
        session_id = uuid.uuid4().hex

        flow_session = FlowSession(
            session_id=session_id,
            phone_number=user_number,
            flow_id=ZERNIO_FLOW_ID,
            completed=False
        )

        db.add(flow_session)
        db.commit()

        logger.info(
            "[FLOW SESSION] New session created | "
            "session_id=%s | phone=%s",
            session_id,
            user_number
        )
   
    flow_token = f"{ZERNIO_FLOW_ID}:{session_id}"
    logger.info(
        "[FLOW SESSION] session_id=%s | flow_token=%s | phone=%s",
        session_id,
        flow_token,
        user_number
    )
    payload = {

        "accountId": account_id,

        "to": user_number,

        "flow_id": ZERNIO_FLOW_ID,

        "flow_cta": "Book Appointment",
        
        "body": (
            "Please select your branch, service, "
            "appointment date and preferred time."
        ),

        "flow_action": "data_exchange",
        "flow_token": flow_token

    }

    headers = {

        "Authorization": (
            f"Bearer {ZERNIO_API_KEY}"
        ),

        "Content-Type": "application/json"

    }

    try:

        response = requests.post(

            ZERNIO_FLOW_SEND_URL,

            headers=headers,

            json=payload,

            timeout=30

        )

        logger.info(
            "[ZERNIO FLOW] status=%s",
            response.status_code
        )

        logger.info(
            "[ZERNIO FLOW] response=%s",
            response.text
        )

        if response.ok:

            return True

        logger.error(
            "[ZERNIO FLOW] Failed | status=%s",
            response.status_code
        )

        return False

    except requests.RequestException:

        logger.exception(
            "[ZERNIO FLOW] Request failed."
        )

        return False


# ==========================================================
# MAIN MESSAGE HANDLER
# ==========================================================

def process_message(
    user_number: str,
    incoming_msg: str,
    conversation_id: str,
    db,
    webhook_data: dict | None = None
):
    """
    Handles WhatsApp conversation outside the Meta Flow.

    Meta Flow handles:
        Branch
        Service
        Date
        Available Slots
        Slot selection

    Normal WhatsApp menu handles:
        Greeting
        Name registration
        Upcoming Appointments
        Branch & Timings
        Book Appointment -> opens Meta Flow
    """

    webhook_data = webhook_data or {}

    message = webhook_data.get(
        "message",
        {}
    )

    account = webhook_data.get(
        "account",
        {}
    )

    account_id = account.get(
        "id"
    )

    incoming_text = (
        incoming_msg or ""
    ).strip()

    normalized_text = (
        incoming_text.lower()
    )

    # ======================================================
    # GET SELECTED MENU OPTION
    # ======================================================

    selected_option = get_selected_option(
        message
    )
    if not selected_option:

        metadata = webhook_data.get(
            "metadata",
            {}
        )

        if isinstance(metadata, dict):

            interactive_id = metadata.get(
                "interactiveId"
            )

            if interactive_id:

                selected_option = str(
                    interactive_id
                )

    logger.info(
        "[HANDLER] phone=%s | text=%s | selected=%s",
        user_number,
        incoming_text,
        selected_option
    )

    # ======================================================
    # EFFECTIVE INPUT
    #
    # For buttons/lists:
    #     selected_option
    #
    # For normal text:
    #     normalized_text
    # ======================================================

    effective_input = (
        selected_option
        or normalized_text
    )

    # ======================================================
    # GET USER
    # ======================================================

    user = (
        db.query(User)
        .filter(
            User.phone_number == user_number
        )
        .first()
    )

    user_name = (
        user.name
        if user
        else "there"
    )

    # ======================================================
    # GREETING
    # ======================================================

    if normalized_text in GREETING_WORDS:

        if user:

            return build_main_menu(
                user.name
            )
        return build_main_menu("there")
        '''
        return (
            "👋 Welcome to Hair Destination Studio!\n\n"
            "Before we begin,\n"
            "May I know your name?"
        )
        
        '''
        

    # ======================================================
    # UPCOMING APPOINTMENTS
    # ======================================================

    if effective_input == "menu_my_appointments":

        # --------------------------------------------------
        # User does not exist
        # --------------------------------------------------
        india_now = datetime.now(ZoneInfo("Asia/Kolkata"))
        today = india_now.date()
        current_time = india_now.time()


        if not user:

            return (
                "I couldn't find your profile yet.\n\n"
                "Please say Hi to get started."
            )

        # --------------------------------------------------
        # Get business
        # --------------------------------------------------

        business_id = user.business_id

        # --------------------------------------------------
        # Get upcoming appointments
        # --------------------------------------------------

        appointments = (
            db.query(
                Appointment,
                Branch,
                Service
            )
            .join(
                Branch,
                Branch.id == Appointment.branch_id
            )
            .join(
                Service,
                Service.id == Appointment.service_id
            )
            .filter(
                Appointment.user_id == user.id,
                Appointment.business_id == business_id,
                Appointment.status == "booked",
                or_(
                    Appointment.appointment_date > today,
                    and_(
                        Appointment.appointment_date == today,
                        Appointment.start_time >= current_time
                    )
                )
            )
            .order_by(
                Appointment.appointment_date,
                Appointment.start_time
            )
            .all()
        )

        logger.info(
            "[DB] Upcoming appointments | "
            "user_id=%s | rows=%s",
            user.id,
            len(appointments)
        )

        # --------------------------------------------------
        # No appointments
        # --------------------------------------------------

        if not appointments:

            return {
                "message": (
                    "📋 You don't have any "
                    "upcoming appointments."
                ),
                "buttons": [
                    {
                        "title": "🏠 Main Menu",
                        "payload": "menu"
                    }
                ]
            }

        # --------------------------------------------------
        # Build appointment details
        # --------------------------------------------------

        appointment_details = []

        for index, (
            appointment,
            branch,
            service
        ) in enumerate(
            appointments,
            start=1
        ):

            date_text = (
                appointment.appointment_date
                .strftime("%d %B %Y")
            )

            start_text = (
                appointment.start_time
                .strftime("%I:%M %p")
                .lstrip("0")
            )

            end_text = (
                appointment.end_time
                .strftime("%I:%M %p")
                .lstrip("0")
            )

            appointment_details.append(
                f"{index}️⃣ {service.name}\n"
                f"📍 {branch.name}\n"
                f"📅 {date_text}\n"
                f"🕒 {start_text} - {end_text}\n"
                f"🟢 Confirmed"
            )

        return {
            "message": (
                "📋 Your Appointments\n\n"
                + "\n\n".join(
                    appointment_details
                )
            ),
            "buttons": [
                {
                    "title": "🏠 Main Menu",
                    "payload": "menu"
                }
            ]
        }

    # ======================================================
    # BRANCHES & TIMINGS
    # ======================================================

    if effective_input == "menu_branches":

        # --------------------------------------------------
        # Determine business
        # --------------------------------------------------

        business_id = (
            user.business_id
            if user
            else BUSINESS_ID
        )

        # --------------------------------------------------
        # Get branches
        # --------------------------------------------------

        branches = (
            db.query(Branch)
            .filter(
                Branch.business_id == business_id,
                Branch.is_active == True
            )
            .order_by(
                Branch.name
            )
            .all()
        )

        logger.info(
            "[DB] Branches | business_id=%s | rows=%s",
            business_id,
            len(branches)
        )

        if not branches:

            return (
                "❌ No branches are currently available."
            )

        branch_details = []

        for branch in branches:

            branch_info = (
                f"📍 {branch.name}\n\n"
                f"🕒 Working Hours:\n"
                f"Monday - Saturday: "
                f"10:00 AM - 8:00 PM\n\n"
            )

            if branch.address:

                branch_info += (
                    f"📌 Address:\n"
                    f"{branch.address}\n\n"
                )

            if branch.maps_url:

                branch_info += (
                    f"🗺️ Google Maps:\n"
                    f"{branch.maps_url}\n\n"
                )

            branch_details.append(
                branch_info
            )

        return {
            "message": (
                "🏢 Our Branches & Timings\n\n"
                + "\n".join(branch_details)
            ),
            "buttons": [
                {
                    "title": "🏠 Main Menu",
                    "payload": "menu"
                }
            ]
        }

    # ======================================================
    # BOOK APPOINTMENT
    # ======================================================

    if (
        effective_input == "menu_book"
        or normalized_text == "book appointment"
        or normalized_text == "📅 book appointment"
    ):

        if not account_id:

            logger.error(
                "[HANDLER] account.id missing."
            )

            return (
                "Unable to open booking right now. "
                "Please try again."
            )


        #
        send_typing_indicator(conversation_id,account_id)    
        flow_sent = send_booking_flow(
            user_number=user_number,
            account_id=account_id,
            db=db
        )

        if flow_sent:

            # Meta Flow has been sent.
            return None

        return (
            "Sorry, I couldn't open the booking form "
            "right now. Please try again."
        )

    # ======================================================
    # MAIN MENU
    # ======================================================

    if effective_input == "menu":

        return build_main_menu(
            user_name
        )

    # ======================================================
    # FALLBACK
    # ======================================================

    logger.info(
        "[HANDLER] No matching action | "
        "effective_input=%s",
        effective_input
    )

    return build_main_menu(
        user_name
    )