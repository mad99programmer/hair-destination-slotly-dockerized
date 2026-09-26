# ==========================================================
# admin_routes.py
# ==========================================================

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date
from pydantic import BaseModel
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models import (
    User,
    Branch,
    Service,
    Appointment,
    Admin,
    BranchWorkingHours
)
from datetime import date, datetime, time, timedelta
from sqlalchemy import func
from security import get_current_admin


router = APIRouter(
    prefix="/admin",
    tags=["admin"]
)
class FCMTokenRequest(BaseModel):
    fcm_token: str



# ==========================================================
# ALL APPOINTMENTS
# ==========================================================

@router.get("/appointments")
def get_appointments(

    status: str = None,
    branch_id: int = None,
    service_id: int = None,
    from_date: date = None,
    to_date: date = None,

    current_admin=Depends(
        get_current_admin
    ),

    db: Session = Depends(get_db)
):

    # ======================================================
    # BASE QUERY
    # ======================================================

    query = (
        db.query(
            Appointment,
            User,
            Branch,
            Service
        )
        .join(
            User,
            User.id == Appointment.user_id
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
            Appointment.status != "deleted"
        )
    )


    # ======================================================
    # STATUS FILTER
    # ======================================================

    if status:

        query = query.filter(
            Appointment.status == status
        )


    # ======================================================
    # BRANCH FILTER
    # ======================================================

    if branch_id:

        query = query.filter(
            Appointment.branch_id == branch_id
        )


    # ======================================================
    # SERVICE FILTER
    # ======================================================

    if service_id:

        query = query.filter(
            Appointment.service_id == service_id
        )


    # ======================================================
    # FROM DATE FILTER
    # ======================================================

    if from_date:

        query = query.filter(
            Appointment.appointment_date >= from_date
        )


    # ======================================================
    # TO DATE FILTER
    # ======================================================

    if to_date:

        query = query.filter(
            Appointment.appointment_date <= to_date
        )


    # ======================================================
    # ORDER
    # ======================================================

    appointments = (
        query
        .order_by(
            Appointment.appointment_date,
            Appointment.start_time
        )
        .all()
    )


    # ======================================================
    # BUILD RESPONSE
    # ======================================================

    result = []

    for appointment, user, branch, service in appointments:

        result.append(
            {
                "id": appointment.id,

                "customer_name": (
                    user.name
                    if user
                    else "Unknown"
                ),

                "customer_phone": (
                    user.phone_number
                    if user
                    else ""
                ),

                "branch_name": (
                    branch.name
                    if branch
                    else "Unknown"
                ),

                "service_name": (
                    service.name
                    if service
                    else "Unknown"
                ),

                "date": (
                    str(
                        appointment.appointment_date
                    )
                ),

                "time": (
                    f"{appointment.start_time.strftime('%I:%M %p')}"
                    f" - "
                    f"{appointment.end_time.strftime('%I:%M %p')}"
                ),

                "status": appointment.status
            }
        )


    # ======================================================
    # RETURN
    # ======================================================

    return result

@router.post("/fcm-token")
def save_fcm_token(
    payload: FCMTokenRequest,
    current_admin=Depends(get_current_admin),
    db: Session = Depends(get_db)
):

    admin = (
        db.query(Admin)
        .filter(Admin.id == current_admin.id)
        .first()
    )

    if not admin:
        raise HTTPException(
            status_code=401,
            detail="Admin not found"
        )

    admin.fcm_token = payload.fcm_token

    db.commit()

    return {
        "success": True,
        "message": "FCM token saved"
    }


# ==========================================================
# CANCEL APPOINTMENT
# ==========================================================

@router.post("/appointments/{appointment_id}/cancel")
def cancel_appointment(

    appointment_id: int,

    current_admin=Depends(
        get_current_admin
    ),

    db: Session = Depends(get_db)
):

    # ======================================================
    # FIND APPOINTMENT
    # ======================================================

    appointment = (
        db.query(Appointment)
        .filter(
            Appointment.id == appointment_id
        )
        .first()
    )

    # ======================================================
    # NOT FOUND
    # ======================================================

    if not appointment:

        raise HTTPException(
            status_code=404,
            detail="Appointment not found"
        )

    # ======================================================
    # ALREADY CANCELLED
    # ======================================================

    if appointment.status == "cancelled":

        return {
            "success": True,
            "message": "Appointment is already cancelled",
            "appointment_id": appointment.id,
            "status": appointment.status
        }

    # ======================================================
    # ALREADY DELETED
    # ======================================================

    if appointment.status == "deleted":

        raise HTTPException(
            status_code=400,
            detail="Cannot cancel a deleted appointment"
        )

    # ======================================================
    # CANCEL
    # ======================================================

    appointment.status = "cancelled"

    db.commit()

    db.refresh(
        appointment
    )

    # ======================================================
    # RETURN
    # ======================================================

    return {
        "success": True,
        "message": "Appointment cancelled successfully",
        "appointment_id": appointment.id,
        "status": appointment.status
    }



