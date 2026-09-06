"""
The Zero-API Fusion Engine.

No external AI judge sits on the request path. Every input to the score is
produced locally by a deterministic component, which buys three things a
model-in-the-loop gateway cannot offer:

  * 100% uptime          -- no provider outage can take the gateway down
  * privacy              -- the prompt under test never leaves the host
  * reproducibility      -- the same request always yields the same verdict,
                            which is what makes the audit chain worth signing

The heuristic model fuses three deterministic signals:

    R = min(100, sum of matching signature weights)
    S = 100          if top corpus similarity >= 0.85, else the similarity itself
    D = 100          if normalization produced decoding evidence, else 0

    Base Risk = (0.50 x R) + (0.35 x S) + (0.15 x D)

Gateway actions:
    BLOCK   risk >= 70, confidence >= 0.6, and at least two independent signals
    REVIEW  30 <= risk <= 69   (quarantined for operator intervention)
    ALLOW   risk < 30

The two-signal rule is what stops any single layer from blocking on its own: a
lone regex hit, however heavy, can only ever reach REVIEW.
"""
from __future__ import annotations

from typing import Any

SIMILARITY_THRESHOLD = 0.85
WEIGHTS = {"rules": 0.50, "similarity": 0.35, "decoding": 0.15}
BLOCK_THRESHOLD = 70.0
REVIEW_THRESHOLD = 30.0
MIN_BLOCK_CONFIDENCE = 0.6
MIN_BLOCK_SIGNALS = 2

# A request that reads as a question *about* injection rather than an attempt at
# one is damped rather than exempted -- decoding evidence cancels the discount,
# because nobody base64-encodes a question they are genuinely asking.
DISCUSSION_DAMPING = 0.45


def rule_component(matched: list[dict[str, Any]]) -> float:
    """R — saturating sum of matching signature weights."""
    return float(min(100, sum(hit["weight"] for hit in matched)))


def similarity_component(top_similarity: float) -> float:
    """S — a near-exact corpus match saturates; anything below is taken at face value."""
    if top_similarity >= SIMILARITY_THRESHOLD:
        return 100.0
    return float(max(0.0, min(1.0, top_similarity)) * 100.0)


def decoding_component(decoded_evidence: list[Any]) -> float:
    """D — binary. Layered obfuscation is evidence of intent, not of degree."""
    return 100.0 if decoded_evidence else 0.0


def base_risk(rules: float, similarity: float, decoding: float) -> float:
    return (WEIGHTS["rules"] * rules
            + WEIGHTS["similarity"] * similarity
            + WEIGHTS["decoding"] * decoding)


def count_signals(matched: list[dict[str, Any]], top_similarity: float, decoded_evidence: list[Any]) -> int:
    """Independent corroborating signals — the anti-single-layer-block guard."""
    return sum([
        bool(matched),
        top_similarity >= SIMILARITY_THRESHOLD,
        bool(decoded_evidence),
    ])


def confidence_for(signals: int) -> float:
    return round(min(0.98, 0.35 + 0.18 * signals), 2)


def decide(risk: float, confidence: float, signals: int) -> str:
    if risk >= BLOCK_THRESHOLD and confidence >= MIN_BLOCK_CONFIDENCE and signals >= MIN_BLOCK_SIGNALS:
        return "BLOCK"
    if risk >= REVIEW_THRESHOLD:
        return "REVIEW"
    return "ALLOW"


def fuse_request(
    matched: list[dict[str, Any]],
    top_similarity: float,
    decoded_evidence: list[Any],
    benign_discussion: bool = False,
) -> dict[str, Any]:
    """Fuse the three deterministic components into a gateway decision."""
    rules = rule_component(matched)
    similarity = similarity_component(top_similarity)
    decoding = decoding_component(decoded_evidence)

    raw = base_risk(rules, similarity, decoding)
    damped = raw * DISCUSSION_DAMPING if (benign_discussion and not decoded_evidence) else raw
    risk = round(min(100.0, damped), 2)

    signals = count_signals(matched, top_similarity, decoded_evidence)
    confidence = confidence_for(signals)
    action = decide(risk, confidence, signals)

    return {
        "risk_score": risk,
        "confidence": confidence,
        "action": action,
        "signals": signals,
        "components": {
            "R_rules": round(rules, 2),
            "S_similarity": round(similarity, 2),
            "D_decoding": round(decoding, 2),
            "weights": dict(WEIGHTS),
            "base_risk": round(raw, 2),
            "discussion_damping_applied": risk != round(min(100.0, raw), 2),
            "formula": "(0.50 x R) + (0.35 x S) + (0.15 x D)",
        },
        "gate_policy": {
            "block": f"risk >= {BLOCK_THRESHOLD:.0f} and confidence >= {MIN_BLOCK_CONFIDENCE} and signals >= {MIN_BLOCK_SIGNALS}",
            "review": f"{REVIEW_THRESHOLD:.0f} <= risk <= {BLOCK_THRESHOLD - 1:.0f}",
            "allow": f"risk < {REVIEW_THRESHOLD:.0f}",
        },
        "engine": "zero-api-deterministic",
    }
