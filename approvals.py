"""
Human-in-the-Loop Approval Management Engine for Sensitive Student Actions.
Enforces institutional guardrails: sensitive modifications to official student records
cannot execute automatically and must wait for human / administrative confirmation.
"""

import os
import json
import time
from typing import Dict, Any, List, Optional, Tuple

APPROVALS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "pending_approvals.json")
DB_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "students_database.json")

class ApprovalManager:
    """Manages creation, inspection, and human resolution of sensitive action requests."""

    def __init__(self, storage_path: str = APPROVALS_FILE):
        self.storage_path = storage_path
        self._ensure_file()

    def _ensure_file(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        if not os.path.exists(self.storage_path):
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)

    def _load_approvals(self) -> List[Dict[str, Any]]:
        self._ensure_file()
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_approvals(self, approvals: List[Dict[str, Any]]):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(approvals, f, indent=2)

    def create_request(
        self,
        actor_student_id: str,
        action_type: str,
        target_student_id: str,
        requested_changes: Dict[str, Any],
        description: str
    ) -> Dict[str, Any]:
        """
        Creates a new PENDING_APPROVAL request. The action MUST NOT execute until explicitly approved.
        """
        approvals = self._load_approvals()
        req_seq = len(approvals) + 1
        approval_id = f"APPR-2026-{req_seq:04d}"
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        req = {
            "approval_id": approval_id,
            "timestamp": now_str,
            "actor_student_id": actor_student_id.strip().upper(),
            "target_student_id": target_student_id.strip().upper(),
            "action_type": action_type,
            "requested_changes": requested_changes,
            "description": description,
            "status": "PENDING_APPROVAL",
            "resolution_timestamp": None,
            "resolved_by": None,
            "resolution_reason": None,
            "execution_status": "WAITING_FOR_APPROVAL"
        }

        approvals.append(req)
        self._save_approvals(approvals)
        return req

    def get_approval(self, approval_id: str) -> Optional[Dict[str, Any]]:
        clean_id = approval_id.strip().upper()
        approvals = self._load_approvals()
        for app in approvals:
            if app.get("approval_id", "").upper() == clean_id:
                return app
        return None

    def get_pending_approvals(self, student_id: Optional[str] = None) -> List[Dict[str, Any]]:
        approvals = self._load_approvals()
        pending = [a for a in approvals if a.get("status") == "PENDING_APPROVAL"]
        if student_id and student_id != "GUEST":
            clean_id = student_id.strip().upper()
            pending = [a for a in pending if a.get("target_student_id") == clean_id or a.get("actor_student_id") == clean_id]
        return pending

    def get_all_approvals(self, student_id: Optional[str] = None) -> List[Dict[str, Any]]:
        approvals = self._load_approvals()
        if student_id and student_id != "GUEST":
            clean_id = student_id.strip().upper()
            approvals = [a for a in approvals if a.get("target_student_id") == clean_id or a.get("actor_student_id") == clean_id]
        return approvals

    def resolve_approval(
        self,
        approval_id: str,
        decision: str,  # 'APPROVED' or 'REJECTED'
        resolved_by: str = "Academic Registrar / Human Advisor",
        reason: Optional[str] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Resolves an approval request:
        - If APPROVED: executes the pending record change directly in the database.
        - If REJECTED: aborts without modifying the database.
        Returns: (success: bool, status_message: str, updated_record: Dict)
        """
        clean_id = approval_id.strip().upper()
        clean_decision = decision.strip().upper()
        if clean_decision not in ["APPROVED", "REJECTED"]:
            return False, f"Invalid decision '{decision}'. Must be 'APPROVED' or 'REJECTED'.", {}

        approvals = self._load_approvals()
        target_idx = None
        for i, a in enumerate(approvals):
            if a.get("approval_id", "").upper() == clean_id:
                target_idx = i
                break

        if target_idx is None:
            return False, f"Approval request '{clean_id}' was not found.", {}

        req = approvals[target_idx]
        if req.get("status") != "PENDING_APPROVAL":
            return False, f"Approval request '{clean_id}' has already been resolved with status '{req.get('status')}'.", req

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        req["status"] = clean_decision
        req["resolution_timestamp"] = now_str
        req["resolved_by"] = resolved_by
        req["resolution_reason"] = reason or ("Approved by administrator" if clean_decision == "APPROVED" else "Rejected by institutional policy / student request")

        if clean_decision == "APPROVED":
            # Execute change in student database
            execution_success, exec_msg = self._apply_database_changes(
                target_student_id=req["target_student_id"],
                action_type=req["action_type"],
                changes=req["requested_changes"]
            )
            if execution_success:
                req["execution_status"] = "EXECUTED_SUCCESSFULLY"
                message = f"Approval Granted: {exec_msg}"
            else:
                req["execution_status"] = f"FAILED: {exec_msg}"
                message = f"Approval Granted but execution failed: {exec_msg}"
        else:
            # REJECTED: Strictly abort without changes!
            req["execution_status"] = "ABORTED_NO_DATABASE_MODIFICATION"
            message = f"Approval Rejected: Action '{req['action_type']}' was rejected. No changes were made to official student records."

        approvals[target_idx] = req
        self._save_approvals(approvals)
        return True, message, req

    def _apply_database_changes(
        self,
        target_student_id: str,
        action_type: str,
        changes: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Applies verified changes to `students_database.json`."""
        if not os.path.exists(DB_FILE_PATH):
            return False, "Database file not found."

        try:
            with open(DB_FILE_PATH, "r", encoding="utf-8") as f:
                db = json.load(f)

            found = False
            for s in db.get("students", []):
                if s.get("student_id", "").upper() == target_student_id.upper():
                    found = True
                    if action_type in ["UPDATE_STUDENT_PROFILE", "UPDATE_CONTACT_INFO"]:
                        field = changes.get("field")
                        new_value = changes.get("new_value")
                        if field:
                            s[field] = new_value
                    elif action_type == "CHANGE_ELECTIVE_COURSE":
                        new_elective = changes.get("new_elective")
                        if "preferences" not in s:
                            s["preferences"] = {}
                        s["preferences"]["specialization_interest"] = new_elective
                        s["preferences"]["preferred_elective"] = new_elective
                    elif action_type == "FEE_DEFERRAL_REQUEST":
                        new_due_date = changes.get("requested_due_date", "2026-12-15")
                        if "fee_details" in s:
                            s["fee_details"]["due_date"] = new_due_date
                            s["fee_details"]["deferral_approved"] = True
                    break

            if not found:
                return False, f"Student {target_student_id} not found in database."

            with open(DB_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(db, f, indent=2)

            return True, f"Official database updated for student {target_student_id}."
        except Exception as e:
            return False, f"Database error: {str(e)}"

    def clear_approvals(self):
        self._save_approvals([])


# Global singleton instance
approval_manager = ApprovalManager()
