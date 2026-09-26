import re
import os
import requests
from dotenv import load_dotenv
from firebase_service import send_admin_notification
import json
import logging
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, date, timedelta
from fastapi import FastAPI, Request, Depends
from fastapi.responses import PlainTextResponse
from database import engine
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from admin_routes import router as admin_router
from auth_routes import router as auth_router
from models import (
    Base,
    User,
    Appointment,
    Branch,
    Service,
    FlowSession,
    Admin
)
from sqlalchemy import text
from zoneinfo import ZoneInfo
from db_queries import (
    get_branches,
    get_services,
    get_available_slots
    
)
from sqlalchemy.orm import Session
from database import engine, SessionLocal
from flow_crypto import (
    decrypt_aes_key,
    decrypt_flow_data,
    encrypt_response
)
from messaging import send_reply, send_typing_indicator
from handlers import process_message
import time
load_dotenv()

BUSINESS_ID = int(
    os.getenv("BUSINESS_ID", "1")
)
notification_executor = ThreadPoolExecutor(max_workers=4)
# ==========================================================
# LOGGING
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(
    "hair-destination-slotly"
)

# ==========================================================
# FASTAPI
# ==========================================================

def parse_selected_slot(selected_slot: str):
    """
    Convert display slot into start_time and end_time.

    Example:
        "02:00 PM - 03:00 PM 🪑 🪑 🪑"

    Returns:
        (datetime.time(14, 0), datetime.time(15, 0))
    """

    if not selected_slot:
        raise ValueError("selected_slot is empty")

    match = re.match(
        r"^\s*(\d{1,2}:\d{2}\s*[AP]M)"
        r"\s*-\s*"
        r"(\d{1,2}:\d{2}\s*[AP]M)",
        selected_slot,
        re.IGNORECASE
    )

    if not match:
        raise ValueError(
            f"Invalid selected slot format: {selected_slot}"
        )

    start_str = match.group(1)
    end_str = match.group(2)

    start_time = datetime.strptime(
        start_str.upper(),
        "%I:%M %p"
    ).time()

    end_time = datetime.strptime(
        end_str.upper(),
        "%I:%M %p"
    ).time()

    return start_time, end_time


print("Server datetime :", datetime.now())
print("UTC datetime    :", datetime.now(timezone.utc))
print("IST datetime    :", datetime.now(ZoneInfo("Asia/Kolkata")))

# ==========================================================
# CREATE DATABASE TABLES
# ==========================================================

Base.metadata.create_all(
    bind=engine
)

logger.info(
    "Database tables checked successfully."
)

#handling double message from zernio 
from collections import OrderedDict
import time

_processed_messages = OrderedDict()
_DEDUPE_TTL_SECONDS = 300  # 5 min

def is_duplicate(message_id: str) -> bool:
    now = time.time()
    expired = [mid for mid, ts in _processed_messages.items() if now - ts > _DEDUPE_TTL_SECONDS]
    for mid in expired:
        _processed_messages.pop(mid, None)
    if message_id in _processed_messages:
        return True
    _processed_messages[message_id] = now
    return False

#temporary admin creation


from models import Admin
from security import hash_password

db = SessionLocal()

try:
    admin = db.query(Admin).filter(
        Admin.username == "admin"
    ).first()

    if not admin:
        admin = Admin(
            username="admin",
            password_hash=hash_password("Admin@123")
        )

        db.add(admin)
        db.commit()

finally:
    db.close()

app = FastAPI(
    title="Hair Destination Slotly"
)



# ==========================================================
# ADMIN FRONTEND PAGES
# ==========================================================

@app.get("/admin/login/")
async def admin_login_page():
    return FileResponse("admin/login.html")


@app.get("/admin/dashboard/")
async def admin_dashboard_page():
    return FileResponse("admin/dashboard.html")


@app.get("/admin/appointments/")
async def admin_appointments_page():
    return FileResponse("admin/appointments.html")

@app.get("/admin/add-appointments/")
async def admin_appointments_page():
    return FileResponse("admin/add-appointment.html")

app.include_router(admin_router)
app.include_router(auth_router)
app.mount("/admin", StaticFiles(directory="admin", html=True), name="admin")


