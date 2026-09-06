"""Unified-architecture endpoints: plane status, signature catalog, differential fuzzing."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AttackPattern, AuditEvent
from ..services import fusion
from ..services.audit import audit_chain
from ..services.fuzzer import differential_fuzz, fuzz_corpus
from ..services.micro_model import backend_status, catalog as sandbox_catalog
from ..services.mutator import MUTATION_ORDER
from ..services.request_inspector import get_corpus
from ..services.response_inspector import SCANNERS
from ..services.session_window import session_windows
from ..services.signatures import SIGNATURE_COUNT, catalog as signature_catalog

router = APIRouter(tags=["architecture"])


class FuzzRequest(BaseModel):
    prompt_text: str | None = None
    attack_pattern_id: str | None = None
    transformations: list[str] = Field(default_factory=list)
    include_boundary_probes: bool = True


class CorpusFuzzRequest(BaseModel):
    categories: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=200)
    transformations: list[str] = Field(default_factory=list)


@router.get("/architecture/planes")
def planes(db: Session = Depends(get_db)):
    """Live status of the four functional planes."""
    categories = [row[0] for row in db.query(AttackPattern.category).distinct().all()]
    return {
        "planes": [
            {
                "plane": "Corpus & Memory",
                "responsibility": "Mutates base seeds across categories; maintains bounded session history.",
                "result": "Validated injection patterns & bounded input windows.",
                "status": {
                    "attack_patterns": db.query(AttackPattern).count(),
                    "categories": len(categories),
                    "category_names": sorted(categories),
                    "transformations": len(MUTATION_ORDER),
                    "session_ttl_seconds": session_windows.ttl_seconds,
                    "session_window_messages": session_windows.max_messages,
                },
            },
            {
                "plane": "Baseline / Proxy",
                "responsibility": "Live traffic routing (ALLOW/BLOCK/REVIEW) or batch mode dispatch.",
                "result": "Versioned target behavior telemetry.",
                "status": {
                    "gate_actions": ["ALLOW", "REVIEW", "BLOCK"],
                    "modes": ["live_proxy", "batch"],
                    "sandbox": backend_status(),
                    "sandbox_models": sandbox_catalog(),
                },
            },
            {
                "plane": "Detection Engine",
                "responsibility": "Multi-pass decoding, rule execution, and vector-free lexical similarity.",
                "result": "Deterministic request decision & response verdict.",
                "status": {
                    "signatures": SIGNATURE_COUNT,
                    "normalization": ["unicode_nfkc", "format_char_strip", "hidden_markup",
                                      "multipass_base64", "multipass_hex", "homoglyph", "leetspeak"],
                    "similarity": "vector-free lexical cosine",
                    "similarity_threshold": fusion.SIMILARITY_THRESHOLD,
                    "fusion": {"weights": fusion.WEIGHTS, "formula": "(0.50 x R) + (0.35 x S) + (0.15 x D)",
                               "engine": "zero-api-deterministic"},
                    "dlp_scanners": SCANNERS,
                },
            },
            {
                "plane": "Cryptographic Audit",
                "responsibility": "HMAC-SHA256 authenticated chains and atomic key publication.",
                "result": "Tamper-proof, verifiable security reports.",
                "status": {
                    "algorithm": "HMAC-SHA256",
                    "events": db.query(AuditEvent).count(),
                    "open_segment": audit_chain.key_id,
                    "published_segments": sorted(audit_chain.published_keys()),
                },
            },
        ]
    }


@router.get("/signatures")
def signatures():
    """The deterministic runtime signature catalog used by the detection engine."""
    return {"count": SIGNATURE_COUNT, "signatures": signature_catalog()}


@router.get("/fusion/model")
def fusion_model():
    return {
        "engine": "zero-api-deterministic",
        "formula": "Base Risk = (0.50 x R) + (0.35 x S) + (0.15 x D)",
        "components": {
            "R": "min(100, sum of matching signature weights)",
            "S": f"100 if top corpus similarity >= {fusion.SIMILARITY_THRESHOLD} else the similarity itself",
            "D": "100 if normalization produced decoding evidence else 0",
        },
        "weights": fusion.WEIGHTS,
        "gateway_actions": {
            "BLOCK": f"risk >= {fusion.BLOCK_THRESHOLD:.0f}, confidence >= {fusion.MIN_BLOCK_CONFIDENCE}, and >= {fusion.MIN_BLOCK_SIGNALS} signal triggers",
            "REVIEW": f"{fusion.REVIEW_THRESHOLD:.0f} <= risk <= {fusion.BLOCK_THRESHOLD - 1:.0f} (quarantined for operator intervention)",
            "ALLOW": f"risk < {fusion.REVIEW_THRESHOLD:.0f}",
        },
        "rationale": "No external AI judge on the request path: 100% uptime, no prompt leaves the host, reproducible verdicts.",
    }


@router.post("/fuzz/differential")
def fuzz_one(body: FuzzRequest, db: Session = Depends(get_db)):
    """Fuzz a single payload through 13 transformations plus truncation and boundary probes."""
    prompt = body.prompt_text
    exclude: set[str] | None = None
    if body.attack_pattern_id:
        pattern = db.get(AttackPattern, body.attack_pattern_id)
        if pattern:
            prompt = prompt or pattern.raw_prompt
            root = pattern.parent_pattern_id or pattern.id
            exclude = {
                str(r.id) for r in db.query(AttackPattern)
                .filter((AttackPattern.id == root) | (AttackPattern.parent_pattern_id == root)).all()
            }
    if not prompt:
        return {"error": "provide prompt_text or a valid attack_pattern_id"}

    return differential_fuzz(
        prompt,
        get_corpus(db),
        body.transformations or None,
        exclude_ids=exclude,
        include_boundary_probes=body.include_boundary_probes,
    )


@router.post("/fuzz/corpus")
def fuzz_many(body: CorpusFuzzRequest, db: Session = Depends(get_db)):
    """Fuzz a slice of the corpus and rank which transformation evades detection most."""
    query = db.query(AttackPattern).filter_by(origin="seed")
    if body.categories:
        query = query.filter(AttackPattern.category.in_(body.categories))
    seeds = [
        {"id": a.id, "category": a.category, "prompt": a.raw_prompt}
        for a in query.limit(body.limit).all()
    ]
    return fuzz_corpus(seeds, get_corpus(db), body.transformations or None, limit=body.limit)
