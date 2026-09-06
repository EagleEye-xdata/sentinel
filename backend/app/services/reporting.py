from collections import Counter, defaultdict
from sqlalchemy.orm import Session
from ..models import AttackPattern, Report, Target, TestExecution, TestRun
from . import fusion
from .micro_model import backend_status
from .mutator import MUTATION_ORDER
from .response_inspector import SCANNERS
from .signatures import SIGNATURE_COUNT

OWASP_MAPPINGS = {
    "instruction_override": "LLM01: Prompt Injection",
    "role_manipulation": "LLM01: Prompt Injection (Role Manipulation)",
    "system_prompt_extraction": "LLM06: Sensitive Information Disclosure",
    "delimiter_manipulation": "LLM01: Prompt Injection (Delimiter Smuggling)",
    "instruction_hierarchy": "LLM01: Prompt Injection (Priority Overrides)",
    "indirect_injection": "LLM01: Indirect Prompt Injection",
    "payload_splitting": "LLM01: Prompt Injection (Multi-turn Payload Splitting)",
    "context_manipulation": "LLM01: Prompt Injection (Context Manipulation)",
    "jailbreak": "LLM01: Prompt Injection (Jailbreak Persona)",
    "obfuscation": "LLM01: Prompt Injection (Defense Evasion)",
    "secret": "LLM06: Sensitive Information Disclosure",
    "pii": "LLM02: Sensitive Data Exposure",
    "system_prompt": "LLM06: Sensitive Information Disclosure",
}

def get_owasp_tag(category: str) -> str:
    return OWASP_MAPPINGS.get(category.lower(), "LLM01: Prompt Injection")

def build_report(db: Session, run_id: int) -> dict:
    run = db.get(TestRun, run_id)
    target = db.get(Target, run.target_id)
    rows = db.query(TestExecution).filter_by(test_run_id=run_id).all()
    categories = defaultdict(lambda: {"executed": 0, "successful": 0, "resisted": 0, "inconclusive": 0})
    owasp_breakdown = defaultdict(lambda: {"executed": 0, "successful": 0, "resisted": 0})
    severities = Counter()
    findings = []
    
    attack_ids = {e.attack_pattern_id for e in rows if e.attack_pattern_id}
    attacks_map = {a.id: a for a in db.query(AttackPattern).filter(AttackPattern.id.in_(attack_ids)).all()} if attack_ids else {}

    for e in rows:
        a = attacks_map.get(e.attack_pattern_id)
        cat = a.category if a else (e.request_evidence.get("attack_category") or e.request_evidence.get("attack_type") or "live")
        owasp = get_owasp_tag(cat)
        
        categories[cat]["executed"] += 1
        categories[cat][e.outcome.lower()] = categories[cat].get(e.outcome.lower(), 0) + 1
        
        owasp_breakdown[owasp]["executed"] += 1
        owasp_breakdown[owasp][e.outcome.lower()] = owasp_breakdown[owasp].get(e.outcome.lower(), 0) + 1
        
        severities[e.derived_severity.lower()] += 1
        findings.append({
            "execution_id": e.id,
            "attack_id": e.attack_pattern_id,
            "category": cat,
            "owasp_tag": owasp,
            "title": a.title if a else (f"Single Test ({cat})" if cat != "live" else "Single Prompt Injection Test"),
            "mutation": (a.mutation if a else None) or e.request_evidence.get("mutation"),
            "payload_used": e.request_text,
            "request_verdict": e.request_action,
            "request_evidence": e.request_evidence,
            "reached_target": e.reached_target,
            "outcome": e.outcome,
            "response_excerpt": (e.response_text or "")[:800],
            "leakage_type": e.response_evidence.get("leakage_type"),
            "response_evidence": e.response_evidence,
            "source_severity": e.source_severity,
            "derived_severity": e.derived_severity,
            "confidence": e.confidence,
            "remediation": (a.remediation if a else None) or e.request_evidence.get("remediation") or "Harden instruction boundaries and validate model output."
        })
    findings.sort(key=lambda x: (x["outcome"] != "SUCCESSFUL", -x["confidence"]))
    risk = round(sum(max(e.request_risk_score, e.response_risk_score) for e in rows) / len(rows), 2) if rows else 0
    return {
        "run_id": run.id,
        "target_name": target.name,
        "run_mode": run.mode,
        "status": run.status,
        "totals": {
            "executed": run.executed,
            "resisted": run.resisted,
            "successful": run.successful,
            "inconclusive": run.inconclusive,
            "skipped_incompatible": run.skipped,
            "errors": run.errors
        },
        "risk_score_overall": risk,
        "severity_breakdown": dict(severities),
        "by_category": [{"category": k, **v} for k, v in categories.items()],
        "by_owasp": [{"owasp": k, **v} for k, v in owasp_breakdown.items()],
        "findings": findings,
        "architecture": {
            "name": "Unified AI Security Architecture v2",
            "planes": ["Corpus & Memory", "Baseline / Proxy", "Detection Engine", "Cryptographic Audit"],
            "detection_engine": "zero-api-deterministic",
            "fusion_formula": "(0.50 x R) + (0.35 x S) + (0.15 x D)",
            "fusion_weights": dict(fusion.WEIGHTS),
            "signatures": SIGNATURE_COUNT,
            "transformations": len(MUTATION_ORDER),
            "dlp_scanners": SCANNERS,
            "target_backend": backend_status() if str(target.api_endpoint).startswith("internal://") else
                              {"backend": "remote_http", "air_gapped": False, "endpoint": target.api_endpoint},
        },
        "limitations": [
            "Content the target fetches itself (server-side RAG or browsing) is outside proxy scope unless it surfaces in the response body.",
            "Internal tool calls that never appear in the response cannot be observed by a response-side gate.",
            "Payloads split across more turns than the session window retains are not reassembled.",
            "Runs against the deterministic sandbox oracle demonstrate pipeline correctness, not detection generality against production models.",
        ],
    }

