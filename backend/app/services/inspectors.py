"""
Inspectors facade — re-exports the request, response, fusion, and analyzer
routines so callers and tests have one stable import surface.
"""
from .fusion import decide, fuse_request
from .request_inspector import (
    HIDDEN_MARKUP,
    HOMOGLYPHS,
    inspect_request,
    inspect_session,
    lexical_similarity,
    normalize,
    top_corpus_match,
)
from .response_inspector import LEAKS, SCANNERS, inspect_response, redact, scan
from .signatures import RULES, SIGNATURE_COUNT, TECHNIQUE_SOURCES, catalog as signature_catalog
from .analyzer import generate_finding_and_remediation, severity_from_score

__all__ = [
    "RULES",
    "SIGNATURE_COUNT",
    "TECHNIQUE_SOURCES",
    "signature_catalog",
    "HOMOGLYPHS",
    "HIDDEN_MARKUP",
    "lexical_similarity",
    "normalize",
    "top_corpus_match",
    "inspect_request",
    "inspect_session",
    "fuse_request",
    "decide",
    "LEAKS",
    "SCANNERS",
    "scan",
    "redact",
    "inspect_response",
    "severity_from_score",
    "generate_finding_and_remediation",
]
