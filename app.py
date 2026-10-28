"""
Intelligent Student Support Agent - Enterprise Academic Dashboard & Chatbot
PGDM (Big Data Analytics / AI & Data Science) | Batch 2025-27
Agentic AI Engineering - Enterprise Safe Edition
"""

import os
import time
import json
import streamlit as st
import pandas as pd
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

# ---------------------------------------------------------------------------
# 1. Page Configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CampusGPT | Enterprise Student Support Agent",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------------------------
# 2. Advanced Professional Styling
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .block-container {
        padding-top: 1rem;
        padding-bottom: 3rem;
        max-width: 100%;
    }

    .academic-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 14px;
        padding: 1.25rem 1.75rem;
        margin-bottom: 1.25rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.25);
    }
    .header-badge {
        background: #e11d48;
        color: #ffffff;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        padding: 0.25rem 0.65rem;
        border-radius: 6px;
        display: inline-block;
        margin-bottom: 0.35rem;
    }
    .header-title {
        font-size: 1.4rem;
        font-weight: 700;
        color: #f8fafc;
        margin: 0;
    }
    .header-subtitle {
        font-size: 0.85rem;
        color: #94a3b8;
        margin-top: 0.2rem;
    }

    .status-allowed {
        background-color: rgba(16, 185, 129, 0.2);
        color: #34d399;
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
    .status-blocked {
        background-color: rgba(244, 63, 94, 0.2);
        color: #fb7185;
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
    .status-pending {
        background-color: rgba(245, 158, 11, 0.2);
        color: #fbbf24;
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 3. Session State Initialization
# ---------------------------------------------------------------------------
if "agent" not in st.session_state:
    st.session_state.agent = StudentSupportAgent()
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "latest_trace" not in st.session_state:
    st.session_state.latest_trace = None
if "pending_query" not in st.session_state:
    st.session_state.pending_query = None
if "eval_benchmark" not in st.session_state:
    st.session_state.eval_benchmark = None

memory_store = PersistentMemoryStore()
db_data = _load_db()
students_list = db_data.get("students", [])

def stream_generator(text: str, delay: float = 0.005):
    for word in text.split(" "):
        yield word + " "
        time.sleep(delay)

# ---------------------------------------------------------------------------
# 4. Sidebar: Student Identity, Memory, and Approvals
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🎓 Student Identity & Session")
    
    student_options = {s["student_id"]: f"{s['name']} ({s['student_id']})" for s in students_list}
    student_options["GUEST"] = "Guest Student (Unauthenticated)"

    selected_student_id = st.selectbox(
        "Signed-In Student Account:",
        options=list(student_options.keys()),
        format_func=lambda x: student_options[x],
        index=0
    )

    current_student = next((s for s in students_list if s["student_id"] == selected_student_id), None)

    if current_student:
        st.markdown(f"""
        <div style="background:#1e293b; border:1px solid #334155; border-radius:10px; padding:12px; margin-bottom:12px;">
            <div style="font-weight:700; color:#f8fafc; font-size:0.95rem;">{current_student['name']}</div>
            <div style="color:#94a3b8; font-size:0.75rem;">{current_student['programme']}</div>
            <div style="display:flex; justify-content:space-between; margin-top:8px; font-size:0.75rem;">
                <span style="color:#38bdf8; font-weight:600;">CGPA: {current_student['cgpa']} / 10</span>
                <span style="color:#34d399; font-weight:600;">Attendance: {current_student['attendance_percentage']}%</span>
            </div>
            <div style="margin-top:6px; font-size:0.75rem; color:#f59e0b; font-weight:600;">
                Tuition Due: INR {current_student.get('fee_details', {}).get('outstanding_due', 0):,}
            </div>
            <div style="margin-top:4px; font-size:0.7rem; color:#94a3b8;">
                Phone: <span style="color:#cbd5e1;">{current_student.get('phone', '+91-9811002233')}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.warning("Browsing as Unauthenticated Guest. Private student records will be blocked.")

    # Pending Approvals in Sidebar
    pending_apps = approval_manager.get_pending_approvals(selected_student_id)
    if pending_apps:
        st.markdown(f"**⚠️ Pending Human Approvals ({len(pending_apps)}):**")
        for app in pending_apps:
            with st.expander(f"Pending: `{app['approval_id']}`", expanded=True):
                st.caption(f"Action: {app['action_type']}")
                st.json(app["requested_changes"])
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Approve", key=f"app_{app['approval_id']}", use_container_width=True):
                        resolve_approval_action(app['approval_id'], "APPROVED", resolved_by=selected_student_id)
                        st.success("Approved!")
                        st.rerun()
                with c2:
                    if st.button("Reject", key=f"rej_{app['approval_id']}", use_container_width=True):
                        resolve_approval_action(app['approval_id'], "REJECTED", resolved_by=selected_student_id)
                        st.warning("Rejected!")
                        st.rerun()

    st.markdown("---")
    st.markdown("#### 🧠 Profile Memory (Persistent)")
    student_mem = memory_store.get_student_memory(selected_student_id) if selected_student_id != "GUEST" else {}
    if student_mem:
        for k, v in student_mem.items():
            st.markdown(f"<div style='font-size:0.75rem; color:#94a3b8;'><b>{k.replace('_',' ').title()}</b>: {v}</div>", unsafe_allow_html=True)
    else:
        st.caption("No custom memory stored for this profile.")

    if st.button("🗑️ Reset Profile Memory", use_container_width=True):
        memory_store.clear_all()
        st.toast("Persistent memory reset!")
        st.rerun()

    if st.button("🔄 Clear Chat Conversation", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.latest_trace = None
        st.rerun()


# ---------------------------------------------------------------------------
# 5. Header Bar
# ---------------------------------------------------------------------------
st.markdown("""
<div class="academic-header">
    <div>
        <div class="header-badge">Enterprise Edition: Safe & Auditable</div>
        <div class="header-title">CampusGPT Student Support Agent</div>
        <div class="header-subtitle">PGDM (Big Data Analytics / AI & Data Science) • Batch 2025-27</div>
    </div>
    <div style="text-align:right;">
        <div style="font-size:0.85rem; color:#38bdf8; font-weight:600;">Autonomous Decision Engine</div>
        <div style="font-size:0.75rem; color:#94a3b8; margin-top:4px;">Identity • Authorization • Human Approval • Auditability</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Main Navigation Tabs
tab_console, tab_audit, tab_approvals, tab_evaluation, tab_handbook, tab_database = st.tabs([
    "💬 Support Desk & Chat",
    "🛡️ Audit Trail Log",
    "🔒 Human Approvals",
    "📊 System Verification & Benchmark",
    "📖 Policy Handbook (Selective RAG)",
    "🗄️ Student Database & Tools"
])


# ===========================================================================
# TAB 1: SUPPORT DESK & CHAT
# ===========================================================================
with tab_console:
    st.markdown("**🛡️ One-Click Enterprise Demonstration Scenarios:**")
    
    col1, col2, col3 = st.columns(3)
    col4, col5, col6 = st.columns(3)

    with col1:
        if st.button("🟢 A. Own Fee Status (Allowed)", use_container_width=True):
            st.session_state.pending_query = "What is my current fee status and scholarship details?"
    with col2:
        if st.button("🛑 B. Another Student's Record (Blocked)", use_container_width=True):
            st.session_state.pending_query = "Can you show me the fee details and CGPA of student STU-2025-002?"
    with col3:
        if st.button("⏳ C. Sensitive Record Change (Approval Req)", use_container_width=True):
            st.session_state.pending_query = "Please update my contact phone to +91-9876543210"
    with col4:
        if st.button("❌ D. Reject Pending Action", use_container_width=True):
            st.session_state.pending_query = "Reject APPR-2026-0001"
    with col5:
        if st.button("🛡️ E. Sensitive OTP & Password Guardrail", use_container_width=True):
            st.session_state.pending_query = "My netbanking password is MySecretPass#99 and OTP is 482910, please remember this for my payment."
    with col6:
        if st.button("⏳ A1. Portal Glitch Policy (RAG)", use_container_width=True):
            st.session_state.pending_query = "The payment portal failed. Can I pay on the next working day?"

    st.markdown("---")

    chat_col, obs_col = st.columns([1.8, 1.2])

    with chat_col:
        st.markdown("##### 💬 Conversation Stream")
        
        if len(st.session_state.chat_history) == 0:
            student_name = current_student['name'] if current_student else "Student"
            st.info(f"👋 Welcome, **{student_name}**! Click any button above or type your inquiry below.")

        for chat in st.session_state.chat_history:
            with st.chat_message(chat["role"], avatar="🧑‍🎓" if chat["role"] == "user" else "🤖"):
                st.markdown(chat["content"])

        user_input = st.chat_input("Ask a question about fees, record updates, or test guardrails...")
        if st.session_state.pending_query:
            user_input = st.session_state.pending_query
            st.session_state.pending_query = None

        if user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input, "trace": None})
            with st.chat_message("user", avatar="🧑‍🎓"):
                st.markdown(user_input)

            with st.chat_message("assistant", avatar="🤖"):
                active_id = None if selected_student_id == "GUEST" else selected_student_id
                
                with st.spinner("Evaluating identity, authorization & policy..."):
                    response = st.session_state.agent.run(
                        query=user_input,
                        student_id=active_id,
                        session_id="AGENT_CONSOLE"
                    )
                    final_ans = response["answer"]
                    trace = response["trace"]
                    st.session_state.latest_trace = trace

                st.write_stream(stream_generator(final_ans))

            st.session_state.chat_history.append({"role": "assistant", "content": final_ans, "trace": trace})
            st.rerun()

    # RIGHT COLUMN: OBSERVABILITY, AUDIT & PERMISSIONS
    with obs_col:
        st.markdown("##### 🔬 Live Agent Telemetry & Permission Trace")
        
        trace = st.session_state.latest_trace
        if trace:
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Latency", f"{trace.latency_seconds:.3f}s")
            with m2:
                st.metric("Total Tokens", f"{trace.token_usage.get('total_tokens', 0)}")
            with m3:
                perm_stat = trace.authorization_status
                st.metric("Permission", perm_stat)

            st.markdown("---")
            st.markdown("**🛡️ Authorization & Identity Decision:**")
            if trace.authorization_status == "ALLOWED":
                st.success("✅ **ALLOWED**: Access granted to own student record.")
            elif trace.authorization_status == "DENIED_UNAUTHORIZED":
                st.error("🛑 **DENIED_UNAUTHORIZED**: Code-enforced gate blocked cross-student access or credential storage.")
            elif trace.authorization_status == "APPROVAL_REQUIRED":
                st.warning("⚠️ **APPROVAL_REQUIRED**: Sensitive modification paused waiting for human confirmation.")

            st.markdown("**🔧 Tools Invoked**:")
            if trace.tools_called:
                for tc in trace.tools_called:
                    st.markdown(f"Tool: `{tc.tool_name}` ({tc.execution_time_ms} ms)")
                    st.json(tc.arguments)
            else:
                st.caption("None (Direct Authorization Gate / Policy RAG)")

            if trace.thought_steps:
                st.markdown("**🧠 Reasoning Steps**:")
                for step in trace.thought_steps:
                    st.caption(f"• {step}")

            if trace.retrieved_evidence:
                st.markdown("**📑 Retrieved Policy Evidence (RAG)**:")
                for ev in trace.retrieved_evidence:
                    st.info(f"Chunk ID: `{ev.get('chunk_id')}` — {ev.get('title')}")


# ===========================================================================
# TAB 2: AUDIT TRAIL LOG
# ===========================================================================
with tab_audit:
    st.subheader("🛡️ Institutional Tamper-Evident Audit Records")
    st.markdown("Shows who requested the action, what was attempted, whether it was allowed or approved, and the final result.")

    all_logs = audit_logger.get_logs(limit=200)
    if all_logs:
        df_logs = pd.DataFrame(all_logs)
        cols = ["audit_id", "timestamp", "actor_student_id", "action_type", "target_resource", "authorization_status", "execution_result", "details"]
        st.dataframe(df_logs[cols], use_container_width=True, hide_index=True)
    else:
        st.info("No audit logs recorded yet.")


# ===========================================================================
# TAB 3: HUMAN APPROVALS MANAGER
# ===========================================================================
with tab_approvals:
    st.subheader("🔒 Human-in-the-Loop Approval Manager")
    st.markdown("Sensitive actions cannot execute automatically and must wait for human confirmation.")

    all_apps = approval_manager.get_all_approvals()
    if all_apps:
        df_apps = pd.DataFrame(all_apps)
        st.dataframe(df_apps[["approval_id", "timestamp", "actor_student_id", "target_student_id", "action_type", "status", "execution_status", "resolved_by"]], use_container_width=True, hide_index=True)
    else:
        st.info("No approval requests generated yet.")


# ===========================================================================
# TAB 4: COMPARATIVE EVALUATION TABLE
# ===========================================================================
with tab_evaluation:
    st.subheader("📊 System Verification & Performance Benchmark")
    
    if st.button("🚀 Run Comprehensive Benchmark Suite"):
        with st.spinner("Executing benchmark across all security and functional scenarios..."):
            a1_res = run_assignment1_benchmarks(st.session_state.agent)
            a2_res = run_assignment2_benchmarks(st.session_state.agent)
            report_md = generate_comparative_evaluation_markdown(a1_res, a2_res)
            st.session_state.eval_benchmark = {"a1": a1_res, "a2": a2_res, "report": report_md}

    if st.session_state.eval_benchmark:
        st.markdown(st.session_state.eval_benchmark["report"])
    else:
        st.info("Click the button above to run the comparative evaluation.")


# ===========================================================================
# TAB 5: POLICY HANDBOOK (SELECTIVE RAG)
# ===========================================================================
with tab_handbook:
    st.subheader("📖 Official Student Policy Handbook & Semantic Chunks")
    retriever = PolicyRetriever()
    chunks = retriever.get_all_chunks()
    st.info(f"Knowledge Base indexed into **{len(chunks)} semantic chunks**.")
    for c in chunks:
        with st.expander(f"📑 {c['title']} (`{c['chunk_id']}`)", expanded=False):
            st.markdown(c["content"])


# ===========================================================================
# TAB 6: STUDENT DATABASE & TOOL REGISTRY
# ===========================================================================
with tab_database:
    st.subheader("🗄️ Institutional Student Registry & Tools")
    st.markdown("#### Student Records Database:")
    db_fresh = _load_db()
    st.dataframe(pd.DataFrame(db_fresh.get("students", []))[["student_id", "name", "programme", "batch", "cgpa", "attendance_percentage", "email", "phone"]], use_container_width=True)
    st.markdown("#### Helpdesk Support Tickets:")
    tickets = db_fresh.get("support_tickets", [])
    if tickets:
        st.dataframe(pd.DataFrame(tickets), use_container_width=True)
