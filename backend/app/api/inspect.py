from datetime import datetime
from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import AttackPattern, Target, TestExecution, TestRun
from ..schemas import InspectRequest, InspectResponse
from ..services.request_inspector import get_corpus, inspect_session
from ..services.response_inspector import inspect_response
from ..services.analyzer import generate_finding_and_remediation
from ..services.judge import judge
from ..services.adapter import call_target
from ..services.audit import audit_chain, record
from ..services.reporting import build_report

router = APIRouter(tags=["inspect"])


class PipelineRequest(BaseModel):
    target_id: int
    prompt_text: str
    session_id: str = "default-session"
    attack_category: str | None = None
    mutation: str | None = None
    expected_safe_behaviour: str | None = None
    success_indicators: list[str] = []
    failure_indicators: list[str] = []
    enforce_block: bool = False


@router.post("/inspect/request")
def inspect_req(body: InspectRequest, db: Session = Depends(get_db)):
    return inspect_session(body.prompt_text, body.session_id, get_corpus(db))


@router.post("/inspect/response")
async def inspect_resp(body: InspectResponse):
    j = await judge(body.original_attack, body.response_text, body.objective, body.expected_safe_behaviour, body.declared_policy)
    return inspect_response(body.response_text, body.success_indicators, body.failure_indicators, body.canary, j)


@router.post("/inspect/pipeline")
async def inspect_pipeline(body: PipelineRequest, db: Session = Depends(get_db)):
    target = db.get(Target, body.target_id)
    if not target:
        raise HTTPException(404, "Target not found")

    req_verdict = inspect_session(body.prompt_text, body.session_id, get_corpus(db))
    reached_target = not (body.enforce_block and req_verdict["action"] == "BLOCK")
    raw_response, resp_verdict, target_error = None, None, None

    if reached_target:
        try:
            raw_response = await call_target(target, body.prompt_text, body.session_id)
            if raw_response and raw_response.startswith("[Target ") and ("Error" in raw_response or "Failed" in raw_response):
                target_error = raw_response
                raw_response = None
            else:
                j_eval = await judge(body.prompt_text, raw_response, body.attack_category or "prompt injection test", body.expected_safe_behaviour or target.declared_policy, target.declared_policy)
                resp_verdict = inspect_response(raw_response, body.success_indicators, body.failure_indicators, target.system_prompt_canary, j_eval)
        except Exception as exc:
            target_error = str(exc)

    analyzer = generate_finding_and_remediation(req_verdict, resp_verdict, reached_target=reached_target)

    # Determine execution outcome
    if not reached_target:
        outcome = "RESISTED"
    elif resp_verdict and resp_verdict.get("leakage_detected"):
        outcome = "SUCCESSFUL"
    elif resp_verdict and resp_verdict.get("outcome") == "RESISTED":
        outcome = "RESISTED"
    elif analyzer.get("verdict") == "VULNERABLE":
        outcome = "SUCCESSFUL"
    elif analyzer.get("verdict") in ("RESISTED", "BLOCKED"):
        outcome = "RESISTED"
    elif target_error:
        outcome = "ERROR"
    else:
        outcome = "INCONCLUSIVE"

    now = datetime.utcnow()
    test_run = TestRun(
        target_id=target.id,
        mode="single",
        status="completed",
        config={
            "attack_category": body.attack_category or req_verdict.get("attack_type"),
            "mutation": body.mutation,
            "session_id": body.session_id,
            "enforce_block": body.enforce_block,
        },
        total=1,
        executed=1,
        resisted=1 if outcome == "RESISTED" else 0,
        successful=1 if outcome == "SUCCESSFUL" else 0,
        inconclusive=1 if outcome == "INCONCLUSIVE" else 0,
        skipped=0,
        errors=1 if outcome == "ERROR" else 0,
        started_at=now,
        finished_at=now,
    )
    db.add(test_run)
    db.flush()

    matched_pattern = db.query(AttackPattern).filter(AttackPattern.raw_prompt == body.prompt_text).first()
    pattern_id = matched_pattern.id if matched_pattern else None

    req_evidence = dict(req_verdict.get("evidence") or {})
    req_evidence["attack_category"] = body.attack_category or req_verdict.get("attack_type") or "custom_injection"
    req_evidence["mutation"] = body.mutation
    req_evidence["remediation"] = analyzer.get("remediation")
    req_evidence["remediation_details"] = analyzer.get("remediation_details")
    req_evidence["finding"] = analyzer.get("finding")

    execution = TestExecution(
        test_run_id=test_run.id,
        attack_pattern_id=pattern_id,
        session_id=body.session_id,
        sequence_number=1,
        request_text=body.prompt_text,
        request_risk_score=float(req_verdict.get("risk_score", 0)),
        request_action=req_verdict.get("action", "ALLOW"),
        request_evidence=req_evidence,
        reached_target=reached_target,
        response_text=raw_response or target_error,
        response_risk_score=float((resp_verdict or {}).get("risk_score", 0)),
        response_action=(resp_verdict or {}).get("action", "ALLOW") if reached_target else "BLOCK",
        response_evidence=(resp_verdict or {}).get("evidence") or {},
        outcome=outcome,
        source_severity=analyzer.get("severity", "LOW"),
        derived_severity=analyzer.get("severity", "LOW"),
        confidence=float(req_verdict.get("confidence", 0.9)),
        latency_ms=float(req_verdict.get("evidence", {}).get("timings", {}).get("total_ms", 35.0)),
        created_at=now,
    )
    db.add(execution)

    audit = record(db, "pipeline.decision", {
        "run_id": test_run.id,
        "target_id": target.id,
        "session_id": body.session_id,
        "prompt_sha": sha256(body.prompt_text.encode()).hexdigest(),
        "request_action": req_verdict["action"],
        "request_risk": req_verdict["risk_score"],
        "reached_target": reached_target,
        "response_action": (resp_verdict or {}).get("action"),
        "response_risk": (resp_verdict or {}).get("risk_score"),
        "verdict": analyzer["verdict"],
    })
    db.commit()

    report_data = build_report(db, test_run.id)
    report_data["audit"] = audit_chain.verify(db, test_run.id)

    return {
        "test_run_id": test_run.id,
        "report": report_data,
        "prompt": body.prompt_text,
        "mutation": body.mutation,
        "attack_category": body.attack_category or req_verdict.get("attack_type"),
        "target": {"id": target.id, "name": target.name, "model_name": target.model_name},
        "request_verdict": req_verdict,
        "reached_target": reached_target,
        "target_response": raw_response,
        "target_error": target_error,
        "response_verdict": resp_verdict,
        "analyzer": analyzer,
        "audit": audit,
    }
