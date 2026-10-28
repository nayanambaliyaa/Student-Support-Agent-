"""
FastAPI Backend Server for CampusGPT Safe Student Support Agent (Enterprise Edition).
Hosts Agent REST APIs, Authorization Engine, Audit Logger, Approval Manager,
and serves the React.js Production Single Page Application.
"""

import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from agent.core_agent import StudentSupportAgent
from agent.tools import AVAILABLE_TOOLS, _load_db, resolve_approval_action
from agent.memory import PersistentMemoryStore
from agent.retriever import PolicyRetriever
from agent.audit import audit_logger
from agent.approvals import approval_manager
from agent.test_scenarios import (
    run_assignment1_benchmarks,
    run_assignment2_benchmarks,
    generate_comparative_evaluation_markdown
)

app = FastAPI(title="CampusGPT Safe & Production-Aware Agentic API", version="2.5.0")

# Enable CORS for React Dev Server & Local Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Instances
agent = StudentSupportAgent()
memory_store = PersistentMemoryStore()
retriever = PolicyRetriever()

class ChatRequest(BaseModel):
    query: str
    student_id: Optional[str] = None
    session_id: Optional[str] = "SESSION_REACT"

class ResolveApprovalRequest(BaseModel):
    approval_id: str
    decision: str  # "APPROVED" or "REJECTED"
    resolved_by: Optional[str] = "Academic Registrar / Human Advisor"
    reason: Optional[str] = None

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    
    clean_id = None if req.student_id in ["GUEST", "", None] else req.student_id
    response = agent.run(
        query=req.query,
        student_id=clean_id,
        session_id=req.session_id
    )
    
    trace_dict = response["trace"].to_dict()
    return {
        "answer": response["answer"],
        "trace": trace_dict,
        "run_id": response["run_id"]
    }

@app.get("/api/audit-logs")
async def get_audit_logs(limit: int = 100, actor_id: Optional[str] = None):
    """Returns recent tamper-evident audit logs."""
    logs = audit_logger.get_logs(limit=limit, actor_id=actor_id)
    return {"audit_logs": logs}

@app.get("/api/approvals")
async def get_approvals(student_id: Optional[str] = None):
    """Returns pending and historical approval requests."""
    clean_id = None if student_id in ["GUEST", "", None] else student_id
    pending = approval_manager.get_pending_approvals(clean_id)
    all_reqs = approval_manager.get_all_approvals(clean_id)
    return {
        "pending_approvals": pending,
        "all_approvals": all_reqs
    }

@app.post("/api/approvals/resolve")
async def resolve_approval_endpoint(req: ResolveApprovalRequest):
    """Approves or rejects a sensitive action."""
    res = resolve_approval_action(
        approval_id=req.approval_id,
        decision=req.decision,
        resolved_by=req.resolved_by,
        reason=req.reason
    )
    if res.get("status") == "ERROR":
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res

@app.get("/api/benchmark")
@app.get("/api/benchmark/assignment2")
async def benchmark_assignment2_endpoint():
    """Runs Assignment 2 Privacy & Safety benchmark and returns comparative markdown."""
    a1_results = run_assignment1_benchmarks(agent)
    a2_results = run_assignment2_benchmarks(agent)
    markdown_report = generate_comparative_evaluation_markdown(a1_results, a2_results)
    return {
        "assignment1_results": a1_results,
        "assignment2_results": a2_results,
        "markdown_report": markdown_report
    }

@app.get("/api/benchmark/assignment1")
async def benchmark_assignment1_endpoint():
    """Runs Assignment 1 baseline benchmark."""
    results = run_assignment1_benchmarks(agent)
    return {"results": results}

@app.get("/api/students")
async def get_students():
    db = _load_db()
    return {
        "students": db.get("students", []),
        "support_tickets": db.get("support_tickets", [])
    }

@app.get("/api/memory")
async def get_memory(student_id: Optional[str] = None):
    if not student_id or student_id == "GUEST":
        return {"memory": {}}
    return {"memory": memory_store.get_student_memory(student_id)}

@app.post("/api/memory/clear")
async def clear_memory():
    memory_store.clear_all()
    return {"status": "SUCCESS", "message": "Persistent memory reset."}

@app.get("/api/policy")
async def get_policy_chunks():
    chunks = retriever.get_all_chunks()
    return {"chunks": chunks}

@app.get("/api/faqs")
async def get_top_faqs():
    faq_path = os.path.join(os.path.dirname(__file__), "data", "top_50_student_questions.json")
    if os.path.exists(faq_path):
        with open(faq_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"categories": []}

# Serve React Production Build if dist exists
dist_dir = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(dist_dir):
    app.mount("/", StaticFiles(directory=dist_dir, html=True), name="static")

if __name__ == "__main__":
    print("Starting CampusGPT Safe Student Support Agent on http://localhost:8000 ...")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
