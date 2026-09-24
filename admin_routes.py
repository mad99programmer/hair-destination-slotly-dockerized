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
    Admin
)

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