# =========================
# DATABASE SESSION
# =========================
def get_db():

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


# ==========================================================
# HEALTH CHECK
# ==========================================================

@app.get("/")
async def health_check():

    return {
        "status": "Hair Destination Slotly is alive"
    }

# ==========================================================
# INIT HANDLER
# ==========================================================
def handle_init(flow_token=""):

    from database import SessionLocal

    db = SessionLocal()

    try:

        # --------------------------------------------------
        # RESOLVE USER FROM FLOW TOKEN
        # --------------------------------------------------

        user_name = ""

        session_id = (
            flow_token.split(":", 1)[1]
            if ":" in flow_token
            else flow_token
        )

        if session_id:

            flow_session = (
                db.query(FlowSession)
                .filter(
                    FlowSession.session_id == session_id
                )
                .first()
            )

            if flow_session:

                user = (
                    db.query(User)
                    .filter(
                        User.phone_number == flow_session.phone_number
                    )
                    .first()
                )

                if user:
                    user_name = user.name or ""

                    logger.info(
                        "Existing user found for Flow | "
                        "user_id=%s | name=%s",
                        user.id,
                        user.name
                    )

                else:
                    logger.info(
                        "New user Flow | phone=%s",
                        flow_session.phone_number
                    )

            else:
                logger.warning(
                    "FlowSession not found during INIT | session_id=%s",
                    session_id
                )

        # --------------------------------------------------
        # GET BRANCHES
        # --------------------------------------------------

        branches = get_branches(db)

        # --------------------------------------------------
        # GET SERVICES
        # --------------------------------------------------

        services = get_services(db)

        # --------------------------------------------------
        # BUILD RESPONSE
        # --------------------------------------------------
        now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))

        if now_ist.hour >= 20:
            min_date_obj = date.today() + timedelta(days=1)
        else:
            min_date_obj = date.today()

        max_date_obj = min_date_obj + timedelta(days=60)

        min_date = min_date_obj.isoformat()
        max_date = max_date_obj.isoformat()

        response_data = {

            "screen": "BOOKING_DETAILS",

            "data": {

                "name": user_name,

                "branches": branches,

                "services": services,

                "min_date": min_date,

                "max_date": max_date

            }

        }

        logger.info(
            "INIT loaded %d branches, %d services | name=%s",
            len(branches),
            len(services),
            user_name
        )

        return response_data

    finally:

        db.close()

# =========================
# Zernio WEBHOOK
# =========================
@app.post("/webhook/zernio")
async def webhook_zernio(request: Request, db: Session = Depends(get_db)):
    webhook_start = time.perf_counter()
    payload = await request.json()

    
    '''
    print("RAW PAYLOAD:")
        print(
            json.dumps(
                payload,
                indent=4,
                ensure_ascii=False
            )
        )
    '''
    
    logger.info(
        "[WEBHOOK] Received | event=%s",
        payload.get("event")
    )

    if payload.get("event") == "message.received":
        message = payload.get("message", {})
        account = payload.get("account", {})
        message_id = message.get("id")
        #if message_id and is_duplicate(message_id):
        #    return {"status": "duplicate, skipped"}

        user_number = message.get("sender", {}).get("phoneNumber")
        incoming_msg = message.get("text", "").strip()
        conversation_id = message.get("conversationId")
        account_id = account.get("id")
        if conversation_id:
            send_typing_indicator(conversation_id,account_id)
        process_start = time.perf_counter()
        reply = process_message(user_number, incoming_msg, conversation_id,db,webhook_data=payload)
        process_time = (
            time.perf_counter() - process_start
        ) * 1000

        logger.info(
            "[PROCESS] Completed | time=%.2f ms",
            process_time
        )
        send_start = time.perf_counter()
        print("CONVERSATION ID:", conversation_id)
        print("ACCOUNT ID:", account_id)
        if reply is not None:
            send_reply(conversation_id, account_id, reply)
        else:
            logger.info("[ZERNIO] No text reply required | Flow already sent")
        send_time = (
            time.perf_counter() - send_start
        ) * 1000
        logger.info(
            "[ZERNIO] Reply completed | time=%.2f ms",
            send_time
        )

        total_time = (
            time.perf_counter() - webhook_start
        ) * 1000

        logger.info(
            "[WEBHOOK] Completed | total=%.2f ms",
            total_time
        )

    return {"status": "ok"}

