"""
Application-Level Authorization and Permission Control Engine.
Enforces institutional privacy and access policies in deterministic Python code:
- Verifies authenticated student identity
- Blocks cross-student read/write attempts
- Enforces human approval requirements on sensitive modifications
- Connects directly with the Audit Logger for compliance
"""

import re
from typing import Dict, Any, Optional, Tuple
from agent.audit import audit_logger

KNOWN_STUDENTS_MAP = {
    "rahul sharma": "STU-2025-001",
    "rahul": "STU-2025-001",
    "priya patel": "STU-2025-002",
    "priya": "STU-2025-002",
    "amit verma": "STU-2025-003",
    "amit": "STU-2025-003"
}

class AuthorizationEngine:
    """Deterministic, code-enforced authorization gatekeeper."""

    @staticmethod
    def identify_target_student(query: str, actor_student_id: Optional[str]) -> Tuple[Optional[str], bool]:
        """
        Extracts target student ID mentioned in query and detects if it is a cross-student reference.
        Returns: (target_student_id, is_cross_student_reference)
        """
        clean_actor = actor_student_id.strip().upper() if actor_student_id and actor_student_id != "GUEST" else None
        
        # 1. Look for explicit Student ID pattern (e.g. STU-2025-002)
        matches = re.findall(r"\b(STU-202[0-9]-[0-9]{3,4})\b", query, re.IGNORECASE)
        if matches:
            found_id = matches[0].upper()
            is_cross = bool(clean_actor and found_id != clean_actor)
            return found_id, is_cross

        # 2. Look for student names
        q_lower = query.lower()
        for name, sid in KNOWN_STUDENTS_MAP.items():
            pattern = rf"\b{re.escape(name)}\b"
            if re.search(pattern, q_lower):
                is_cross = bool(clean_actor and sid != clean_actor)
                return sid, is_cross

        # Default: if no target specified, target is the authenticated actor
        return clean_actor, False

    @staticmethod
    def authorize_read(
        actor_student_id: Optional[str],
        target_student_id: Optional[str],
        resource_name: str = "Private Student Record"
    ) -> Tuple[bool, str]:
        """
        Enforces read access control in code.
        Only allows students to read their own private data.
        """
        clean_actor = actor_student_id.strip().upper() if actor_student_id and actor_student_id != "GUEST" else None
        clean_target = target_student_id.strip().upper() if target_student_id else None

        if not clean_actor:
            reason = f"Access Denied: Authentication required. You must sign in to view {resource_name}."
            audit_logger.log_event(
                actor_student_id="GUEST",
                action_type="UNAUTHENTICATED_ACCESS_BLOCKED",
                target_resource=f"{clean_target or 'UNKNOWN'} ({resource_name})",
                authorization_status="DENIED_UNAUTHORIZED",
                execution_result="BLOCKED",
                details=reason
            )
            return False, reason

        if not clean_target:
            clean_target = clean_actor

        if clean_actor != clean_target:
            reason = (
                f"Access Denied [Authorization Error]: You are signed in as '{clean_actor}'. "
                f"You do NOT have permission to read the private {resource_name} of student '{clean_target}'. "
                f"Institutional data privacy regulations strictly restrict access to your own records."
            )
            audit_logger.log_event(
                actor_student_id=clean_actor,
                action_type="CROSS_STUDENT_ACCESS_BLOCKED",
                target_resource=f"{clean_target} ({resource_name})",
                authorization_status="DENIED_UNAUTHORIZED",
                execution_result="BLOCKED",
                details=reason,
                metadata={"attempted_target": clean_target, "actor": clean_actor}
            )
            return False, reason

        # Allowed - student accessing own record
        audit_logger.log_event(
            actor_student_id=clean_actor,
            action_type=f"READ_{resource_name.upper().replace(' ', '_')}",
            target_resource=f"{clean_actor} ({resource_name})",
            authorization_status="ALLOWED",
            execution_result="SUCCESS",
            details=f"Authorized read access for student {clean_actor}."
        )
        return True, "Authorized: Access to personal student record granted."

    @staticmethod
    def authorize_modification(
        actor_student_id: Optional[str],
        target_student_id: Optional[str],
        action_name: str = "Record Modification"
    ) -> Tuple[bool, str, bool]:
        """
        Enforces write/modification access control in code.
        Returns: (is_allowed: bool, reason: str, requires_human_approval: bool)
        """
        clean_actor = actor_student_id.strip().upper() if actor_student_id and actor_student_id != "GUEST" else None
        clean_target = target_student_id.strip().upper() if target_student_id else clean_actor

        if not clean_actor:
            reason = "Access Denied: Authentication required to request changes to official records."
            audit_logger.log_event(
                actor_student_id="GUEST",
                action_type="UNAUTHENTICATED_MODIFICATION_BLOCKED",
                target_resource=f"{clean_target or 'UNKNOWN'} ({action_name})",
                authorization_status="DENIED_UNAUTHORIZED",
                execution_result="BLOCKED",
                details=reason
            )
            return False, reason, False

        if clean_actor != clean_target:
            reason = (
                f"Access Denied [Authorization Error]: Student '{clean_actor}' cannot modify records "
                f"belonging to student '{clean_target}'. Cross-student record alteration is strictly prohibited."
            )
            audit_logger.log_event(
                actor_student_id=clean_actor,
                action_type="CROSS_STUDENT_MODIFICATION_BLOCKED",
                target_resource=f"{clean_target} ({action_name})",
                authorization_status="DENIED_UNAUTHORIZED",
                execution_result="BLOCKED",
                details=reason
            )
            return False, reason, False

        # Modifying own record is permitted to request, but REQUIRES human approval
        details = (
            f"Authorized request: Student {clean_actor} requested sensitive modification ({action_name}). "
            f"Institutional safety policy requires formal human confirmation/approval before execution."
        )
        audit_logger.log_event(
            actor_student_id=clean_actor,
            action_type="SENSITIVE_RECORD_UPDATE_REQUEST",
            target_resource=f"{clean_actor} ({action_name})",
            authorization_status="APPROVAL_REQUIRED",
            execution_result="PENDING_APPROVAL",
            details=details
        )
        return True, details, True
