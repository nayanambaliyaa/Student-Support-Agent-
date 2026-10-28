"""
Agent Tools Module for Intelligent Student Support.
Provides functional tools for student records, fees/scholarships, support tickets,
and sensitive record modification with code-enforced authorization and human-in-the-loop approval.
"""

import os
import json
import time
from typing import Dict, Any, Optional

from agent.auth import AuthorizationEngine
from agent.audit import audit_logger
from agent.approvals import approval_manager

DB_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "students_database.json")

def _load_db() -> Dict[str, Any]:
    if not os.path.exists(DB_FILE_PATH):
        return {"students": [], "support_tickets": []}
    try:
        with open(DB_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"students": [], "support_tickets": []}

def _save_db(data: Dict[str, Any]):
    os.makedirs(os.path.dirname(DB_FILE_PATH), exist_ok=True)
    with open(DB_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def check_student_record(
    actor_student_id: Optional[str] = None,
    target_student_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Tool: Retrieves official academic profile, programme, batch, CGPA, and attendance.
    Enforces application-level authorization in Python code.
    """
    effective_target = target_student_id or actor_student_id
    
    # 1. Enforce code-level authorization gate
    authorized, auth_msg = AuthorizationEngine.authorize_read(
        actor_student_id=actor_student_id,
        target_student_id=effective_target,
        resource_name="Academic Profile & CGPA Record"
    )
    if not authorized:
        return {
            "status": "ERROR_UNAUTHORIZED",
            "error": auth_msg,
            "actor": actor_student_id,
            "target": effective_target
        }

    clean_id = effective_target.strip().upper()
    db = _load_db()
    for s in db.get("students", []):
        if s.get("student_id", "").upper() == clean_id:
            return {
                "status": "SUCCESS",
                "student_id": s["student_id"],
                "name": s["name"],
                "programme": s["programme"],
                "batch": s["batch"],
                "trimester": s["trimester"],
                "cgpa": s["cgpa"],
                "attendance_percentage": f"{s['attendance_percentage']}%",
                "email": s.get("email", ""),
                "phone": s.get("phone", "+91-9811002233")
            }

    return {
        "status": "ERROR_NOT_FOUND",
        "error": f"No student found with ID '{clean_id}'. Please verify with the Academic Office."
    }


def check_fee_and_scholarship(
    actor_student_id: Optional[str] = None,
    target_student_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Tool: Retrieves current tuition fee status, balance dues, payment deadline,
    and associated scholarship concessions / retention status.
    Enforces application-level authorization in Python code.
    """
    effective_target = target_student_id or actor_student_id

    # 1. Enforce code-level authorization gate
    authorized, auth_msg = AuthorizationEngine.authorize_read(
        actor_student_id=actor_student_id,
        target_student_id=effective_target,
        resource_name="Tuition Fee and Scholarship Record"
    )
    if not authorized:
        return {
            "status": "ERROR_UNAUTHORIZED",
            "error": auth_msg,
            "actor": actor_student_id,
            "target": effective_target
        }

    clean_id = effective_target.strip().upper()
    db = _load_db()
    for s in db.get("students", []):
        if s.get("student_id", "").upper() == clean_id:
            fee = s.get("fee_details", {})
            sch = s.get("scholarship", {})
            return {
                "status": "SUCCESS",
                "student_id": s["student_id"],
                "name": s["name"],
                "programme": s["programme"],
                "fee_summary": {
                    "trimester_fee": f"INR {fee.get('trimester_fee', 0):,}",
                    "amount_paid": f"INR {fee.get('amount_paid', 0):,}",
                    "outstanding_due": f"INR {fee.get('outstanding_due', 0):,}",
                    "due_date": fee.get("due_date", "N/A"),
                    "payment_status": fee.get("status", "UNKNOWN"),
                    "last_payment_date": fee.get("last_payment_date", "None"),
                    "payment_reference": fee.get("payment_reference", "None")
                },
                "scholarship_summary": {
                    "has_scholarship": sch.get("has_scholarship", False),
                    "scheme_name": sch.get("scheme_name", "None"),
                    "waiver_percentage": f"{sch.get('concession_percentage', 0)}%",
                    "annual_benefit": f"INR {sch.get('annual_benefit_inr', 0):,}",
                    "status": sch.get("status", "N/A"),
                    "retention_criteria": sch.get("retention_criteria", "N/A"),
                    "eligibility_met": sch.get("current_eligibility_met", False)
                }
            }

    return {
        "status": "ERROR_NOT_FOUND",
        "error": f"Student ID '{clean_id}' was not found in the institutional finance registry."
    }


def create_support_ticket(
    student_id: Optional[str],
    category: str,
    description: str,
    urgency: str = "Medium"
) -> Dict[str, Any]:
    """
    Tool: Creates a tracked helpdesk support ticket for unresolved administrative,
    financial, or academic matters.
    """
    clean_id = student_id.strip().upper() if student_id and student_id != "GUEST" else "GUEST_STUDENT"

    db = _load_db()
    ticket_count = len(db.get("support_tickets", [])) + 1
    ticket_id = f"TCK-2026-{ticket_count:04d}"
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")

    new_ticket = {
        "ticket_id": ticket_id,
        "student_id": clean_id,
        "category": category,
        "description": description,
        "urgency": urgency,
        "status": "OPEN",
        "created_at": now_str,
        "expected_sla": "24-48 Hours" if urgency in ["High", "Urgent"] else "3 Working Days"
    }

    tickets = db.get("support_tickets", [])
    tickets.append(new_ticket)
    db["support_tickets"] = tickets
    _save_db(db)

    audit_logger.log_event(
        actor_student_id=clean_id,
        action_type="SUPPORT_TICKET_CREATED",
        target_resource=f"Support Desk ({ticket_id})",
        authorization_status="ALLOWED",
        execution_result="SUCCESS",
        details=f"Created support ticket {ticket_id} under category '{category}'.",
        metadata=new_ticket
    )

    return {
        "status": "SUCCESS",
        "ticket_id": ticket_id,
        "student_id": clean_id,
        "category": category,
        "assigned_sla": new_ticket["expected_sla"],
        "ticket_status": "OPEN",
        "message": f"Support Ticket {ticket_id} has been formally logged with the Student Services Desk."
    }


def request_student_record_update(
    actor_student_id: Optional[str],
    target_student_id: Optional[str],
    field: str,
    new_value: str,
    reason: Optional[str] = None
) -> Dict[str, Any]:
    """
    Tool: Requests a sensitive change to official institutional student records
    (e.g., updating contact phone, email, or elective course).
    Enforces authorization check and creates a PENDING_APPROVAL request.
    DOES NOT execute modification automatically.
    """
    effective_target = target_student_id or actor_student_id

    # 1. Enforce authorization gate
    allowed, auth_msg, requires_approval = AuthorizationEngine.authorize_modification(
        actor_student_id=actor_student_id,
        target_student_id=effective_target,
        action_name=f"Update {field}"
    )

    if not allowed:
        return {
            "status": "ERROR_UNAUTHORIZED",
            "error": auth_msg,
            "actor": actor_student_id,
            "target": effective_target
        }

    # 2. Sensitive Action Gate: Must create pending approval, NOT execute directly
    action_type = "UPDATE_CONTACT_INFO" if field in ["email", "phone", "contact"] else "UPDATE_STUDENT_PROFILE"
    if "elective" in field.lower() or "course" in field.lower():
        action_type = "CHANGE_ELECTIVE_COURSE"

    appr_req = approval_manager.create_request(
        actor_student_id=actor_student_id,
        action_type=action_type,
        target_student_id=effective_target,
        requested_changes={"field": field, "new_value": new_value, "reason": reason or "Student self-service update request"},
        description=f"Request to update {field} to '{new_value}' for {effective_target}"
    )

    return {
        "status": "PENDING_APPROVAL",
        "approval_id": appr_req["approval_id"],
        "actor_student_id": appr_req["actor_student_id"],
        "target_student_id": appr_req["target_student_id"],
        "action_type": appr_req["action_type"],
        "requested_changes": appr_req["requested_changes"],
        "execution_status": "WAITING_FOR_APPROVAL",
        "message": (
            f"Sensitive Action Intercepted: Modifying official institutional records requires human confirmation / approval. "
            f"Approval Request `{appr_req['approval_id']}` has been created. The action has NOT been executed yet."
        )
    }


def resolve_approval_action(
    approval_id: str,
    decision: str,  # 'APPROVED' or 'REJECTED'
    resolved_by: str = "Academic Registrar / Human Advisor",
    reason: Optional[str] = None
) -> Dict[str, Any]:
    """
    Tool: Resolves a pending approval request.
    - If APPROVED: Executes the sensitive change in the database.
    - If REJECTED: Aborts without touching the database.
    Logs audit events accordingly.
    """
    success, msg, req = approval_manager.resolve_approval(
        approval_id=approval_id,
        decision=decision,
        resolved_by=resolved_by,
        reason=reason
    )

    clean_decision = decision.strip().upper()
    if success:
        if clean_decision == "APPROVED":
            audit_logger.log_event(
                actor_student_id=resolved_by,
                action_type="APPROVAL_DECISION_APPROVED",
                target_resource=f"{req.get('target_student_id')} ({req.get('action_type')})",
                authorization_status="APPROVED",
                execution_result="EXECUTED",
                details=f"Approval granted for {approval_id}. Record change executed in database.",
                metadata=req
            )
            return {
                "status": "APPROVED_AND_EXECUTED",
                "approval_id": approval_id,
                "decision": "APPROVED",
                "execution_result": "EXECUTED",
                "message": msg,
                "request": req
            }
        else:
            audit_logger.log_event(
                actor_student_id=resolved_by,
                action_type="APPROVAL_DECISION_REJECTED",
                target_resource=f"{req.get('target_student_id')} ({req.get('action_type')})",
                authorization_status="REJECTED",
                execution_result="ABORTED_NO_CHANGE",
                details=f"Approval rejected for {approval_id}. Action aborted without modifying database.",
                metadata=req
            )
            return {
                "status": "REJECTED_AND_ABORTED",
                "approval_id": approval_id,
                "decision": "REJECTED",
                "execution_result": "ABORTED_NO_CHANGE",
                "message": msg,
                "request": req
            }
    else:
        return {
            "status": "ERROR",
            "error": msg,
            "approval_id": approval_id
        }


# Registry of available tools with metadata
AVAILABLE_TOOLS = {
    "check_fee_and_scholarship": {
        "name": "check_fee_and_scholarship",
        "description": "Lookup student fee payment status, outstanding balance, due date, and scholarship scheme details with authorization checks.",
        "parameters": {"actor_student_id": "string", "target_student_id": "string (optional)"},
        "handler": check_fee_and_scholarship
    },
    "check_student_record": {
        "name": "check_student_record",
        "description": "Lookup student academic profile, programme, CGPA, batch, and attendance percentage with authorization checks.",
        "parameters": {"actor_student_id": "string", "target_student_id": "string (optional)"},
        "handler": check_student_record
    },
    "request_student_record_update": {
        "name": "request_student_record_update",
        "description": "Request a sensitive update to official student record (email, phone, elective). Creates human approval requirement.",
        "parameters": {
            "actor_student_id": "string",
            "target_student_id": "string",
            "field": "string ('phone', 'email', 'elective')",
            "new_value": "string",
            "reason": "string (optional)"
        },
        "handler": request_student_record_update
    },
    "resolve_approval_action": {
        "name": "resolve_approval_action",
        "description": "Approve or reject a pending sensitive action request.",
        "parameters": {
            "approval_id": "string (e.g. 'APPR-2026-0001')",
            "decision": "string ('APPROVED' or 'REJECTED')",
            "resolved_by": "string (optional)",
            "reason": "string (optional)"
        },
        "handler": resolve_approval_action
    },
    "create_support_ticket": {
        "name": "create_support_ticket",
        "description": "Create a formal support ticket for payment issues, course change exceptions, or unresolved policy questions.",
        "parameters": {
            "student_id": "string",
            "category": "string",
            "description": "string",
            "urgency": "string ('Low', 'Medium', 'High')"
        },
        "handler": create_support_ticket
    }
}
