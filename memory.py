"""
Persistent Memory Store with Built-in Privacy & Sensitivity Guardrails.
Stores persistent profile & preference facts across sessions while rejecting
sensitive credentials (cards, passwords, OTPs) and transient states (sleepy, hungry).
Integrates directly with institutional audit logging.
"""

import os
import re
import json
import time
from typing import Dict, Any, List, Optional, Tuple
from agent.audit import audit_logger

MEMORY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "persistent_memory.json")

class PrivacyGuardrail:
    """
    Evaluates whether an incoming fact is safe for long-term storage or if it
    contains sensitive/temporary data that MUST NOT be persisted.
    """

    # Comprehensive regex patterns for sensitive credentials, OTPs, passwords & PII
    SENSITIVE_PATTERNS = [
        (r"\b(?:\d[ -]*?){13,16}\b", "CREDIT_DEBIT_CARD", "Credit or debit card number detected"),
        (r"\b(cvv|cvc|card security code)[\s:]*([0-9]{3,4})\b", "CARD_CVV", "Card CVV/CVC security code detected"),
        (r"\b(otp|one[- ]?time[- ]?password|verification code)[\s:=is]*([0-9]{4,8})\b", "OTP", "One-Time Password (OTP) detected"),
        (r"\b(password|pwd|passcode|login credential|secret pin)[\s:=is]+([^\s,]+)", "CREDENTIALS", "Account password or security PIN detected"),
        (r"\b(netbanking password|upi pin)[\s:=is]+([0-9a-zA-Z]+)\b", "BANKING_PIN", "Financial PIN or banking password detected")
    ]

    # Transient, ephemeral, or emotional states that should not be saved as long-term profile memory
    TRANSIENT_PATTERNS = [
        (r"\b(feeling sleepy|feeling tired|exhausted|gonna sleep|taking a nap)\b", "TRANSIENT_MOOD", "Transient physical or fatigue state (not relevant for institutional student profile)"),
        (r"\b(hungry|eating lunch|eating dinner|in the cafeteria|getting a coffee)\b", "TRANSIENT_STATE", "Temporary fleeting daily activity"),
        (r"\b(weather is|it is raining outside|sunny day)\b", "EPHEMERAL_WEATHER", "Ephemeral non-academic weather observation"),
        (r"\b(bored|headache right now|feeling lazy)\b", "TRANSIENT_EMOTION", "Temporary emotional state")
    ]

    @classmethod
    def evaluate(cls, text: str, actor_student_id: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
        """
        Returns:
            (is_allowed: bool, reason: str, violation_type: Optional[str])
        """
        text_lower = text.lower()

        # 1. Check sensitive credentials (OTP, passwords, cards, pins)
        for pattern, violation_type, reason in cls.SENSITIVE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                rejection_msg = f"REJECTED [Privacy Violation]: {reason}. Sensitive credentials are never stored in persistent memory."
                audit_logger.log_event(
                    actor_student_id=actor_student_id or "GUEST",
                    action_type="CREDENTIAL_INTERCEPTION",
                    target_resource="Persistent Memory Store",
                    authorization_status="DENIED_UNAUTHORIZED",
                    execution_result="BLOCKED_FROM_PERSISTENT_MEMORY",
                    details=f"Intercepted sensitive {violation_type} in user input; strictly blocked from persistent storage."
                )
                return False, rejection_msg, violation_type

        # 2. Check transient / temporary state
        for pattern, violation_type, reason in cls.TRANSIENT_PATTERNS:
            if re.search(pattern, text_lower):
                rejection_msg = f"REJECTED [Temporary Info]: {reason}. Persistent memory only preserves long-term student preferences and academic facts."
                audit_logger.log_event(
                    actor_student_id=actor_student_id or "GUEST",
                    action_type="TRANSIENT_DATA_FILTERED",
                    target_resource="Persistent Memory Store",
                    authorization_status="DENIED_UNAUTHORIZED",
                    execution_result="FILTERED",
                    details=f"Filtered out transient state ({violation_type}) from profile memory."
                )
                return False, rejection_msg, violation_type

        return True, "ACCEPTED: Information is suitable for long-term persistent memory.", None


class PersistentMemoryStore:
    """
    Session-independent storage for student preferences, programme details, and background facts.
    """

    def __init__(self, storage_path: str = MEMORY_FILE_PATH):
        self.storage_path = storage_path
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not os.path.exists(self.storage_path):
            initial_data = {
                "STU-2025-001": {
                    "programme": "PGDM (Artificial Intelligence & Data Science)",
                    "specialization_preference": "Deep Learning & MLOps",
                    "preferred_study_mode": "Evening & Weekend practical labs",
                    "career_goal": "AI Engineer in FinTech"
                },
                "STU-2025-002": {
                    "programme": "PGDM (Big Data Analytics)",
                    "specialization_preference": "Financial Data Analytics",
                    "preferred_contact_method": "SMS alerts for deadlines"
                }
            }
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(initial_data, f, indent=2)

    def _load_data(self) -> Dict[str, Dict[str, Any]]:
        self._ensure_file_exists()
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_data(self, data: Dict[str, Dict[str, Any]]):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_student_memory(self, student_id: str) -> Dict[str, Any]:
        """Retrieve all persistent facts remembered about a student."""
        if not student_id or student_id == "GUEST":
            return {}
        data = self._load_data()
        return data.get(student_id, {})

    def remember_fact(
        self,
        student_id: str,
        key: str,
        value: str,
        bypass_guardrail: bool = False
    ) -> Tuple[bool, str]:
        """
        Attempts to store a fact. Passes through PrivacyGuardrail first.
        Returns (success: bool, status_message: str).
        """
        if not student_id or student_id == "GUEST":
            return False, "Failed to store: Valid Student ID is required to bind persistent memory."

        raw_content = f"{key}: {value}"
        if not bypass_guardrail:
            is_allowed, reason, violation = PrivacyGuardrail.evaluate(raw_content, actor_student_id=student_id)
            if not is_allowed:
                return False, reason

        data = self._load_data()
        if student_id not in data:
            data[student_id] = {}

        data[student_id][key] = value
        self._save_data(data)
        
        audit_logger.log_event(
            actor_student_id=student_id,
            action_type="PERSISTENT_MEMORY_SAVED",
            target_resource=f"{student_id}.memory.{key}",
            authorization_status="ALLOWED",
            execution_result="SUCCESS",
            details=f"Persisted profile fact '{key}' to student memory."
        )
        return True, f"Successfully persisted '{key}' to long-term memory for {student_id}."

    def extract_and_store_memory_from_query(
        self,
        student_id: str,
        user_query: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Analyzes user statement to check if user is asking the agent to remember something or provides credentials.
        Returns (attempted: bool, success_or_rejection_message: Optional[str], stored_key: Optional[str])
        """
        q_lower = user_query.lower()
        remember_triggers = ["remember that", "remember:", "note that", "save my", "my preference is", "my preferred", "i want to specialize in"]
        
        matches_trigger = any(t in q_lower for t in remember_triggers)
        # Check if user mentions sensitive info directly even without explicit "remember"
        contains_sensitive = any(re.search(pat[0], user_query, re.IGNORECASE) for pat in PrivacyGuardrail.SENSITIVE_PATTERNS)
        contains_transient = any(re.search(pat[0], q_lower) for pat in PrivacyGuardrail.TRANSIENT_PATTERNS)

        if not (matches_trigger or contains_sensitive or contains_transient):
            return False, None, None

        # Check guardrail first
        is_safe, message, violation = PrivacyGuardrail.evaluate(user_query, actor_student_id=student_id)
        if not is_safe:
            return True, message, None

        if not student_id or student_id == "GUEST":
            return True, "Unable to store memory: You are in guest mode. Please sign in to save preferences to your profile.", None

        # If safe, extract key and value
        key = "general_preference"
        val = user_query
        for t in ["remember that", "remember:", "note that", "save my"]:
            if t in q_lower:
                idx = q_lower.find(t) + len(t)
                val = user_query[idx:].strip().strip(".")
                break

        if "elective" in q_lower or "subject" in q_lower:
            key = "preferred_elective"
        elif "career" in q_lower or "job" in q_lower or "goal" in q_lower:
            key = "career_goal"
        elif "programme" in q_lower or "course" in q_lower:
            key = "programme_interest"
        elif "contact" in q_lower or "email" in q_lower or "phone" in q_lower:
            key = "contact_preference"

        success, save_msg = self.remember_fact(student_id, key, val)
        return True, save_msg, key

    def clear_all(self):
        """Reset persistent memory to fresh state for testing."""
        if os.path.exists(self.storage_path):
            os.remove(self.storage_path)
        self._ensure_file_exists()
