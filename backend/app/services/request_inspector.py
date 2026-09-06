"""
PLANE 3 (request side) — Advanced Normalization + Signature Engine + Zero-API Fusion.

Order matters. Normalization runs to a fixed point *before* any signature is
evaluated, so an attacker cannot hide a payload behind a layer the detector
never peeled: NFKC reduction, zero-width/format-character stripping, hidden
markup extraction, multi-pass Base64/Hex decoding (whole-string and embedded),
homoglyph folding, and dynamic leetspeak translation.
"""
from __future__ import annotations

import base64
import binascii
import math
import re
import time
import unicodedata
from collections import Counter
from typing import Any

from ..models import AttackPattern
from . import fusion
from .session_window import session_windows
from .signatures import RULES, SIGNATURE_COUNT, TECHNIQUE_SOURCES, evaluate as evaluate_signatures

HOMOGLYPHS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s", "һ": "h",
    "ν": "v", "ρ": "p", "τ": "t", "к": "k", "м": "m", "т": "t", "н": "h", "А": "A", "В": "B", "Е": "E", "К": "K",
    "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X"
})

HIDDEN_MARKUP = re.compile(r"<!--(.*?)-->|```[a-z]*\n?(.*?)```|\[\^\d+\]:\s*([^\n]+)", re.S | re.I)


def _tokens(s: str) -> Counter:
    return Counter(re.findall(r"[a-z0-9]+", s.lower()))


def lexical_similarity(a: str, b: str) -> float:
    """Vector-free cosine over token counts. No model download, no embedding service."""
    x, y = _tokens(a), _tokens(b)
    dot = sum(x[k] * y[k] for k in x)
    den = math.sqrt(sum(v * v for v in x.values()) * sum(v * v for v in y.values()))
    return dot / den if den else 0.0


def _printable(value: str) -> bool:
    return len(value) > 8 and sum(c.isprintable() or c.isspace() for c in value) / len(value) > 0.9