################# addition of appointment from admin panel #####################################
# ==========================================================
# GET ACTIVE BRANCHES
# ==========================================================

@router.get("/branches")
def get_branches(
    current_admin=Depends(get_current_admin),
    db: Session = Depends(get_db)
):

    branches = (
        db.query(Branch)
        .filter(Branch.is_active == True)
        .order_by(Branch.name)
        .all()
    )

    return [
        {
            "id": branch.id,
            "name": branch.name,
            "capacity": branch.capacity
        }
        for branch in branches
    ]


# ==========================================================
# GET ACTIVE SERVICES
# ==========================================================

@router.get("/services")
def get_services(
    current_admin=Depends(get_current_admin),
    db: Session = Depends(get_db)
):

    services = (
        db.query(Service)
        .filter(Service.is_active == True)
        .order_by(Service.name)
        .all()
    )

    return [
        {
            "id": service.id,
            "name": service.name
        }
        for service in services
    ]


# ==========================================================
# APPOINTMENT AVAILABILITY
# ==========================================================

@router.get("/appointment-availability")
def get_appointment_availability(
    branch_id: int,
    appointment_date: date,

    current_admin=Depends(get_current_admin),

    db: Session = Depends(get_db)
):

    # ------------------------------------------------------
    # FIND BRANCH
    # ------------------------------------------------------

    branch = (
        db.query(Branch)
        .filter(
            Branch.id == branch_id,
            Branch.is_active == True
        )
        .first()
    )

    if not branch:
        raise HTTPException(
            status_code=404,
            detail="Branch not found"
        )

    # ------------------------------------------------------
    # FIND WORKING HOURS
    # ------------------------------------------------------

    weekday = appointment_date.strftime("%A")

    working_hours = (
        db.query(BranchWorkingHours)
        .filter(
            BranchWorkingHours.branch_id == branch_id,
            BranchWorkingHours.weekday == weekday,
            BranchWorkingHours.is_active == True
        )
        .first()
    )

    # ------------------------------------------------------
    # BRANCH CLOSED
    # ------------------------------------------------------

    if (
        not working_hours
        or not working_hours.start_time
        or not working_hours.end_time
    ):
        return {
            "branch": {
                "id": branch.id,
                "name": branch.name,
                "capacity": branch.capacity
            },
            "slots": []
        }

    # ------------------------------------------------------
    # GENERATE 1-HOUR SLOTS
    # ------------------------------------------------------

    slots = []

    current_time = working_hours.start_time
    end_time = working_hours.end_time

    while True:

        slot_start = current_time

        slot_end_datetime = (
            datetime.combine(
                appointment_date,
                slot_start
            )
            + timedelta(
                minutes=branch.slot_duration_minutes
            )
        )

        slot_end = slot_end_datetime.time()

        # Don't create a slot beyond closing time
        if slot_end > end_time:
            break

        # --------------------------------------------------
        # COUNT OCCUPIED APPOINTMENTS
        # --------------------------------------------------

        occupied = (
            db.query(func.count(Appointment.id))
            .filter(
                Appointment.branch_id == branch_id,
                Appointment.appointment_date == appointment_date,

                Appointment.start_time == slot_start,
                Appointment.end_time == slot_end,

                Appointment.status != "cancelled",
                Appointment.status != "deleted"
            )
            .scalar()
        )

        occupied = int(occupied or 0)

        available = max(
            0,
            branch.capacity - occupied
        )

        slots.append(
            {
                "start_time": slot_start.strftime("%H:%M"),
                "end_time": slot_end.strftime("%H:%M"),
                "occupied": occupied,
                "available": available,
                "capacity": branch.capacity
            }
        )

        current_time = slot_end

        if current_time >= end_time:
            break

    # ------------------------------------------------------
    # RESPONSE
    # ------------------------------------------------------

    return {
        "branch": {
            "id": branch.id,
            "name": branch.name,
            "capacity": branch.capacity
        },
        "slots": slots
    }


# ==========================================================
# CREATE ADMIN APPOINTMENT
# ==========================================================

