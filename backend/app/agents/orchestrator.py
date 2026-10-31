import re
import uuid
import hashlib
from typing import Any, Dict, List, Optional, TypedDict
from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, END

from app.schemas.orchestrator import AgentRoute, WorkflowStatus, RouteClassificationResult
from app.core.workflow import WorkflowContext, WorkflowLimitExceededError, DuplicateActionBlockedError
from app.agents.resolve import ResolveAgent
from app.agents.fix import FixAgent
from app.agents.reconcile import ReconcileAgent
from app.agents.revive import ReviveAgent
from app.agents.onboard import OnboardAgent
from app.agents.fieldmate import FieldMateAgent
from app.agents.vasooli import VasooliAgent
from app.adapters.speech import MockSpeechAdapter
from app.policy.audit import audit_log
from app.db.models import Merchant, Task, TaskBucket


class RouterState(TypedDict, total=False):
    merchant_id: str
    query_text: str
    city: str
    actor_id: str
    execution_id: str
    route: AgentRoute
    confidence: float
    reasoning: str
    is_safe: bool
    flagged_patterns: List[str]
    workflow_status: WorkflowStatus
    agent_result: Dict[str, Any]


class SaathiBrainOrchestrator:
    """
    Saathi Brain Master Orchestrator & LangGraph Router (Phase 11).

    Enforces:
    1. Deterministic classification into explicit AgentRoute enum:
       RESOLVE | FIX | RECONCILE | REVIVE | ONBOARD | FIELDMATE | VASOOLI | NEEDS_HUMAN | UNCLEAR
       Strict enum rejection: any unrecognized route falls back to UNCLEAR / NEEDS_HUMAN.
    2. Shared Workflow Contract & Bounded Loop Ceilings:
       - max 5 planner loops, 6 delegations, 12 tool calls, 2 retries
       - Repeated-action guard: hash(execution_id + action_type + target_id + canonical_params)
       - Loop ceiling breach resolves to NEEDS_HUMAN_REVIEW (never silent COMPLETED).
    3. Untrusted content & prompt-injection security layer:
       Coercive, fraud-flavored, or rule-bypass attempts route to NEEDS_HUMAN without executing tools.
    4. Authoritative Audit Telemetry:
       Logs router's decision to employee Activity Log as "Saathi routed to: <Agent>".
    """

    # Prohibited / Prompt Injection / Rule Bypass patterns
    PROMPT_INJECTION_PATTERNS = [
        "ignore rules",
        "ignore the rules",
        "ignore all",
        "ignore previous",
        "ignore previous instructions",
        "system prompt",
        "prompt override",
        "override safety",
        "override rules",
        "bypass policy",
        "bypass safety",
        "jailbreak",
        "disburse without",
        "approve the refund",
        "approve refund without",
        "execute refund without",
        "drop database",
        "delete tables",
        "format disk",
    ]

    # Fraud-flavored or threatening patterns requiring human escalation
    NEEDS_HUMAN_PATTERNS = [
        "hacked",
        "account hacked",
        "stolen money",
        "scam",
        "scammer",
        "bribe",
        "extortion",
        "blackmail",
        "money laundering",
        "threaten",
        "physical violence",
        "beat you up",
        "burn the shop",
        "police case against fraud",
        "lodge a fraud",
        "report fraud to police",
    ]

    # Out of scope patterns
    OUT_OF_SCOPE_PATTERNS = [
        "capital of france",
        "write a poem",
        "crypto trading",
        "bitcoin investment",
        "movie review",
    ]

    def __init__(self, db: Session):
        self.db = db
        self.resolve_agent = ResolveAgent(db)
        self.fix_agent = FixAgent(db)
        self.reconcile_agent = ReconcileAgent(db)
        self.revive_agent = ReviveAgent(db)
        self.onboard_agent = OnboardAgent(db)
        self.fieldmate_agent = FieldMateAgent(db)
        self.vasooli_agent = VasooliAgent(db)
        self.speech_adapter = MockSpeechAdapter()
        self.router_graph = self._build_router_graph()

    def _build_router_graph(self):
        builder = StateGraph(RouterState)

        builder.add_node("classify_intent", self._node_classify_intent)
        builder.add_node("validate_enum_route", self._node_validate_enum_route)
        builder.add_node("dispatch_to_agent", self._node_dispatch_to_agent)

        builder.set_entry_point("classify_intent")
        builder.add_edge("classify_intent", "validate_enum_route")
        builder.add_edge("validate_enum_route", "dispatch_to_agent")
        builder.add_edge("dispatch_to_agent", END)

        return builder.compile()

    def classify_utterance(self, query_text: str) -> RouteClassificationResult:
        """
        Public pure classification helper.
        Deterministic classification into AgentRoute enum.
        """
        text = query_text.strip().lower()

        # 1. Security & Prompt-Injection Check
        for pat in self.PROMPT_INJECTION_PATTERNS:
            if pat in text:
                return RouteClassificationResult(
                    route=AgentRoute.NEEDS_HUMAN,
                    confidence=1.0,
                    reasoning=f"Prohibited prompt injection or rule-bypass attempt detected: '{pat}'",
                    is_safe=False,
                    flagged_patterns=[pat],
                )

        # 2. Fraud & Threatening Check
        for pat in self.NEEDS_HUMAN_PATTERNS:
            if pat in text:
                return RouteClassificationResult(
                    route=AgentRoute.NEEDS_HUMAN,
                    confidence=0.95,
                    reasoning=f"Fraud-flavored or security incident detected: '{pat}'. Escalating to Human Review.",
                    is_safe=True,
                    flagged_patterns=[pat],
                )

        # 3. Out-of-scope Check
        for pat in self.OUT_OF_SCOPE_PATTERNS:
            if pat in text:
                return RouteClassificationResult(
                    route=AgentRoute.NEEDS_HUMAN,
                    confidence=0.90,
                    reasoning=f"Out-of-scope domain request: '{pat}'. Handed to Human Support.",
                    is_safe=True,
                    flagged_patterns=[pat],
                )

        # 4. FieldMate (Sales Beat / Route Planner / Visits)
        fieldmate_keywords = [
            "fieldmate",
            "sales rep",
            "sales route",
            "assigned sales route",
            "visit route",
            "my route",
            "merchant brief",
            "merchant briefs",
            "sales copilot",
            "visit plan",
            "lead pitch",
            "beat plan",
            "prioritized merchant visit",
            "prioritized route",
        ]
        if any(k in text for k in fieldmate_keywords):
            return RouteClassificationResult(
                route=AgentRoute.FIELDMATE,
                confidence=0.98,
                reasoning="Query relates to field sales route planning, merchant visits, or rep briefs.",
            )

        # 5. Vasooli (Store Credit / Udhaar / Consensual Reminders)
        vasooli_keywords = [
            "udhaar",
            "khata",
            "receivable",
            "receivables",
            "vasooli",
            "credit ledger",
            "store credit",
            "remind customer",
            "polite reminder",
            "bought on credit",
            "bought on udhaar",
            "record udhaar",
            "add udhaar",
            "split payment",
            "installment",
        ]
        # Ignore if strictly settlement query
        if any(k in text for k in vasooli_keywords) and not ("settlement" in text or "mdr" in text):
            return RouteClassificationResult(
                route=AgentRoute.VASOOLI,
                confidence=0.98,
                reasoning="Query relates to customer store credit (udhaar), khata recording, or polite payment reminder.",
            )

        # 6. Onboard (KYC Closer / Missing Documents / OCR)
        onboard_keywords = [
            "onboard",
            "onboarding",
            "kyc",
            "document",
            "documents",
            "pan",
            "bank proof",
            "cheque",
            "passbook",
            "shop photo",
            "store photo",
            "signup",
            "application checklist",
            "blurry document",
            "resubmit document",
            "missing document",
            "missing documents",
            "kyc onboarding status",
        ]
        if any(k in text for k in onboard_keywords):
            return RouteClassificationResult(
                route=AgentRoute.ONBOARD,
                confidence=0.97,
                reasoning="Query relates to merchant signup, missing KYC documents, or OCR document verification.",
            )

        # 7. Revive (Dormant Merchant Recovery / Sales Drop / Retention Booster)
        revive_keywords = [
            "volume dropped",
            "sales dropped",
            "sales drop",
            "sales down",
            "slowdown in your soundbox",
            "transaction volume dropped",
            "dormant",
            "revive",
            "retention",
            "kirana booster",
            "decline in sales",
            "volume decline",
        ]
        if any(k in text for k in revive_keywords):
            return RouteClassificationResult(
                route=AgentRoute.REVIVE,
                confidence=0.96,
                reasoning="Query relates to merchant transaction volume decline, dormancy diagnosis, or retention offers.",
            )

        # 8. Reconcile (Settlement Breakdown / Fees / Discrepancy / Chargebacks)
        settlement_keywords = [
            "settlement",
            "settle",
            "reconcile",
            "payout",
            "mismatch",
            "shortfall",
            "ledger difference",
            "bank credit",
            "fees and chargebacks",
            "fees",
            "chargeback",
            "yesterday's settlement",
            "daily settlement breakdown",
            "mdr",
            "unreconciled",
        ]
        if any(k in text for k in settlement_keywords):
            return RouteClassificationResult(
                route=AgentRoute.RECONCILE,
                confidence=0.97,
                reasoning="Query relates to daily payout breakdown, settlement shortfall, fees, or dispute filing.",
            )

        # 9. Fix (Soundbox Telemetry / Remote Reboot / Hardware & Technician)
        device_keywords = [
            "soundbox",
            "sb-",
            "speaker",
            "battery",
            "charge",
            "restart",
            "reboot",
            "red light",
            "green light",
            "silent",
            "chime",
            "chime not heard",
            "not speaking",
            "technician",
            "hardware issue",
        ]
        has_device_serial = bool(re.search(r"SB-[A-Za-z0-9-]+", query_text, re.IGNORECASE))
        if any(k in text for k in device_keywords) or has_device_serial:
            return RouteClassificationResult(
                route=AgentRoute.FIX,
                confidence=0.97,
                reasoning="Query relates to Soundbox device diagnostics, remote reboot, or technician dispatch.",
            )

        # 10. Resolve (Customer Failed Payment / Reversal / Refund Review)
        payment_keywords = [
            "payment failed",
            "failed payment",
            "payment stuck",
            "transaction stuck",
            "deducted",
            "amount deducted",
            "reversal",
            "refund",
            "utr",
            "upi deduction",
            "refund review",
        ]
        has_paytm_tx = bool(re.search(r"PAYTM_[A-Z0-9_]+", query_text, re.IGNORECASE))
        if any(k in text for k in payment_keywords) or has_paytm_tx:
            return RouteClassificationResult(
                route=AgentRoute.RESOLVE,
                confidence=0.96,
                reasoning="Query relates to customer failed or stuck payment, bank reversal status, or refund review.",
            )

        # 11. Unclear / General Greeting
        return RouteClassificationResult(
            route=AgentRoute.UNCLEAR,
            confidence=0.50,
            reasoning="Query is ambiguous, general greeting, or does not clearly match a specialist domain.",
        )

    def _node_classify_intent(self, state: RouterState) -> Dict[str, Any]:
        query_text = state.get("query_text", "")
        classification = self.classify_utterance(query_text)
        return {
            "route": classification.route,
            "confidence": classification.confidence,
            "reasoning": classification.reasoning,
            "is_safe": classification.is_safe,
            "flagged_patterns": classification.flagged_patterns,
        }

    def _node_validate_enum_route(self, state: RouterState) -> Dict[str, Any]:
        """
        Enforce strict enum validation.
        Reject any route not in AgentRoute enum.
        """
        raw_route = state.get("route")
        valid_enum_values = {e.value for e in AgentRoute}

        if not isinstance(raw_route, AgentRoute) and raw_route not in valid_enum_values:
            return {
                "route": AgentRoute.UNCLEAR,
                "reasoning": f"Rejected invalid route '{raw_route}'. Defaulted to UNCLEAR.",
            }

        enum_route = raw_route if isinstance(raw_route, AgentRoute) else AgentRoute(raw_route)
        return {"route": enum_route}

    def _node_dispatch_to_agent(self, state: RouterState) -> Dict[str, Any]:
        route = state["route"]
        merchant_id = state.get("merchant_id", "mer_sharma_kirana")
        query_text = state.get("query_text", "")
        actor_id = state.get("actor_id", "merchant_user")
        city = state.get("city", "Jaipur")
        execution_id = state.get("execution_id", f"exec_wf_{uuid.uuid4().hex[:8]}")

        # Authoritative Audit: "Saathi routed to: <Agent>"
        audit_log(
            db=self.db,
            actor="saathi_brain",
            action=f"Saathi routed to: {route.value}",
            target=merchant_id,
            result="ROUTED",
            policy_decision_id=f"dec_route_{uuid.uuid4().hex[:8]}",
            idempotency_key=f"route_{execution_id}",
        )

        # 1. RESOLVE
        if route == AgentRoute.RESOLVE:
            res = self.resolve_agent.run(
                merchant_id=merchant_id,
                query_text=query_text,
                actor_id=actor_id,
            )
            speech = self.speech_adapter.synthesize(res["agent_reply"], language="hi-IN")
            return {
                "workflow_status": WorkflowStatus.COMPLETED,
                "agent_result": {
                    "agent": "RESOLVE",
                    "reply": res["agent_reply"],
                    "chip_status": res.get("chip_status", "verified"),
                    "branch": res.get("branch"),
                    "explanation_en": res.get("explanation_en"),
                    "explanation_hi": res.get("explanation_hi"),
                    "tx_ref": res.get("tx_ref"),
                    "case_id": res.get("case_id"),
                    "approval_card": res.get("approval_card"),
                    "action_card": None,
                    "breakdown_card": None,
                    "speech_audio_base64": speech.audio_base64,
                    "speech_duration_seconds": speech.duration_seconds,
                },
            }

        # 2. FIX
        elif route == AgentRoute.FIX:
            res = self.fix_agent.run(
                merchant_id=merchant_id,
                query_text=query_text,
                city=city,
                actor_id=actor_id,
            )
            return {
                "workflow_status": WorkflowStatus.COMPLETED,
                "agent_result": {
                    "agent": "FIX",
                    "reply": res["agent_reply"],
                    "chip_status": res.get("chip_status", "verified"),
                    "step": res.get("step"),
                    "technician_booked": res.get("technician_booked", False),
                    "technician_slot": res.get("technician_slot"),
                    "case_id": res.get("case_id"),
                    "action_card": res.get("action_card"),
                    "breakdown_card": None,
                    "approval_card": None,
                    "speech_audio_base64": res.get("speech_audio_base64"),
                    "speech_duration_seconds": res.get("speech_duration_seconds"),
                },
            }

        # 3. RECONCILE
        elif route == AgentRoute.RECONCILE:
            res = self.reconcile_agent.run(
                merchant_id=merchant_id,
                query_text=query_text,
                actor_id=actor_id,
            )
            speech = self.speech_adapter.synthesize(res["agent_reply"], language="hi-IN")
            return {
                "workflow_status": WorkflowStatus.COMPLETED,
                "agent_result": {
                    "agent": "RECONCILE",
                    "reply": res["agent_reply"],
                    "chip_status": res.get("chip_status", "verified"),
                    "branch": res.get("branch"),
                    "settlement_date": res.get("settlement_date"),
                    "breakdown_card": res.get("breakdown_card"),
                    "action_card": res.get("breakdown_card"),
                    "approval_card": None,
                    "dispute_data": res.get("dispute_data"),
                    "speech_audio_base64": speech.audio_base64,
                    "speech_duration_seconds": speech.duration_seconds,
                },
            }

        # 4. REVIVE
        elif route == AgentRoute.REVIVE:
            res = self.revive_agent.run(
                merchant_id=merchant_id,
                actor_id=actor_id,
            )
            speech = self.speech_adapter.synthesize(res["agent_reply"], language="hi-IN")
            return {
                "workflow_status": WorkflowStatus.COMPLETED,
                "agent_result": {
                    "agent": "REVIVE",
                    "reply": res["agent_reply"],
                    "chip_status": res.get("chip_status", "verified"),
                    "branch": res.get("branch"),
                    "diagnosed_cause": res.get("diagnosed_cause"),
                    "checkin_card": res.get("checkin_card"),
                    "action_card": res.get("checkin_card"),
                    "breakdown_card": None,
                    "approval_card": None,
                    "followup_data": res.get("followup_data"),
                    "speech_audio_base64": speech.audio_base64,
                    "speech_duration_seconds": speech.duration_seconds,
                },
            }

        # 5. ONBOARD
        elif route == AgentRoute.ONBOARD:
            res = self.onboard_agent.run(
                merchant_id=merchant_id,
                query_text=query_text,
                actor_id=actor_id,
            )
            speech = self.speech_adapter.synthesize(res["agent_reply"], language="hi-IN")
            return {
                "workflow_status": WorkflowStatus.COMPLETED,
                "agent_result": {
                    "agent": "ONBOARD",
                    "reply": res["agent_reply"],
                    "chip_status": res.get("chip_status", "verified"),
                    "branch": res.get("action_taken"),
                    "missing_item_card": res.get("missing_item_card"),
                    "action_card": res.get("missing_item_card"),
                    "breakdown_card": None,
                    "approval_card": None,
                    "checklist": res.get("checklist"),
                    "verification_result": res.get("verification_result"),
                    "speech_audio_base64": speech.audio_base64,
                    "speech_duration_seconds": speech.duration_seconds,
                },
            }

        # 6. FIELDMATE
        elif route == AgentRoute.FIELDMATE:
            rep_id = actor_id if actor_id.startswith("emp_") else "emp_sales_01"
            res = self.fieldmate_agent.run(
                query_type="GET_ROUTE",
                sales_rep_id=rep_id,
                merchant_id=merchant_id,
            )
            speech = self.speech_adapter.synthesize(res["agent_reply"], language="en-IN")
            return {
                "workflow_status": WorkflowStatus.COMPLETED,
                "agent_result": {
                    "agent": "FIELDMATE",
                    "reply": res["agent_reply"],
                    "chip_status": res.get("chip_status", "verified"),
                    "branch": res.get("action_taken"),
                    "route_items": res.get("route_items"),
                    "brief_detail": res.get("brief_detail"),
                    "action_card": None,
                    "breakdown_card": None,
                    "approval_card": None,
                    "speech_audio_base64": speech.audio_base64,
                    "speech_duration_seconds": speech.duration_seconds,
                },
            }

        # 7. VASOOLI
        elif route == AgentRoute.VASOOLI:
            res = self.vasooli_agent.run(
                query_text=query_text,
                merchant_id=merchant_id,
                actor_id=actor_id,
            )
            speech = self.speech_adapter.synthesize(res["agent_reply"], language="hi-IN")
            return {
                "workflow_status": WorkflowStatus.COMPLETED,
                "agent_result": {
                    "agent": "VASOOLI",
                    "reply": res["agent_reply"],
                    "chip_status": res.get("chip_status", "verified"),
                    "branch": res.get("action_type", "PARSE_QUERY"),
                    "approval_card": res.get("approval_card"),
                    "vasooli_card": res.get("vasooli_card"),
                    "action_card": res.get("action_card") or res.get("approval_card"),
                    "breakdown_card": None,
                    "speech_audio_base64": speech.audio_base64,
                    "speech_duration_seconds": speech.duration_seconds,
                },
            }

        # 8. NEEDS_HUMAN (Security / Prompt Injection / Fraud)
        elif route == AgentRoute.NEEDS_HUMAN:
            # Create human support escalation task
            m_obj = self.db.query(Merchant).filter_by(id=merchant_id).first()
            tenant_id = m_obj.tenant_id if m_obj and m_obj.tenant_id else "tenant_paytm_demo"

            task = Task(
                id=f"task_human_{uuid.uuid4().hex[:8]}",
                tenant_id=tenant_id,
                merchant_id=merchant_id,
                title="Saathi Brain Escalation: Policy / Security / Fraud Review",
                description=f"Automated query flagged: '{query_text}'. Reason: {state.get('reasoning')}",
                bucket=TaskBucket.NEEDS_HUMAN,
                priority="HIGH",
                assigned_to="Pooja Malhotra (Manager)",
                is_synthetic=True,
                environment="DEMO",
            )
            self.db.add(task)
            self.db.commit()

            reply = (
                "Notice: Your request has been routed to a Paytm Senior Human Support Specialist. "
                "Due to security, regulatory compliance, or safety policies, automated execution for this request "
                f"is paused. A support case has been opened (Case ID: {task.id})."
            )
            speech = self.speech_adapter.synthesize(reply, language="en-IN")

            return {
                "workflow_status": WorkflowStatus.NEEDS_HUMAN_REVIEW,
                "agent_result": {
                    "agent": "NEEDS_HUMAN",
                    "reply": reply,
                    "chip_status": "needs_human",
                    "branch": "SECURITY_OR_HUMAN_ESCALATION",
                    "case_id": task.id,
                    "action_card": None,
                    "breakdown_card": None,
                    "approval_card": None,
                    "speech_audio_base64": speech.audio_base64,
                    "speech_duration_seconds": speech.duration_seconds,
                },
            }

        # 9. UNCLEAR (Clarification / Greeting)
        else:
            greeting = (
                "Namaste! I am Saathi, your Kirana AI teammate. "
                "I can explain daily settlements (Reconcile), verify KYC documents (Onboard), "
                "investigate stuck customer payments (Resolve), troubleshoot Soundbox audio (Fix), "
                "assist dormant shop recovery (Revive), or record consensual store credit khata (Vasooli). "
                "How can I help you today?"
            )
            speech = self.speech_adapter.synthesize(greeting, language="hi-IN")

            return {
                "workflow_status": WorkflowStatus.COMPLETED,
                "agent_result": {
                    "agent": "ORCHESTRATOR",
                    "reply": greeting,
                    "chip_status": "verified",
                    "branch": "GREETING",
                    "breakdown_card": None,
                    "action_card": None,
                    "approval_card": None,
                    "speech_audio_base64": speech.audio_base64,
                    "speech_duration_seconds": speech.duration_seconds,
                },
            }

    def route_and_run(
        self,
        merchant_id: str,
        query_text: str,
        city: str = "Jaipur",
        actor_id: str = "merchant_user",
        execution_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Unified single entry point replacing all direct per-agent triggers.
        Runs LangGraph router node and enforces Master Context workflow limits.
        """
        wf_ctx = WorkflowContext(
            execution_id=execution_id,
            db=self.db,
            merchant_id=merchant_id,
            actor_id=actor_id,
        )

        try:
            # Enforce bounded-loop planner limit
            wf_ctx.record_planner_loop()

            initial_state: RouterState = {
                "merchant_id": merchant_id,
                "query_text": query_text,
                "city": city,
                "actor_id": actor_id,
                "execution_id": wf_ctx.execution_id,
            }

            final_state = self.router_graph.invoke(initial_state)
            agent_result = final_state.get("agent_result") or {}
            agent_result["route"] = final_state.get("route")
            agent_result["workflow_status"] = final_state.get("workflow_status", WorkflowStatus.COMPLETED)
            return agent_result

        except WorkflowLimitExceededError as e:
            # Ceiling reached without verified progress -> NEEDS_HUMAN_REVIEW
            wf_ctx.escalate_to_human(str(e))
            reply = f"System alert: Workflow limit exceeded. Escalated to human operator. ({str(e)})"
            return {
                "agent": "ORCHESTRATOR",
                "route": AgentRoute.NEEDS_HUMAN,
                "reply": reply,
                "chip_status": "needs_human",
                "workflow_status": WorkflowStatus.NEEDS_HUMAN_REVIEW,
                "branch": "LOOP_LIMIT_EXCEEDED",
            }
        except DuplicateActionBlockedError as e:
            return {
                "agent": "ORCHESTRATOR",
                "route": AgentRoute.UNCLEAR,
                "reply": f"Duplicate side-effect blocked: {str(e)}",
                "chip_status": "executed",
                "workflow_status": WorkflowStatus.COMPLETED_WITH_WARNINGS,
                "branch": "DUPLICATE_ACTION_BLOCKED",
            }