def normalize(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Reduce text to its semantic core and return the evidence for each layer peeled."""
    evidence = []
    norm = unicodedata.normalize("NFKC", text)
    norm = "".join(c for c in norm if unicodedata.category(c) != "Cf")
    if norm != text:
        evidence.append({"type": "unicode_normalization", "decoded": norm[:1000]})

    hidden = [m.group(1) or m.group(2) or m.group(3) for m in HIDDEN_MARKUP.finditer(norm) if any(m.groups())]
    if hidden:
        revealed = " ".join(h.strip() for h in hidden if h and h.strip())
        norm = f"{norm}\n{revealed}"
        evidence.append({"type": "hidden_markup", "decoded": revealed[:1000]})

    for _ in range(2):
        changed = False
        compact = re.sub(r"\s+", "", norm)
        for kind in ("base64", "hex"):
            try:
                dec = base64.b64decode(compact, validate=True).decode() if kind == "base64" else bytes.fromhex(compact.removeprefix("0x")).decode()
                if _printable(dec):
                    norm = dec; evidence.append({"type": kind, "decoded": dec[:1000]}); changed = True; break
            except (ValueError, UnicodeError, binascii.Error):
                pass
        if changed:
            continue
        for kind, rx in (("embedded_base64", r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/=])"), ("embedded_hex", r"\b(?:[0-9a-fA-F]{2}){12,}\b")):
            for token in re.findall(rx, norm):
                try:
                    dec = base64.b64decode(token, validate=True).decode() if kind.endswith("base64") else bytes.fromhex(token).decode()
                    if _printable(dec):
                        norm = norm.replace(token, dec); evidence.append({"type": kind, "decoded": dec[:1000]}); changed = True
                except (ValueError, UnicodeError, binascii.Error):
                    pass
        if not changed:
            break

    dehom = norm.translate(HOMOGLYPHS)
    if dehom != norm:
        evidence.append({"type": "homoglyph", "decoded": dehom[:1000]}); norm = dehom

    leet_hits = sum(norm.lower().count(c) for c in "431057")
    deleet = norm.lower().translate(str.maketrans("431057", "aeiost"))
    if leet_hits >= 3:
        evidence.append({"type": "leetspeak", "decoded": deleet[:1000]}); norm = deleet

    return norm, evidence


def _is_discussion(norm: str) -> bool:
    if re.search(r"^\s*(explain|discuss|describe|define|write (?:an?|the) (?:article|guide)|how (?:can|do|should) (?:i|we) (?:detect|prevent|protect)|what (?:is|are|does))\b", norm, re.I):
        return True
    return bool(re.search(r"^\s*how do i .*(?:in|for) (?:a |my )?(?:config|configuration|code|application|document|article)\b", norm, re.I))


_corpus_cache: list[dict] | None = None
_corpus_tokens: list[tuple[dict[str, Any], Counter, float, str]] | None = None


def invalidate_corpus_cache():
    global _corpus_cache, _corpus_tokens
    _corpus_cache = None
    _corpus_tokens = None


def _get_or_build_corpus_tokens(corpus: list[dict[str, Any]]):
    global _corpus_tokens, _corpus_cache
    if _corpus_tokens is not None and _corpus_cache is not None and corpus is _corpus_cache:
        return _corpus_tokens
    # Build token cache
    tokens_list = []
    for item in corpus:
        toks = _tokens(item["prompt"])
        norm_sq = math.sqrt(sum(v * v for v in toks.values()))
        pat = " ".join(item["prompt"].lower().split())
        tokens_list.append((item, toks, norm_sq, pat))
    if _corpus_cache is not None and corpus is _corpus_cache:
        _corpus_tokens = tokens_list
    return tokens_list


def top_corpus_match(norm: str, corpus: list[dict[str, Any]], exclude_ids: set[str] | None = None) -> tuple[dict[str, Any], int]:
    """Best lexical match, with the attack's own family excluded in batch mode."""
    best = {"id": None, "score": 0.0, "category": None}
    norm_lower = " ".join(norm.lower().split())
    norm_toks = _tokens(norm)
    norm_sq = math.sqrt(sum(v * v for v in norm_toks.values()))
    excluded = 0

    cached_entries = _get_or_build_corpus_tokens(corpus)

    for item, toks, y_sq, pat in cached_entries:
        if exclude_ids and str(item["id"]) in exclude_ids:
            excluded += 1
            continue
        if len(pat) > 20 and pat in norm_lower:
            score = 1.0
        elif norm_sq == 0.0 or y_sq == 0.0:
            score = 0.0
        else:
            dot = sum(norm_toks[k] * toks[k] for k in norm_toks if k in toks)
            den = norm_sq * y_sq
            score = dot / den if den else 0.0

        if score > best["score"]:
            best = {"id": item["id"], "score": round(score, 4), "category": item["category"]}
    return best, excluded


def inspect_request(
    text: str,
    corpus: list[dict[str, Any]],
    judge_score: float | None = None,
    exclude_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Deterministic request verdict. `judge_score` is accepted and ignored (zero-API)."""
    started = time.perf_counter()
    norm, decoded = normalize(text)
    matched = evaluate_signatures(norm)
    best, excluded = top_corpus_match(norm, corpus, exclude_ids)
    discussion = _is_discussion(norm)

    verdict = fusion.fuse_request(matched, best["score"], decoded, benign_discussion=discussion)
    category = matched[0]["category"] if matched else best["category"]

    return {
        "attack_detected": verdict["action"] != "ALLOW",
        "attack_type": category,
        "risk_score": verdict["risk_score"],
        "confidence": verdict["confidence"],
        "action": verdict["action"],
        "evidence": {
            "matched_rules": matched,
            "matched_techniques": [{"rule": x["name"], "source": x["technique_source"]} for x in matched if x["technique_source"]],
            "top_similarity": {**best, "excluded_family_patterns": excluded},
            "decoded_obfuscation": decoded,
            "benign_discussion_context": discussion,
            "fusion": verdict["components"],
            "gate_policy": verdict["gate_policy"],
            "signals": verdict["signals"],
            "engine": verdict["engine"],
            "signature_engine": {"signatures_evaluated": SIGNATURE_COUNT, "signatures_fired": len(matched)},
            "judge": {"used": False, "score": None, "note": "zero-api fusion: no external judge on the request path"},
            "timings": {"total_ms": round((time.perf_counter() - started) * 1000, 3)},
        },
    }


def get_corpus(db) -> list[dict]:
    global _corpus_cache, _corpus_tokens
    if _corpus_cache is not None:
        return _corpus_cache
    records = db.query(AttackPattern).filter(AttackPattern.origin.in_(["seed", "github"])).all()
    _corpus_cache = [{"id": a.id, "category": a.category, "prompt": a.cleaned_prompt} for a in records]
    _get_or_build_corpus_tokens(_corpus_cache)
    return _corpus_cache


def inspect_session(message: str, session_id: str, patterns: list[dict]):
    """PLANE 1 (memory): score the message alone and against the bounded session window."""
    single = inspect_request(message, patterns)
    window_text = session_windows.add_and_join(session_id, message)
    if window_text == message:
        return {**single, "session_window_used": False}
    combined = inspect_request(window_text, patterns)
    used = combined["risk_score"] > single["risk_score"]
    res = combined if used else single
    return {
        **res,
        "session_window_used": used,
        "evidence": {
            **res["evidence"],
            "single_message_risk": single["risk_score"],
            "session_window_risk": combined["risk_score"],
            "session_ttl_seconds": session_windows.ttl_seconds,
        },
    }