@app.post("/webhook/whatsapp-flow")
async def whatsapp_flow(
    request: Request
):
    try:

        # ==================================================
        # RECEIVE REQUEST
        # ==================================================

        body = await request.json()

        logger.info(
            "\n%s\nWHATSAPP FLOW REQUEST\n%s",
            "=" * 60,
            "=" * 60
        )

        logger.info(
            json.dumps(
                body,
                indent=2,
                ensure_ascii=False
            )
        )

        # ==================================================
        # GET ENCRYPTED VALUES
        # ==================================================

        encrypted_flow_data = body[
            "encrypted_flow_data"
        ]

        encrypted_aes_key = body[
            "encrypted_aes_key"
        ]

        initial_vector = body[
            "initial_vector"
        ]

        # ==================================================
        # DECODE INITIAL VECTOR
        # ==================================================

        iv = base64.b64decode(
            initial_vector
        )

        # ==================================================
        # DECRYPT AES KEY
        # ==================================================

        encrypted_key_bytes = base64.b64decode(
            encrypted_aes_key
        )

        logger.info(
            "RSA DEBUG | ciphertext_len=%d",
            len(encrypted_key_bytes)
        )

        try:

            aes_key = decrypt_aes_key(
                encrypted_aes_key
            )

            logger.info(
                "RSA DEBUG | decrypt SUCCESS | aes_len=%d",
                len(aes_key)
            )

        except Exception:

            logger.exception(
                "RSA DEBUG | decrypt FAILED"
            )

            raise

        # ==================================================
        # DECRYPT FLOW DATA
        # ==================================================

        logger.info(
            "FLOW DEBUG | encrypted_flow_data_len=%d | iv_len=%d",
            len(base64.b64decode(encrypted_flow_data)),
            len(iv)
        )

        decrypted_data = decrypt_flow_data(
            encrypted_flow_data,
            aes_key,
            iv
        )

        logger.info(
            "\nDECRYPTED DATA:\n%s",
            json.dumps(
                decrypted_data,
                indent=2,
                ensure_ascii=False
            )
        )

        # ==================================================
        # GET ACTION / SCREEN
        # ==================================================

        action = decrypted_data.get(
            "action"
        )

        current_screen = decrypted_data.get(
            "screen"
        )

        logger.info(
            "ACTION: %s | SCREEN: %s",
            action,
            current_screen
        )

        # ==================================================
        # INIT
        # ==================================================

        if action == "INIT":

            logger.info(
                "Handling INIT..."
            )

            flow_token = decrypted_data.get(
                "flow_token",
                ""
            )

            response_data = handle_init(
                flow_token
            )

        # ==================================================
        # PING
        # ==================================================

        elif action == "ping":

            logger.info(
                "Handling PING..."
            )

            response_data = {
                "data": {
                    "status": "active"
                }
            }

        # ==================================================
        # DATA EXCHANGE
        # ==================================================

        elif action == "data_exchange":

            logger.info(
                "Handling DATA_EXCHANGE..."
            )

            data = decrypted_data.get(
                "data",
                {}
            )

            # ==================================================
            # GET DATA
            # ==================================================

            name = data.get(
                "name"
            )

            branch_id = data.get(
                "branch_id"
            )

            service_id = data.get(
                "service_id"
            )

            appointment_date = data.get(
                "date"
            )

            selected_slot = data.get(
                "selected_slot"
            )

            branch_name = data.get(
                "branch"
            )

            service_name = data.get(
                "service"
            )

            logger.info(
                "Flow data | "
                "screen=%s | "
                "name=%s | "
                "branch_id=%s | "
                "service_id=%s | "
                "date=%s | "
                "selected_slot=%s | "
                "branch=%s | "
                "service=%s",
                current_screen,
                name,
                branch_id,
                service_id,
                appointment_date,
                selected_slot,
                branch_name,
                service_name
            )

            # ==================================================
            # BOOKING DETAILS
            #
            # Check availability
            #
            # BOOKING IS NOT CREATED HERE
            # ==================================================

            if current_screen == "BOOKING_DETAILS":

                logger.info(
                    "Checking availability from BOOKING_DETAILS..."
                )

                # ------------------------------------------
                # VALIDATE REQUIRED VALUES
                # ------------------------------------------

                if (
                    not branch_id
                    or not service_id
                    or not appointment_date
                ):

                    logger.warning(
                        "Missing booking data."
                    )

                    response_data = {
                        "screen": "BOOKING_DETAILS",
                        "data": {}
                    }

                else:

                    from database import SessionLocal

                    db = SessionLocal()

                    try:

                        # ------------------------------------------
                        # CONVERT IDS
                        # ------------------------------------------

                        branch_id = int(
                            branch_id
                        )

                        service_id = int(
                            service_id
                        )

                        # ------------------------------------------
                        # CONVERT DATE
                        # ------------------------------------------

                        appointment_date = datetime.strptime(
                            appointment_date,
                            "%Y-%m-%d"
                        ).date()

                        logger.info(
                            "Checking availability | "
                            "branch_id=%s | date=%s",
                            branch_id,
                            appointment_date
                        )

                        # ------------------------------------------
                        # VALIDATE BRANCH
                        # ------------------------------------------

                        branch = (
                            db.query(Branch)
                            .filter(
                                Branch.id == branch_id,
                                Branch.business_id == BUSINESS_ID,
                                Branch.is_active == True
                            )
                            .first()
                        )

                        if not branch:

                            logger.warning(
                                "Invalid branch_id=%s",
                                branch_id
                            )

                            response_data = {
                                "screen": "BOOKING_DETAILS",
                                "data": {}
                            }

                        else:

                            # ------------------------------------------
                            # VALIDATE SERVICE
                            # ------------------------------------------

                            service = (
                                db.query(Service)
                                .filter(
                                    Service.id == service_id,
                                    Service.business_id == BUSINESS_ID,
                                    Service.is_active == True
                                )
                                .first()
                            )

                            if not service:

                                logger.warning(
                                    "Invalid service_id=%s",
                                    service_id
                                )

                                response_data = {
                                    "screen": "BOOKING_DETAILS",
                                    "data": {}
                                }

                            else:

                                # ==================================================
                                # RESOLVE USER FROM FLOW SESSION
                                # ==================================================

                                flow_token = decrypted_data.get(
                                    "flow_token",
                                    ""
                                )

                                session_id = (
                                    flow_token.split(":", 1)[1]
                                    if ":" in flow_token
                                    else flow_token
                                )

                                logger.info(
                                    "Resolving FlowSession for early booking check | "
                                    "session_id=%s",
                                    session_id
                                )

                                flow_session = (
                                    db.query(FlowSession)
                                    .filter(
                                        FlowSession.session_id == session_id
                                    )
                                    .first()
                                )

                                if not flow_session:

                                    logger.error(
                                        "FlowSession not found | session_id=%s",
                                        session_id
                                    )

                                    response_data = {
                                        "screen": "BOOKING_DETAILS",
                                        "data": {}
                                    }

                                else:

                                    user_number = (
                                        flow_session.phone_number
                                    )

                                    logger.info(
                                        "Early booking check | "
                                        "phone=%s | date=%s",
                                        user_number,
                                        appointment_date
                                    )

                                    # ==================================================
                                    # CHECK IF USER ALREADY HAS APPOINTMENT
                                    # ON THIS DATE
                                    # ==================================================

                                    existing_appointment = (
                                        db.query(Appointment)
                                        .join(
                                            User,
                                            Appointment.user_id == User.id
                                        )
                                        .filter(
                                            User.phone_number == user_number,
                                            Appointment.appointment_date == appointment_date,
                                            Appointment.status == "booked"
                                        )
                                        .first()
                                    )

                                    logger.info(
                                        "Early booking check result | "
                                        "appointment_id=%s",
                                        (
                                            existing_appointment.id
                                            if existing_appointment
                                            else None
                                        )
                                    )

                                    # ==================================================
                                    # USER ALREADY BOOKED
                                    # ==================================================

                                    if existing_appointment:

                                        logger.warning(
                                            "USER ALREADY BOOKED ON DATE | "
                                            "phone=%s | date=%s | appointment_id=%s",
                                            user_number,
                                            appointment_date,
                                            existing_appointment.id
                                        )

                                        response_data = {
                                            "version": "3.0",
                                            "screen": "USER_ALREADY_BOOKED",
                                            "data": {
                                                "date": (
                                                    existing_appointment
                                                    .appointment_date
                                                    .strftime("%d %B %Y")
                                                ),
                                                "time": (
                                                    f"{existing_appointment.start_time.strftime('%I:%M %p').lstrip('0')} - "
                                                    f"{existing_appointment.end_time.strftime('%I:%M %p').lstrip('0')}"
                                                ),
                                                "branch": branch.name,
                                                "service": service.name
                                            }
                                        }

                                    # ==================================================
                                    # NO EXISTING APPOINTMENT
                                    # CONTINUE WITH NORMAL SLOT FLOW
                                    # ==================================================

                                    else:

                                        # ------------------------------------------
                                        # GET AVAILABLE SLOTS
                                        # ------------------------------------------

                                        available_slots = get_available_slots(
                                            db=db,
                                            branch_id=branch_id,
                                            slot_date=appointment_date
                                        )

                                        logger.info(
                                            "Backend returned %d available slots.",
                                            len(available_slots)
                                        )

                                        # ------------------------------------------
                                        # RAW SLOT LOG
                                        # ------------------------------------------

                                        logger.info(
                                            "AVAILABLE SLOTS RAW:\n%s",
                                            json.dumps(
                                                [
                                                    str(item)
                                                    for item in available_slots
                                                ],
                                                indent=2
                                            )
                                        )

                                        # ------------------------------------------
                                        # BUILD FLOW OPTIONS
                                        # ------------------------------------------

                                        slots = []

                                        now_ist = datetime.now(
                                            ZoneInfo("Asia/Kolkata")
                                        )

                                        today_ist = now_ist.date()

                                        for item in available_slots:

                                            # --------------------------------------
                                            # GET SLOT DATA
                                            # --------------------------------------

                                            start_time = item[
                                                "start_time"
                                            ]

                                            end_time = item[
                                                "end_time"
                                            ]

                                            remaining = item[
                                                "remaining"
                                            ]

                                            # --------------------------------------
                                            # HIDE PAST SLOTS FOR TODAY
                                            # --------------------------------------

                                            if appointment_date == today_ist:

                                                if start_time <= now_ist.time():
                                                    continue

                                            # --------------------------------------
                                            # SAFETY
                                            # --------------------------------------

                                            if remaining <= 0:
                                                continue

                                            # --------------------------------------
                                            # FORMAT TIME
                                            # --------------------------------------

                                            start = start_time.strftime(
                                                "%I:%M %p"
                                            )

                                            end = end_time.strftime(
                                                "%I:%M %p"
                                            )

                                            # --------------------------------------
                                            # DISPLAY SLOT
                                            # --------------------------------------

                                            display_title = (
                                                f"{start} - {end}   "
                                                f"{'🪑 ' * remaining}"
                                            ).strip()

                                            slots.append({
                                                "id": display_title,
                                                "title": display_title
                                            })

                                        # ------------------------------------------
                                        # SESSION RESPONSE
                                        # ------------------------------------------

                                        response_data = {
                                            "version": "3.0",
                                            "screen": "SESSION",
                                            "data": {
                                                "name": name,
                                                "branch_id": str(
                                                    branch_id
                                                ),
                                                "service_id": str(
                                                    service_id
                                                ),
                                                "branch": branch.name,
                                                "service": service.name,
                                                "date": (
                                                    appointment_date.isoformat()
                                                ),
                                                "available_slots": slots
                                            }
                                        }

                                        logger.info(
                                            "Returning %d slots to SESSION.",
                                            len(slots)
                                        )

                                        # ------------------------------------------
                                        # NO SLOTS
                                        # ------------------------------------------

                                        if not slots:

                                            logger.warning(
                                                "No available slots found."
                                            )

                    except Exception:

                        db.rollback()

                        logger.exception(
                            "Availability check failed."
                        )

                        response_data = {
                            "screen": "BOOKING_DETAILS",
                            "data": {}
                        }

                    finally:

                        db.close()

            # ==================================================
            # BOOKING CONFIRMATION
            #
            # ONLY HERE APPOINTMENT IS CREATED
            # ==================================================

            elif current_screen == "BOOKING_CONFIRMATION":

                logger.info(
                    "FINAL BOOKING CONFIRMATION RECEIVED."
                )

                logger.info(
                    "Selected slot = %s",
                    selected_slot
                )

                from database import SessionLocal

                db = SessionLocal()

                try:

                    # ==================================================
                    # RESOLVE USER FROM FLOW TOKEN
                    # ==================================================

                    flow_token = decrypted_data.get(
                        "flow_token",
                        ""
                    )

                    session_id = (
                        flow_token.split(":", 1)[1]
                        if ":" in flow_token
                        else flow_token
                    )

                    logger.info(
                        "Resolving FlowSession | session_id=%s",
                        session_id
                    )

                    flow_session = (
                        db.query(FlowSession)
                        .filter(
                            FlowSession.session_id == session_id
                        )
                        .first()
                    )

                    if not flow_session:

                        logger.error(
                            "FlowSession not found | session_id=%s",
                            session_id
                        )

                        raise ValueError(
                            f"FlowSession not found: {session_id}"
                        )

                    user_number = flow_session.phone_number

                    logger.info(
                        "FlowSession resolved | "
                        "session_id=%s | phone=%s",
                        session_id,
                        user_number
                    )

                    # ==================================================
                    # VALIDATE REQUIRED DATA
                    # ==================================================

                    if (
                        not name
                        or not branch_id
                        or not service_id
                        or not appointment_date
                        or not selected_slot
                    ):

                        logger.warning(
                            "Incomplete booking data received."
                        )

                        response_data = {
                            "screen": "BOOKING_DETAILS",
                            "data": {}
                        }

                    else:

                        # ==================================================
                        # CONVERT IDS / DATE
                        # ==================================================

                        branch_id = int(
                            branch_id
                        )

                        service_id = int(
                            service_id
                        )

                        appointment_date = datetime.strptime(
                            appointment_date,
                            "%Y-%m-%d"
                        ).date()

                        # ==================================================
                        # PARSE DISPLAY SLOT
                        #
                        # Example:
                        # 02:00 PM - 03:00 PM 🪑 🪑 🪑
                        # ==================================================

                        try:

                            start_time, end_time = parse_selected_slot(
                                selected_slot
                            )

                            logger.info(
                                "Parsed selected slot | "
                                "selected_slot=%s | "
                                "start=%s | end=%s",
                                selected_slot,
                                start_time,
                                end_time
                            )

                        except ValueError:

                            logger.error(
                                "Invalid selected_slot format: %s",
                                selected_slot
                            )

                            response_data = {
                                "screen": "BOOKING_CONFIRMATION",
                                "data": {}
                            }

                            raise

                        # ==================================================
                        # VALIDATE BRANCH
                        # ==================================================

                        branch = (
                            db.query(Branch)
                            .filter(
                                Branch.id == branch_id,
                                Branch.business_id == BUSINESS_ID,
                                Branch.is_active == True
                            )
                            .first()
                        )

                        if not branch:

                            logger.warning(
                                "Invalid branch_id=%s",
                                branch_id
                            )

                            response_data = {
                                "screen": "BOOKING_DETAILS",
                                "data": {}
                            }

                        else:

                            # ==================================================
                            # VALIDATE SERVICE
                            # ==================================================

                            service = (
                                db.query(Service)
                                .filter(
                                    Service.id == service_id,
                                    Service.business_id == BUSINESS_ID,
                                    Service.is_active == True
                                )
                                .first()
                            )

                            if not service:

                                logger.warning(
                                    "Invalid service_id=%s",
                                    service_id
                                )

                                response_data = {
                                    "screen": "BOOKING_DETAILS",
                                    "data": {}
                                }

                            else:

                                # ==================================================
                                # LOCK THIS EXACT BOOKING SLOT
                                # ==================================================

                                lock_key = (
                                    f"{branch_id}:"
                                    f"{appointment_date.isoformat()}:"
                                    f"{start_time}"
                                )

                                db.execute(
                                    text(
                                        "SELECT pg_advisory_xact_lock("
                                        "hashtext(:lock_key))"
                                    ),
                                    {
                                        "lock_key": lock_key
                                    }
                                )

                                logger.info(
                                    "Booking slot locked | key=%s",
                                    lock_key
                                )

                                # ==================================================
                                # CHECK SLOT CAPACITY
                                # ==================================================

                                booked_count = (
                                    db.query(Appointment)
                                    .filter(
                                        Appointment.branch_id == branch_id,
                                        Appointment.appointment_date == appointment_date,
                                        Appointment.start_time == start_time,
                                        Appointment.status == "booked"
                                    )
                                    .count()
                                )

                                logger.info(
                                    "Booking validation | "
                                    "branch=%s | date=%s | "
                                    "start=%s | booked=%s | capacity=%s",
                                    branch_id,
                                    appointment_date,
                                    start_time,
                                    booked_count,
                                    branch.capacity
                                )

                                # ==================================================
                                # SLOT NO LONGER AVAILABLE
                                # ==================================================

                                if booked_count >= branch.capacity:

                                    logger.warning(
                                        "Selected slot is no longer available."
                                    )

                                    response_data = {
                                        "version": "3.0",
                                        "screen": "BOOKING_FAILURE",
                                        "data": {
                                            "message": (
                                                "Sorry, this slot has just "
                                                "been booked by someone else."
                                            )
                                        }
                                    }

                                else:

                                    # ==================================================
                                    # FIND / CREATE USER
                                    # ==================================================

                                    user = (
                                        db.query(User)
                                        .filter(
                                            User.phone_number == user_number
                                        )
                                        .first()
                                    )

                                    if user:

                                        logger.info(
                                            "Existing user found | "
                                            "user_id=%s | phone=%s",
                                            user.id,
                                            user_number
                                        )

                                        # Update name
                                        user.name = name

                                        # Keep business association current
                                        user.business_id = BUSINESS_ID

                                    else:

                                        logger.info(
                                            "Creating new user | phone=%s",
                                            user_number
                                        )

                                        user = User(
                                            business_id=BUSINESS_ID,
                                            phone_number=user_number,
                                            name=name,
                                            is_active=True
                                        )

                                        db.add(
                                            user
                                        )

                                        # Get generated user.id
                                        db.flush()

                                    # ==================================================
                                    # FINAL SAFETY CHECK:
                                    # USER ALREADY BOOKED ON THIS DATE
                                    # ==================================================

                                    existing_appointment = (
                                        db.query(Appointment)
                                        .filter(
                                            Appointment.user_id == user.id,
                                            Appointment.appointment_date == appointment_date,
                                            Appointment.status == "booked"
                                        )
                                        .first()
                                    )

                                    if existing_appointment:

                                        logger.warning(
                                            "USER ALREADY BOOKED | "
                                            "user_id=%s | date=%s | appointment_id=%s",
                                            user.id,
                                            appointment_date,
                                            existing_appointment.id
                                        )

                                        response_data = {
                                            "version": "3.0",
                                            "screen": "USER_ALREADY_BOOKED",
                                            "data": {
                                                "date": (
                                                    existing_appointment
                                                    .appointment_date
                                                    .strftime("%d %B %Y")
                                                ),
                                                "time": (
                                                    f"{existing_appointment.start_time.strftime('%I:%M %p').lstrip('0')} - "
                                                    f"{existing_appointment.end_time.strftime('%I:%M %p').lstrip('0')}"
                                                ),
                                                "branch": branch.name,
                                                "service": service.name
                                            }
                                        }

                                    else:

                                        # ==================================================
                                        # CREATE APPOINTMENT
                                        # ==================================================

                                        appointment = Appointment(

                                            user_id=user.id,

                                            business_id=BUSINESS_ID,

                                            branch_id=branch_id,

                                            service_id=service_id,

                                            branch_slot_id=None,

                                            appointment_date=appointment_date,

                                            start_time=start_time,

                                            end_time=end_time,

                                            status="booked"
                                        )

                                        db.add(
                                            appointment
                                        )

                                        db.commit()

                                        db.refresh(
                                            appointment
                                        )

                                        flow_session.completed = True

                                        flow_session.completed_at = (
                                            datetime.now(timezone.utc)
                                        )

                                        db.commit()

                                        db.refresh(
                                            appointment
                                        )

                                        logger.info(
                                            "APPOINTMENT BOOKED SUCCESSFULLY | "
                                            "appointment_id=%s | "
                                            "user_id=%s | "
                                            "phone=%s | "
                                            "branch=%s | "
                                            "service=%s | "
                                            "date=%s | "
                                            "start=%s | "
                                            "end=%s",
                                            appointment.id,
                                            user.id,
                                            user_number,
                                            branch_id,
                                            service_id,
                                            appointment_date,
                                            start_time,
                                            end_time
                                        )

                                        # ==================================================
                                        # FCM NOTIFICATION
                                        # ==================================================

                                        admin = (
                                            db.query(Admin)
                                            .filter(
                                                Admin.is_active == True,
                                                Admin.fcm_token.isnot(None)
                                            )
                                            .first()
                                        )

                                        if admin and admin.fcm_token:

                                            # Extract plain Python values
                                            # BEFORE background thread

                                            fcm_token = (
                                                admin.fcm_token
                                            )

                                            appointment_id = (
                                                appointment.id
                                            )

                                            user_name = (
                                                user.name
                                            )

                                            service_name = (
                                                service.name
                                            )

                                            branch_name = (
                                                branch.name
                                            )

                                            # Do NOT overwrite
                                            # appointment_date variable

                                            appointment_date_str = (
                                                str(
                                                    appointment
                                                    .appointment_date
                                                )
                                            )

                                            start_time_str = (
                                                appointment
                                                .start_time
                                                .strftime("%I:%M %p")
                                            )

                                            notification_executor.submit(
                                                send_admin_notification,
                                                fcm_token,
                                                appointment_id,
                                                user_name,
                                                service_name,
                                                branch_name,
                                                appointment_date_str,
                                                start_time_str
                                            )

                                            logger.info(
                                                "[FCM] Notification submitted to background"
                                            )

                                        # ==================================================
                                        # SUCCESS SCREEN
                                        # ==================================================

                                        response_data = {
                                            "version": "3.0",

                                            "screen": "BOOKING_SUCCESS",

                                            "data": {

                                                "appointment_id": str(
                                                    appointment.id
                                                ),

                                                "date": (
                                                    appointment
                                                    .appointment_date
                                                    .strftime(
                                                        "%d %B %Y"
                                                    )
                                                ),

                                                "time": (
                                                    f"{appointment.start_time.strftime('%I:%M %p').lstrip('0')} - "
                                                    f"{appointment.end_time.strftime('%I:%M %p').lstrip('0')}"
                                                ),

                                                "branch": branch.name,

                                                "service": service.name
                                            }
                                        }

                except Exception:

                    db.rollback()

                    logger.exception(
                        "Final appointment booking failed."
                    )

                    response_data = {
                        "screen": "BOOKING_DETAILS",
                        "data": {}
                    }

                finally:

                    db.close()

            # ==================================================
            # UNKNOWN DATA_EXCHANGE SCREEN
            # ==================================================

            else:

                logger.warning(
                    "DATA_EXCHANGE received from unsupported screen: %s",
                    current_screen
                )

                response_data = {
                    "screen": "BOOKING_DETAILS",
                    "data": {}
                }

        # ==================================================
        # UNKNOWN ACTION
        # ==================================================

        else:

            logger.warning(
                "Unsupported action: %s",
                action
            )

            response_data = {
                "screen": "BOOKING_DETAILS",
                "data": {}
            }

        # ==================================================
        # LOG RESPONSE
        # ==================================================

        logger.info(
            "\nRESPONSE DATA:\n%s",
            json.dumps(
                response_data,
                indent=2,
                ensure_ascii=False
            )
        )

        # ==================================================
        # ENCRYPT RESPONSE
        # ==================================================

        encrypted_response = encrypt_response(
            response_data,
            aes_key,
            iv
        )

        logger.info(
            "Encrypted response generated successfully."
        )

        # ==================================================
        # RETURN RESPONSE
        # ==================================================

        return PlainTextResponse(
            content=encrypted_response,
            status_code=200
        )

    except Exception:

        logger.exception(
            "WhatsApp Flow error"
        )

        return PlainTextResponse(
            content="",
            status_code=500
        )