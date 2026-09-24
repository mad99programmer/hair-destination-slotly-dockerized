import os

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from models import (
    Branch,
    BranchWorkingHours,
    Appointment,
    Service
)


from dotenv import load_dotenv

# ==========================================================
# ENVIRONMENT
# ==========================================================

load_dotenv()

BUSINESS_ID = int(
    os.getenv("BUSINESS_ID", "1")
)


# ==========================================================
# GET ACTIVE BRANCHES
# ==========================================================

def get_branches(db: Session):

    branches = (
        db.query(Branch)
        .filter(
            Branch.business_id == BUSINESS_ID,
            Branch.is_active == True
        )
        .order_by(Branch.name)
        .all()
    )

    return [
        {
            "id": str(branch.id),
            "title": branch.name
        }
        for branch in branches
    ]


# ==========================================================
# GET ACTIVE SERVICES
# ==========================================================

def get_services(db: Session):

    services = (
        db.query(Service)
        .filter(
            Service.business_id == BUSINESS_ID,
            Service.is_active == True
        )
        .order_by(Service.name)
        .all()
    )

    return [
        {
            "id": str(service.id),
            "title": service.name
        }
        for service in services
    ]



def get_available_slots(
    db: Session,
    branch_id: int,
    slot_date
):
    # ======================================================
    # 1. GET ACTIVE BRANCH
    # ======================================================

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
        return []


    # ======================================================
    # 2. CONVERT DATE → WEEKDAY
    # ======================================================

    weekday = slot_date.strftime("%A")


    # ======================================================
    # 3. GET BRANCH WORKING HOURS
    # ======================================================

    working_hours = (
        db.query(BranchWorkingHours)
        .filter(
            BranchWorkingHours.branch_id == branch_id,
            BranchWorkingHours.weekday == weekday,
            BranchWorkingHours.is_active == True
        )
        .first()
    )

    if not working_hours:
        return []

    if (
        working_hours.start_time is None
        or working_hours.end_time is None
    ):
        return []


    # ======================================================
    # 4. BRANCH SLOT DURATION
    # ======================================================
    # IMPORTANT:
    # We use branch.slot_duration_minutes.
    # Service duration is NOT used for slot generation.

    slot_duration = branch.slot_duration_minutes

    if not slot_duration or slot_duration <= 0:
        return []


    # ======================================================
    # 5. CREATE START AND CLOSING DATETIME
    # ======================================================

    current_datetime = datetime.combine(
        slot_date,
        working_hours.start_time
    )

    closing_datetime = datetime.combine(
        slot_date,
        working_hours.end_time
    )


    # ======================================================
    # 6. FETCH EXISTING BOOKINGS
    # ======================================================
    # We fetch all booked appointments for this
    # branch + date only once.

    booked_rows = (
        db.query(
            Appointment.start_time
        )
        .filter(
            Appointment.branch_id == branch_id,
            Appointment.appointment_date == slot_date,
            Appointment.status == "booked"
        )
        .all()
    )


    # ======================================================
    # 7. COUNT BOOKINGS BY START TIME
    # ======================================================

    booked_count_map = {}

    for row in booked_rows:

        start_time = row[0]

        booked_count_map[start_time] = (
            booked_count_map.get(start_time, 0) + 1
        )


    # ======================================================
    # 8. GENERATE DYNAMIC SLOTS
    # ======================================================

    available_slots = []

    while current_datetime < closing_datetime:

        slot_end_datetime = (
            current_datetime
            + timedelta(minutes=slot_duration)
        )


        # --------------------------------------------------
        # Do not create a slot beyond closing time
        # --------------------------------------------------

        if slot_end_datetime > closing_datetime:
            break


        # --------------------------------------------------
        # Extract TIME values
        # --------------------------------------------------

        slot_start = current_datetime.time()
        slot_end = slot_end_datetime.time()


        # ==================================================
        # 9. CHECK EXISTING BOOKINGS FOR THIS SLOT
        # ==================================================

        booked_count = booked_count_map.get(
            slot_start,
            0
        )


        # ==================================================
        # 10. CALCULATE REMAINING CAPACITY
        # ==================================================

        remaining = (
            branch.capacity
            - booked_count
        )


        # ==================================================
        # 11. ONLY RETURN AVAILABLE SLOTS
        # ==================================================

        if remaining > 0:

            available_slots.append(
                {
                    "start_time": slot_start,
                    "end_time": slot_end,
                    "remaining": remaining
                }
            )


        # ==================================================
        # 12. MOVE TO NEXT SLOT
        # ==================================================

        current_datetime = slot_end_datetime


    # ======================================================
    # 13. RETURN AVAILABLE SLOTS
    # ======================================================

    return available_slots