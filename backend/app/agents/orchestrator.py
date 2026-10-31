import re
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.agents.resolve import ResolveAgent
from app.agents.fix import FixAgent
from app.agents.reconcile import ReconcileAgent
from app.agents.revive import ReviveAgent
from app.agents.onboard import OnboardAgent
from app.adapters.speech import MockSpeechAdapter
from app.policy.audit import audit_log

class SaathiBrainOrchestrator:
    """
    Unified Orchestrator for Paytm Saathi.
    Routes queries to specialist agents:
    - Specialist 1: Resolve (Failed payments, bank reversals, refund reviews)
    - Specialist 2: Fix (Soundbox diagnostics, remote restart, technician visits)
    - Specialist 3: Reconcile (Settlement breakdown, fee/chargeback audits, dispute cases)
    - Specialist 4: Revive (Dormant merchant reactivation, root-cause diagnosis, retention check-ins)
    - Specialist 5: Onboard (KYC closer, untrusted OCR extraction, missing doc chaser, authorized verification)
    """

    def __init__(self, db: Session):
        self.db = db
        self.resolve_agent = ResolveAgent(db)
        self.fix_agent = FixAgent(db)
        self.reconcile_agent = ReconcileAgent(db)
        self.revive_agent = ReviveAgent(db)
        self.onboard_agent = OnboardAgent(db)
        self.speech_adapter = MockSpeechAdapter()

    def route_and_run(
        self,
        merchant_id: str,
        query_text: str,
        city: str = "Jaipur",
        actor_id: str = "merchant_user",
    ) -> Dict[str, Any]:
        query_clean = query_text.strip().lower()

        # 1. Settlement / Reconcile Keywords -> Reconcile Agent
        settlement_keywords = [
            "settlement",
            "settle",
            "reconcile",
            "payout",
            "mismatch",
            "shortfall",
            "ledger",
            "bank credit",
            "charges",
            "difference",
            "yesterday's settlement",
            "yesterday settlement",
            "statement",
            "deposit",
            "unreconciled",
            "fees",
            "chargeback",
            "chargebacks",
            "mdr",
            "breakdown",
            "9200",
            "11800",
            "13000",
        ]
        is_settlement_intent = any(k in query_clean for k in settlement_keywords)

        # 2. Device / Soundbox Keywords -> Fix Agent
        device_keywords = [
            "soundbox",
            "device",
            "speaker",
            "battery",
            "charge",
            "restart",
            "reboot",
            "light",
            "silent",
            "technician",
            "hardware",
            "sb-",
            "red light",
            "green light",
            "power button",
            "volume",
        ]
        is_device_intent = any(k in query_clean for k in device_keywords) or bool(
            re.search(r"SB-[A-Za-z0-9-]+", query_text, re.IGNORECASE)
        )

        # 3. Payment / Transaction Keywords -> Resolve Agent
        payment_keywords = [
            "payment",
            "failed",
            "stuck",
            "refund",
            "reversal",
            "upi",
            "utr",
            "paytm_",
            "dispute",
            "fraud",
            "suspicious",
            "250",
            "500",
            "320",
            "1200",
            "alok",
            "deepak",
            "pooja",
        ]
        is_payment_intent = any(k in query_clean for k in payment_keywords) or bool(
            re.search(r"PAYTM_[A-Z0-9_]+", query_text, re.IGNORECASE)
        )

        # 4. Dormancy / Revive / Retention Keywords -> Revive Agent
        revive_keywords = [
            "dormant",
            "revive",
            "retention",
            "booster",
            "slowdown",
            "decline",
            "drop in sales",
            "sales down",
            "volume drop",
            "checkin",
            "check-in",
            "kirana booster",
            "special offer",
        ]
        is_revive_intent = any(k in query_clean for k in revive_keywords)

        # 5. Onboarding / KYC Keywords -> Onboard Agent
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
            "storefront",
            "signup",
            "sign up",
            "application",
            "checklist",
            "blurry",
            "unreadable",
            "resubmit",
            "verify documents",
            "submit verification",
            "verification status",
            "missing document",
            "missing documents",
            "password",
            "otp",
            "pin",
            "upi pin",
        ]
        is_onboard_intent = any(k in query_clean for k in onboard_keywords)

        # Priority routing
        # Priority A: Onboard / KYC intent (includes credential security gate)
        if is_onboard_intent:
            onb_res = self.onboard_agent.run(
                merchant_id=merchant_id,
                query_text=query_text,
                actor_id=actor_id,
            )
            speech_res = self.speech_adapter.synthesize(onb_res["agent_reply"], language="hi-IN")
            return {
                "agent": "ONBOARD",
                "reply": onb_res["agent_reply"],
                "chip_status": onb_res["chip_status"],
                "branch": onb_res.get("action_taken"),
                "missing_item_card": onb_res.get("missing_item_card"),
                "action_card": onb_res.get("missing_item_card"),
                "breakdown_card": None,
                "approval_card": None,
                "checklist": onb_res.get("checklist"),
                "verification_result": onb_res.get("verification_result"),
                "speech_audio_base64": speech_res.audio_base64,
                "speech_duration_seconds": speech_res.duration_seconds,
            }

        # Priority B: Revive / Retention intent
        if is_revive_intent:
            rev_res = self.revive_agent.run(
                merchant_id=merchant_id,
                actor_id=actor_id,
            )
            speech_res = self.speech_adapter.synthesize(rev_res["agent_reply"], language="hi-IN")
            return {
                "agent": "REVIVE",
                "reply": rev_res["agent_reply"],
                "chip_status": rev_res["chip_status"],
                "branch": rev_res.get("branch"),
                "diagnosed_cause": rev_res.get("diagnosed_cause"),
                "checkin_card": rev_res.get("checkin_card"),
                "action_card": rev_res.get("checkin_card"),
                "breakdown_card": None,
                "approval_card": None,
                "followup_data": rev_res.get("followup_data"),
                "speech_audio_base64": speech_res.audio_base64,
                "speech_duration_seconds": speech_res.duration_seconds,
            }

        # Priority B: Settlement / Reconcile intent
        if is_settlement_intent:
            rec_res = self.reconcile_agent.run(
                merchant_id=merchant_id,
                query_text=query_text,
                actor_id=actor_id,
            )
            speech_res = self.speech_adapter.synthesize(rec_res["agent_reply"], language="hi-IN")
            return {
                "agent": "RECONCILE",
                "reply": rec_res["agent_reply"],
                "chip_status": rec_res["chip_status"],
                "branch": rec_res.get("branch"),
                "settlement_date": rec_res.get("settlement_date"),
                "breakdown_card": rec_res.get("breakdown_card"),
                "action_card": rec_res.get("breakdown_card"),
                "approval_card": None,
                "dispute_data": rec_res.get("dispute_data"),
                "speech_audio_base64": speech_res.audio_base64,
                "speech_duration_seconds": speech_res.duration_seconds,
            }

        # Priority B: Device / Soundbox intent
        if is_device_intent and not ("₹" in query_text or "utr" in query_clean or "refund" in query_clean):
            fix_res = self.fix_agent.run(
                merchant_id=merchant_id,
                query_text=query_text,
                city=city,
                actor_id=actor_id,
            )
            return {
                "agent": "FIX",
                "reply": fix_res["agent_reply"],
                "chip_status": fix_res["chip_status"],
                "step": fix_res.get("step"),
                "technician_booked": fix_res.get("technician_booked", False),
                "technician_slot": fix_res.get("technician_slot"),
                "case_id": fix_res.get("case_id"),
                "action_card": fix_res.get("action_card"),
                "breakdown_card": None,
                "approval_card": None,
                "speech_audio_base64": fix_res.get("speech_audio_base64"),
                "speech_duration_seconds": fix_res.get("speech_duration_seconds"),
            }

        # Priority C: Payment / Resolve intent
        if is_payment_intent:
            res_res = self.resolve_agent.run(
                merchant_id=merchant_id,
                query_text=query_text,
                actor_id=actor_id,
            )
            speech_res = self.speech_adapter.synthesize(res_res["agent_reply"], language="hi-IN")
            return {
                "agent": "RESOLVE",
                "reply": res_res["agent_reply"],
                "chip_status": res_res["chip_status"],
                "branch": res_res.get("branch"),
                "explanation_en": res_res.get("explanation_en"),
                "explanation_hi": res_res.get("explanation_hi"),
                "tx_ref": res_res.get("tx_ref"),
                "case_id": res_res.get("case_id"),
                "approval_card": res_res.get("approval_card"),
                "action_card": None,
                "breakdown_card": None,
                "speech_audio_base64": speech_res.audio_base64,
                "speech_duration_seconds": speech_res.duration_seconds,
            }

        # Check for device fallback if user mentions "fix" or "chime"
        if "fix" in query_clean or "chime" in query_clean:
            fix_res = self.fix_agent.run(
                merchant_id=merchant_id,
                query_text=query_text,
                city=city,
                actor_id=actor_id,
            )
            return {
                "agent": "FIX",
                "reply": fix_res["agent_reply"],
                "chip_status": fix_res["chip_status"],
                "step": fix_res.get("step"),
                "technician_booked": fix_res.get("technician_booked", False),
                "technician_slot": fix_res.get("technician_slot"),
                "case_id": fix_res.get("case_id"),
                "action_card": fix_res.get("action_card"),
                "breakdown_card": None,
                "approval_card": None,
                "speech_audio_base64": fix_res.get("speech_audio_base64"),
                "speech_duration_seconds": fix_res.get("speech_duration_seconds"),
            }

        # General Greeting
        greeting_reply = (
            "Namaste! I am Saathi, your Kirana AI teammate. "
            "I can explain your daily settlement breakdown (Reconcile), guide you through onboarding and KYC document verification (Onboard), "
            "investigate failed customer payments (Resolve), or diagnose and fix Soundbox issues including remote reboots and technician visits (Fix). "
            "How can I help you today?"
        )
        speech_res = self.speech_adapter.synthesize(greeting_reply, language="hi-IN")

        audit_log(
            db=self.db,
            actor=actor_id,
            action="SAATHI_ORCHESTRATOR_GREETING",
            target="saathi_brain",
            result="GREETING_RETURNED",
            policy_decision_id="dec_orch_greet",
        )

        return {
            "agent": "ORCHESTRATOR",
            "reply": greeting_reply,
            "chip_status": "verified",
            "branch": "GREETING",
            "breakdown_card": None,
            "action_card": None,
            "approval_card": None,
            "speech_audio_base64": speech_res.audio_base64,
            "speech_duration_seconds": speech_res.duration_seconds,
        }
