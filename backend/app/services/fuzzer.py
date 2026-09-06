"""
Automated Differential Fuzzing.

The corpus applies 13 deterministic payload transformations plus a family of
boundary probes to every seed, then scores each variant through the same gateway
the seed went through. A variant whose verdict is *weaker* than the seed's is a
bypass, and a bypass is a detector bug the report should name.

No live LLM is needed to generate the attacks. Split and staged payloads are
produced structurally -- a three-turn split is a deterministic partition of the
seed, not a model's paraphrase -- which is what keeps the fuzzer reproducible
and runnable offline.

Two probe families beyond the transformations:

  valid-suffix truncation  Drop leading words while the *suffix* remains a
                           working instruction. This defeats detectors anchored
                           on an opening phrase, and it defeats exact-substring
                           corpus matching while the semantic payload survives.

  boundary probes          Pad and prefix the payload with benign text to walk
                           the score across the ALLOW/REVIEW/BLOCK bands and
                           find the exact point where the gate flips.
"""
from __future__ import annotations

from typing import Any

from .mutator import MUTATION_ORDER, mutate
from .request_inspector import inspect_request

ACTION_RANK = {"ALLOW": 0, "REVIEW": 1, "BLOCK": 2}

# A variant that loses this much risk without changing band has not bypassed the
# gate, but it has eroded the margin -- worth naming in the report before the
# next corpus change turns the erosion into an actual bypass.
EROSION_THRESHOLD = -10.0

BENIGN_PADDING = (
    "Thanks for your help so far. Here is some background about our campus service desk "
    "and the ticket I opened last week regarding library access hours. "
)


def _flatten(payload: str | list[str]) -> str:
    return "\n".join(payload) if isinstance(payload, list) else payload


def suffix_truncations(prompt: str, steps: int = 3) -> list[tuple[str, str]]:
    """Progressively drop leading words, keeping a still-valid instruction suffix."""
    words = prompt.split()
    out: list[tuple[str, str]] = []
    if len(words) < 6:
        return out
    for step in range(1, steps + 1):
        cut = int(len(words) * step / (steps + 1))
        if cut == 0 or cut >= len(words) - 2:
            continue
        out.append((f"valid_suffix_truncation_{step}", " ".join(words[cut:])))
    return out


def boundary_probes(prompt: str) -> list[tuple[str, str]]:
    """Dilute the payload with benign context to walk it across the gate bands."""
    return [
        ("boundary_benign_prefix", BENIGN_PADDING + prompt),
        ("boundary_benign_sandwich", BENIGN_PADDING + prompt + " " + BENIGN_PADDING),
        ("boundary_question_frame", f"Quick question about our documentation: {prompt}"),
    ]


def _score(text: str, corpus: list[dict[str, Any]], exclude_ids: set[str] | None) -> dict[str, Any]:
    verdict = inspect_request(text, corpus, exclude_ids=exclude_ids)
    return {
        "risk_score": verdict["risk_score"],
        "action": verdict["action"],
        "confidence": verdict["confidence"],
        "signals": verdict["evidence"]["signals"],
        "signatures_fired": [r["name"] for r in verdict["evidence"]["matched_rules"]],
        "decoding_layers": [d["type"] for d in verdict["evidence"]["decoded_obfuscation"]],
        "top_similarity": verdict["evidence"]["top_similarity"]["score"],
    }


def differential_fuzz(
    prompt: str,
    corpus: list[dict[str, Any]],
    transformations: list[str] | None = None,
    exclude_ids: set[str] | None = None,
    include_boundary_probes: bool = True,
) -> dict[str, Any]:
    """Fuzz one seed and report every variant that scores weaker than the seed."""
    transformations = transformations or list(MUTATION_ORDER)
    baseline = _score(prompt, corpus, exclude_ids)

    candidates: list[tuple[str, str, str]] = []  # (family, name, payload)
    for name in transformations:
        try:
            candidates.append(("transformation", name, _flatten(mutate(prompt, name))))
        except ValueError:
            continue
    for name, payload in suffix_truncations(prompt):
        candidates.append(("truncation", name, payload))
    if include_boundary_probes:
        for name, payload in boundary_probes(prompt):
            candidates.append(("boundary", name, payload))

    variants = []
    for family, name, payload in candidates:
        result = _score(payload, corpus, exclude_ids)
        weaker = ACTION_RANK[result["action"]] < ACTION_RANK[baseline["action"]]
        delta = result["risk_score"] - baseline["risk_score"]
        variants.append({
            "weakened": delta <= EROSION_THRESHOLD,
            "family": family,
            "transformation": name,
            "payload": payload if len(payload) <= 600 else payload[:600] + "…",
            "payload_chars": len(payload),
            **result,
            "risk_delta": round(result["risk_score"] - baseline["risk_score"], 2),
            "bypass": weaker,
            "evaded_to": result["action"] if weaker else None,
        })

    bypasses = [v for v in variants if v["bypass"]]
    weakened = [v for v in variants if v["weakened"] and not v["bypass"]]
    weakest = min(variants, key=lambda v: v["risk_score"]) if variants else None

    return {
        "baseline": {"payload": prompt, **baseline},
        "variants": sorted(variants, key=lambda v: v["risk_score"]),
        "summary": {
            "transformations_applied": sum(1 for v in variants if v["family"] == "transformation"),
            "truncation_probes": sum(1 for v in variants if v["family"] == "truncation"),
            "boundary_probes": sum(1 for v in variants if v["family"] == "boundary"),
            "total_variants": len(variants),
            "bypasses": len(bypasses),
            "bypass_rate": round(len(bypasses) / len(variants), 3) if variants else 0.0,
            "detector_robustness": round(1 - (len(bypasses) / len(variants)), 3) if variants else 1.0,
            "weakened_without_bypass": len(weakened),
            "max_risk_erosion": round(min((v["risk_delta"] for v in variants), default=0.0), 2),
            "weakest_variant": {"transformation": weakest["transformation"], "risk_score": weakest["risk_score"], "action": weakest["action"]} if weakest else None,
            "bypassing_transformations": [v["transformation"] for v in bypasses],
            "eroding_transformations": [v["transformation"] for v in weakened],
            "generation": "deterministic — no live LLM used to build variants",
        },
    }


def fuzz_corpus(
    seeds: list[dict[str, Any]],
    corpus: list[dict[str, Any]],
    transformations: list[str] | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Fuzz a slice of the corpus and aggregate which transformation evades most."""
    reports = []
    evasion: dict[str, int] = {}
    for seed in seeds[:limit]:
        family = {str(seed["id"])}
        report = differential_fuzz(seed["prompt"], corpus, transformations, exclude_ids=family)
        for name in report["summary"]["bypassing_transformations"]:
            evasion[name] = evasion.get(name, 0) + 1
        reports.append({
            "attack_id": seed["id"],
            "category": seed.get("category"),
            "baseline_action": report["baseline"]["action"],
            "baseline_risk": report["baseline"]["risk_score"],
            **report["summary"],
        })

    total_variants = sum(r["total_variants"] for r in reports)
    total_bypasses = sum(r["bypasses"] for r in reports)
    return {
        "seeds_fuzzed": len(reports),
        "total_variants": total_variants,
        "total_bypasses": total_bypasses,
        "overall_bypass_rate": round(total_bypasses / total_variants, 4) if total_variants else 0.0,
        "detector_robustness": round(1 - (total_bypasses / total_variants), 4) if total_variants else 1.0,
        "most_evasive_transformations": sorted(evasion.items(), key=lambda kv: -kv[1])[:5],
        "per_seed": reports,
    }
