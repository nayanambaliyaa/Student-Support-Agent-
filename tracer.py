"""
Tracing and Measurement Module for Intelligent Student Support Agent.
Logs task accuracy, tools used, latency, token usage, retrieved evidence,
permission decisions, and audit/approval status for enterprise compliance.
"""

import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict

@dataclass
class ToolExecutionTrace:
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    appropriate: bool = True
    execution_time_ms: float = 0.0

@dataclass
class AgentRunTrace:
    run_id: str
    timestamp: str
    student_id: Optional[str]
    user_query: str
    final_answer: str
    success: bool
    accuracy_notes: str
    tools_called: List[ToolExecutionTrace] = field(default_factory=list)
    latency_seconds: float = 0.0
    token_usage: Dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    retrieved_evidence: List[Dict[str, str]] = field(default_factory=list)
    memory_recalled: List[Dict[str, Any]] = field(default_factory=list)
    memory_stored: List[Dict[str, Any]] = field(default_factory=list)
    privacy_rejections: List[str] = field(default_factory=list)
    thought_steps: List[str] = field(default_factory=list)
    # Identity & Authorization Security Trace
    authorization_status: str = "ALLOWED"  # ALLOWED, DENIED_UNAUTHORIZED, APPROVAL_REQUIRED, NOT_APPLICABLE
    target_student_id: Optional[str] = None
    approval_id: Optional[str] = None
    approval_status: Optional[str] = None
    audit_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ExecutionTracer:
    """Manages recording, computing metrics, and exporting trace records."""

    def __init__(self):
        self.traces: List[AgentRunTrace] = []

    def start_run(self, run_id: str, student_id: Optional[str], query: str) -> Dict[str, Any]:
        return {
            "run_id": run_id,
            "start_time": time.perf_counter(),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "student_id": student_id,
            "target_student_id": None,
            "authorization_status": "ALLOWED",
            "approval_id": None,
            "approval_status": None,
            "audit_id": None,
            "query": query,
            "tools_called": [],
            "retrieved_evidence": [],
            "memory_recalled": [],
            "memory_stored": [],
            "privacy_rejections": [],
            "thought_steps": [],
            "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }

    def record_tool(
        self,
        run_ctx: Dict[str, Any],
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        appropriate: bool = True,
        duration_ms: float = 0.0
    ):
        run_ctx["tools_called"].append(
            ToolExecutionTrace(
                tool_name=tool_name,
                arguments=args,
                result=result,
                appropriate=appropriate,
                execution_time_ms=duration_ms
            )
        )

    def estimate_tokens(self, text: str) -> int:
        """Heuristic token estimation (~4 chars per token)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    def finalize_run(
        self,
        run_ctx: Dict[str, Any],
        final_answer: str,
        success: bool,
        accuracy_notes: str,
        prompt_text: Optional[str] = None
    ) -> AgentRunTrace:
        end_time = time.perf_counter()
        latency = round(end_time - run_ctx["start_time"], 3)

        tokens = run_ctx.get("token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        if tokens.get("total_tokens", 0) == 0:
            prompt_toks = self.estimate_tokens(prompt_text or run_ctx["query"])
            completion_toks = self.estimate_tokens(final_answer)
            tokens = {
                "prompt_tokens": prompt_toks,
                "completion_tokens": completion_toks,
                "total_tokens": prompt_toks + completion_toks
            }

        trace = AgentRunTrace(
            run_id=run_ctx["run_id"],
            timestamp=run_ctx["timestamp"],
            student_id=run_ctx["student_id"],
            user_query=run_ctx["query"],
            final_answer=final_answer,
            success=success,
            accuracy_notes=accuracy_notes,
            tools_called=run_ctx["tools_called"],
            latency_seconds=latency,
            token_usage=tokens,
            retrieved_evidence=run_ctx["retrieved_evidence"],
            memory_recalled=run_ctx["memory_recalled"],
            memory_stored=run_ctx["memory_stored"],
            privacy_rejections=run_ctx["privacy_rejections"],
            thought_steps=run_ctx["thought_steps"],
            authorization_status=run_ctx.get("authorization_status", "ALLOWED"),
            target_student_id=run_ctx.get("target_student_id"),
            approval_id=run_ctx.get("approval_id"),
            approval_status=run_ctx.get("approval_status"),
            audit_id=run_ctx.get("audit_id")
        )

        self.traces.append(trace)
        return trace
