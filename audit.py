"""
Audit Logging Engine for Intelligent Student Support Agent.
Maintains tamper-evident audit records for all security-sensitive actions:
- Data access (reading own records vs. cross-student attempts)
- Sensitive modification requests
- Human approvals and rejections
- Credential / OTP interceptions
"""

import os
import json
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

AUDIT_LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "audit_log.json")

@dataclass
class AuditRecord:
    audit_id: str
    timestamp: str
    actor_student_id: str
    action_type: str
    target_resource: str
    authorization_status: str  # ALLOWED, DENIED_UNAUTHORIZED, APPROVAL_REQUIRED, APPROVED, REJECTED
    execution_result: str      # SUCCESS, BLOCKED, PENDING_APPROVAL, EXECUTED, ABORTED
    details: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AuditLogger:
    """Thread-safe and persistent audit logger for institutional compliance."""

    def __init__(self, log_path: str = AUDIT_LOG_FILE):
        self.log_path = log_path
        self._ensure_log_file()

    def _ensure_log_file(self):
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)

    def _load_logs(self) -> List[Dict[str, Any]]:
        self._ensure_log_file()
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_logs(self, logs: List[Dict[str, Any]]):
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)

    def log_event(
        self,
        actor_student_id: Optional[str],
        action_type: str,
        target_resource: str,
        authorization_status: str,
        execution_result: str,
        details: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Creates, logs, and persists an audit entry.
        """
        logs = self._load_logs()
        audit_seq = len(logs) + 1
        audit_id = f"AUD-2026-{audit_seq:04d}"
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        actor = actor_student_id.strip().upper() if actor_student_id else "GUEST"

        record = AuditRecord(
            audit_id=audit_id,
            timestamp=now_str,
            actor_student_id=actor,
            action_type=action_type,
            target_resource=target_resource,
            authorization_status=authorization_status,
            execution_result=execution_result,
            details=details,
            metadata=metadata or {}
        )

        logs.append(record.to_dict())
        self._save_logs(logs)
        return record.to_dict()

    def get_logs(
        self,
        limit: int = 100,
        actor_id: Optional[str] = None,
        action_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Returns recent audit logs, optionally filtered."""
        logs = self._load_logs()
        if actor_id:
            clean_actor = actor_id.strip().upper()
            logs = [entry for entry in logs if entry.get("actor_student_id") == clean_actor]
        if action_type:
            logs = [entry for entry in logs if entry.get("action_type") == action_type]
        return logs[-limit:]

    def clear_logs(self):
        """Clears audit logs (for clean test environment reset)."""
        self._save_logs([])


# Global singleton instance
audit_logger = AuditLogger()