class AdminAppointmentRequest(BaseModel):

    customer_name: str
    customer_phone: str

    branch_id: int
    service_id: int

    appointment_date: date

    start_time: time
    end_time: time


@router.post("/appointments")
def create_admin_appointment(

    payload: AdminAppointmentRequest,

    current_admin=Depends(
        get_current_admin
    ),

    db: Session = Depends(get_db)
):

    # ------------------------------------------------------
    # FIND BRANCH
    # ------------------------------------------------------

    branch = (
        db.query(Branch)
        .filter(
            Branch.id == payload.branch_id,
            Branch.is_active == True
        )
        .first()
    )

    if not branch:

        raise HTTPException(
            status_code=404,
            detail="Branch not found"
        )

    # ------------------------------------------------------
    # FIND SERVICE
    # ------------------------------------------------------

    service = (
        db.query(Service)
        .filter(
            Service.id == payload.service_id,
            Service.is_active == True
        )
        .first()
    )

    if not service:

        raise HTTPException(
            status_code=404,
            detail="Service not found"
        )

    # ------------------------------------------------------
    # CHECK TIME
    # ------------------------------------------------------

    if payload.start_time >= payload.end_time:

        raise HTTPException(
            status_code=400,
            detail="Invalid appointment time"
        )

    # ------------------------------------------------------
    # CHECK WORKING HOURS
    # ------------------------------------------------------

    weekday = payload.appointment_date.strftime("%A")

    working_hours = (
        db.query(BranchWorkingHours)
        .filter(
            BranchWorkingHours.branch_id == payload.branch_id,
            BranchWorkingHours.weekday == weekday,
            BranchWorkingHours.is_active == True
        )
        .first()
    )

    if (
        not working_hours
        or not working_hours.start_time
        or not working_hours.end_time
    ):

        raise HTTPException(
            status_code=400,
            detail="Branch is closed on selected date"
        )

    if (
        payload.start_time < working_hours.start_time
        or payload.end_time > working_hours.end_time
    ):

        raise HTTPException(
            status_code=400,
            detail="Appointment time is outside working hours"
        )

    # ------------------------------------------------------
    # CHECK CAPACITY
    # ------------------------------------------------------

    occupied = (
        db.query(func.count(Appointment.id))
        .filter(
            Appointment.branch_id == payload.branch_id,

            Appointment.appointment_date
            == payload.appointment_date,

            Appointment.start_time
            == payload.start_time,

            Appointment.end_time
            == payload.end_time,

            Appointment.status != "cancelled",
            Appointment.status != "deleted"
        )
        .scalar()
    )

    occupied = int(occupied or 0)

    if occupied >= branch.capacity:

        raise HTTPException(
            status_code=409,
            detail="No chairs available for this time slot"
        )

    # ------------------------------------------------------
    # FIND OR CREATE USER
    # ------------------------------------------------------

    phone = payload.customer_phone.strip()

    user = (
        db.query(User)
        .filter(
            User.phone_number == phone
        )
        .first()
    )

    if user:

        # Update name if admin entered a newer name
        if payload.customer_name.strip():
            user.name = payload.customer_name.strip()

    else:

        user = User(
            business_id=branch.business_id,
            phone_number=phone,
            name=payload.customer_name.strip(),
            is_active=True
        )

        db.add(user)

        # Get generated user.id
        db.flush()

    # ------------------------------------------------------
    # CREATE APPOINTMENT
    # ------------------------------------------------------

    appointment = Appointment(

        user_id=user.id,

        business_id=branch.business_id,

        branch_id=branch.id,

        service_id=service.id,

        appointment_date=payload.appointment_date,

        start_time=payload.start_time,

        end_time=payload.end_time,

        status="booked"
    )

    db.add(appointment)

    db.commit()

    db.refresh(appointment)

    # ------------------------------------------------------
    # RESPONSE
    # ------------------------------------------------------

    return {
        "success": True,

        "message": "Appointment created successfully",

        "appointment": {
            "id": appointment.id,

            "user_id": user.id,

            "customer_name": user.name,

            "customer_phone": user.phone_number,

            "branch_id": branch.id,

            "branch_name": branch.name,

            "service_id": service.id,

            "service_name": service.name,

            "appointment_date": str(
                appointment.appointment_date
            ),

            "start_time": (
                appointment.start_time.strftime("%H:%M")
            ),

            "end_time": (
                appointment.end_time.strftime("%H:%M")
            ),

            "status": appointment.status
        }
    }