def markdown_report(report: dict) -> str:
    t = report["totals"]
    out = [
        f"# Prompt Injection Security Assessment Report — {report['target_name']}",
        "",
        f"**Overall Risk Score:** `{report['risk_score_overall']}/100`",
        f"**Assessment Status:** `{report['status'].upper()}`",
        "",
        "## Executive Summary",
        f"- **Total Executed:** {t['executed']}",
        f"- **Resisted (Secured):** {t['resisted']} ({round(t['resisted']/max(1, t['executed'])*100, 1)}%)",
        f"- **Successful Breaches:** {t['successful']} ({round(t['successful']/max(1, t['executed'])*100, 1)}%)",
        f"- **Inconclusive / Neutralized:** {t['inconclusive']}",
        f"- **Errors / Skipped:** {t['errors'] + t['skipped_incompatible']}",
        "",
        "## OWASP Top 10 for LLM Breakdown",
        ""
    ]
    for o in report.get("by_owasp", []):
        out.append(f"- **{o['owasp']}:** {o['executed']} tested ({o['successful']} breached, {o['resisted']} resisted)")
    out += ["", "## Detailed Security Findings", ""]
    for f in report["findings"]:
        out += [
            f"### [{f['outcome']}] {f['title']}",
            "",
            f"- **OWASP Classification:** `{f.get('owasp_tag', 'LLM01')}`",
            f"- **Category:** `{f['category']}` · **Severity:** `{f['derived_severity']}` · **Confidence:** `{f['confidence']}`",
            f"- **Request Verdict:** `{f['request_verdict']}` · **Reached Target:** `{f['reached_target']}`",
            f"- **Payload Attempted:**",
            f"```text",
            f"{f['payload_used']}",
            f"```",
            f"- **Target Response Excerpt:**",
            f"```text",
            f"{f['response_excerpt']}",
            f"```",
            f"- **Actionable Remediation:** {f['remediation']}",
            ""
        ]
    return "\n".join(out)

