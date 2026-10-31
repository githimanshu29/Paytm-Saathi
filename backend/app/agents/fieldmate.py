import uuid
from typing import Any, Dict, List, Optional, TypedDict
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.tools.fieldmate import FieldMateTools
from app.adapters.speech import MockSpeechAdapter


class FieldMateAgentState(TypedDict):
    sales_rep_id: str
    query_type: str  # GET_ROUTE | GET_BRIEF | EXTRACT_VOICE_NOTE | CONFIRM_VISIT_NOTE | CREATE_LEAD
    merchant_id: Optional[str]
    visit_id: Optional[str]
    raw_audio_or_text: Optional[str]
    expected_version: Optional[int]
    confirmed_notes: Optional[str]
    lead_interest: Optional[str]
    rep_lat: float
    rep_lon: float
    execution_id: str
    actor_id: str
    action_taken: str
    agent_reply: str
    chip_status: str  # verified | executed | pending | awaiting_approval | needs_human
    route_items: Optional[List[Dict[str, Any]]]
    brief_detail: Optional[Dict[str, Any]]
    draft_note: Optional[Dict[str, Any]]
    confirmed_result: Optional[Dict[str, Any]]
    error: Optional[str]


class FieldMateAgent:
    """
    Field Sales Copilot Agent (FieldMate).
    Assists Paytm field sales representatives:
    1. Generates prioritized visit routes with truthful evidence-backed briefs.
    2. Provides contextual talking points and pitches based on real hardware/KYC/metric data.
    3. Transcribes voice notes into candidate CRM drafts with mandatory rep review & confirmation.
    4. Guardrails concurrency with optimistic locking to prevent silent overwrites.
    """

    def __init__(self, db: Session):
        self.db = db
        self.tools = FieldMateTools(db=db)
        self.speech_adapter = MockSpeechAdapter()
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(FieldMateAgentState)

        builder.add_node("route_planner", self._node_route_planner)
        builder.add_node("brief_generator", self._node_brief_generator)
        builder.add_node("voice_note_extractor", self._node_voice_note_extractor)
        builder.add_node("visit_note_confirmer", self._node_visit_note_confirmer)

        def route_dispatcher(state: FieldMateAgentState):
            q_type = state.get("query_type", "GET_ROUTE")
            if q_type == "GET_BRIEF":
                return "brief_generator"
            if q_type == "EXTRACT_VOICE_NOTE":
                return "voice_note_extractor"
            if q_type == "CONFIRM_VISIT_NOTE":
                return "visit_note_confirmer"
            return "route_planner"

        # Direct conditional routing from start
        builder.set_conditional_entry_point(
            route_dispatcher,
            {
                "route_planner": "route_planner",
                "brief_generator": "brief_generator",
                "voice_note_extractor": "voice_note_extractor",
                "visit_note_confirmer": "visit_note_confirmer",
            },
        )

        builder.add_edge("route_planner", END)
        builder.add_edge("brief_generator", END)
        builder.add_edge("voice_note_extractor", END)
        builder.add_edge("visit_note_confirmer", END)

        return builder.compile()

    def _node_route_planner(self, state: FieldMateAgentState) -> Dict[str, Any]:
        sales_rep_id = state.get("sales_rep_id", "emp_sales_01")
        rep_lat = state.get("rep_lat", 26.9150)
        rep_lon = state.get("rep_lon", 75.8150)

        res = self.tools.suggest_visit_order(sales_rep_id, rep_lat, rep_lon)
        if not res.get("found"):
            return {
                "action_taken": "ROUTE_FETCH_FAILED",
                "agent_reply": "Could not retrieve route for sales representative.",
                "chip_status": "needs_human",
                "error": res.get("reason"),
            }

        route = res.get("ordered_route", [])
        top_priority = next((r for r in route if r.get("priority") == "HIGH"), None)
        focus_msg = (
            f" Recommended first stop: {top_priority['store_name']} ({top_priority['evidence_backed_brief']})."
            if top_priority
            else " All high-priority issues resolved."
        )

        reply = (
            f"Found {len(route)} scheduled merchant visits ordered by urgency and proximity.{focus_msg} "
            f"(Note: Heuristic recommendation, not a guaranteed-optimal route)."
        )

        return {
            "action_taken": "ROUTE_PLANNED",
            "agent_reply": reply,
            "chip_status": "executed",
            "route_items": route,
        }

    def _node_brief_generator(self, state: FieldMateAgentState) -> Dict[str, Any]:
        merchant_id = state.get("merchant_id")
        sales_rep_id = state.get("sales_rep_id", "emp_sales_01")
        rep_lat = state.get("rep_lat", 26.9150)
        rep_lon = state.get("rep_lon", 75.8150)

        if not merchant_id:
            return {
                "action_taken": "BRIEF_ERROR",
                "agent_reply": "Merchant ID is required to generate a visit brief.",
                "chip_status": "needs_human",
                "error": "MISSING_MERCHANT_ID",
            }

        res = self.tools.get_merchant_brief(merchant_id, sales_rep_id, rep_lat, rep_lon)
        if not res.get("found"):
            return {
                "action_taken": "BRIEF_FAILED",
                "agent_reply": res.get("reason", "Merchant not found or access denied."),
                "chip_status": "needs_human",
                "error": res.get("error", "NOT_FOUND"),
            }

        reply = (
            f"Visit Brief for {res['store_name']} ({res['merchant_name']}):\n"
            f"• Priority: {res['priority']}\n"
            f"• Key Note: {res['one_line_brief']}\n"
            f"• Pitch: {res['recommended_pitch']}"
        )

        return {
            "action_taken": "BRIEF_GENERATED",
            "agent_reply": reply,
            "chip_status": "executed",
            "brief_detail": res,
        }

    def _node_voice_note_extractor(self, state: FieldMateAgentState) -> Dict[str, Any]:
        visit_id = state.get("visit_id")
        raw_text = state.get("raw_audio_or_text", "")
        sales_rep_id = state.get("sales_rep_id", "emp_sales_01")

        if not visit_id:
            return {
                "action_taken": "EXTRACTION_ERROR",
                "agent_reply": "Visit ID is required to process a voice note.",
                "chip_status": "needs_human",
                "error": "MISSING_VISIT_ID",
            }

        try:
            draft = self.tools.fieldmate_adapter.extract_voice_note_draft(
                visit_id=visit_id,
                raw_transcript=raw_text,
                sales_rep_id=sales_rep_id,
            )
            reply = (
                f"Candidate fields extracted from voice note. "
                f"Review required: Merchant Sentiment: {draft.extracted_candidate_fields.get('merchant_sentiment')}, "
                f"Topic: {draft.extracted_candidate_fields.get('product_discussed')}. "
                f"Please review and confirm to commit to CRM."
            )
            return {
                "action_taken": "DRAFT_EXTRACTED_UNCONFIRMED",
                "agent_reply": reply,
                "chip_status": "awaiting_approval",
                "draft_note": {
                    "visit_id": draft.visit_id,
                    "merchant_id": draft.merchant_id,
                    "raw_transcript": draft.raw_transcript,
                    "extracted_candidate_fields": draft.extracted_candidate_fields,
                    "proposed_lead_interest": draft.proposed_lead_interest,
                    "requires_rep_confirmation": True,
                    "version": draft.version,
                },
            }
        except Exception as e:
            return {
                "action_taken": "EXTRACTION_FAILED",
                "agent_reply": f"Failed to extract candidate fields: {str(e)}",
                "chip_status": "needs_human",
                "error": str(e),
            }

    def _node_visit_note_confirmer(self, state: FieldMateAgentState) -> Dict[str, Any]:
        visit_id = state.get("visit_id")
        expected_version = state.get("expected_version", 1)
        confirmed_notes = state.get("confirmed_notes", "")
        lead_interest = state.get("lead_interest")
        sales_rep_id = state.get("sales_rep_id", "emp_sales_01")
        execution_id = state.get("execution_id", f"exec_conf_{uuid.uuid4().hex[:8]}")

        res = self.tools.save_structured_visit_note(
            visit_id=visit_id,
            expected_version=expected_version,
            confirmed_notes=confirmed_notes,
            sales_rep_id=sales_rep_id,
            lead_interest=lead_interest,
            execution_id=execution_id,
        )

        if not res.get("saved"):
            err_code = res.get("error", "SAVE_FAILED")
            status = "needs_human"
            if err_code == "CONCURRENCY_CONFLICT":
                reply = f"Concurrency Conflict: {res.get('reason')}"
            elif err_code == "POLICY_VIOLATION":
                reply = f"Policy Blocked: {res.get('reason')}"
            else:
                reply = f"Failed to save visit note: {res.get('reason')}"

            return {
                "action_taken": "CONFIRMATION_REJECTED",
                "agent_reply": reply,
                "chip_status": status,
                "error": err_code,
            }

        reply = (
            f"Visit note confirmed and saved to CRM (Version {res.get('new_version')}). "
            f"Lead Interest: {res.get('lead_interest') or 'None'}. "
            f"Audit log #{res.get('audit_event_id')} emitted."
        )

        return {
            "action_taken": "NOTE_CONFIRMED_AND_PERSISTED",
            "agent_reply": reply,
            "chip_status": "verified",
            "confirmed_result": res,
        }

    def run(
        self,
        query_type: str,
        sales_rep_id: str = "emp_sales_01",
        merchant_id: Optional[str] = None,
        visit_id: Optional[str] = None,
        raw_audio_or_text: Optional[str] = None,
        expected_version: Optional[int] = 1,
        confirmed_notes: Optional[str] = None,
        lead_interest: Optional[str] = None,
        rep_lat: float = 26.9150,
        rep_lon: float = 75.8150,
    ) -> Dict[str, Any]:
        initial_state: FieldMateAgentState = {
            "sales_rep_id": sales_rep_id,
            "query_type": query_type,
            "merchant_id": merchant_id,
            "visit_id": visit_id,
            "raw_audio_or_text": raw_audio_or_text,
            "expected_version": expected_version,
            "confirmed_notes": confirmed_notes,
            "lead_interest": lead_interest,
            "rep_lat": rep_lat,
            "rep_lon": rep_lon,
            "execution_id": f"exec_fmate_{uuid.uuid4().hex[:8]}",
            "actor_id": sales_rep_id,
            "action_taken": "INITIALIZED",
            "agent_reply": "",
            "chip_status": "pending",
            "route_items": None,
            "brief_detail": None,
            "draft_note": None,
            "confirmed_result": None,
            "error": None,
        }
        return self.graph.invoke(initial_state)
