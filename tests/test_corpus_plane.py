"""PLANE 1 — the corpus and its bounded session memory."""
from pathlib import Path

import yaml

from backend.app.services.micro_model import generate
from backend.app.services.request_inspector import inspect_request
from backend.app.services.response_inspector import inspect_response
from backend.app.services.session_window import session_windows

ROOT = Path(__file__).resolve().parents[1]
CANARY = "GENESIS-7731-INTERNAL"
NEW_CATEGORIES = {"tool_definition_poisoning", "refusal_suppression", "exfiltration_channel"}


def seed_files():
    return sorted((ROOT / "corpus" / "seed").glob("*.yaml"))


def all_seeds():
    seeds = []
    for path in seed_files():
        seeds.extend(yaml.safe_load(path.read_text(encoding="utf-8"))["attacks"])
    return seeds


def test_corpus_covers_seventeen_categories():
    categories = {seed["category"] for seed in all_seeds()}
    assert len(categories) == 17, sorted(categories)
    assert NEW_CATEGORIES <= categories


def test_every_seed_is_well_formed_and_uniquely_identified():
    seeds = all_seeds()
    ids = [seed["id"] for seed in seeds]
    assert len(ids) == len(set(ids))
    for seed in seeds:
        assert seed["prompt"].strip()
        assert seed["success_indicators"] and seed["failure_indicators"]
        assert seed["source_severity"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        assert seed["remediation"].strip()


def test_new_seeds_declare_honest_provenance():
    """No repository or commit is cited that we cannot stand behind."""
    for seed in all_seeds():
        if seed["category"] not in NEW_CATEGORIES:
            continue
        provenance = seed.get("provenance", {})
        assert "hand_authored" in provenance.get("source", "")
        assert provenance.get("taxonomy_source")


def test_every_new_seed_actually_works_against_the_vulnerable_sandbox():
    """Only attacks that really land are allowed to sit in the corpus."""
    for seed in all_seeds():
        if seed["category"] not in NEW_CATEGORIES:
            continue
        response = generate("internal://tinyllama", seed["prompt"], CANARY)["text"]
        verdict = inspect_response(response, seed["success_indicators"], seed["failure_indicators"], CANARY)
        assert verdict["outcome"] == "SUCCESSFUL", f"{seed['id']} does not land on the vulnerable target"


def test_every_new_seed_is_resisted_by_the_hardened_sandbox():
    for seed in all_seeds():
        if seed["category"] not in NEW_CATEGORIES:
            continue
        response = generate("internal://tinyllama-hardened", seed["prompt"], CANARY)["text"]
        assert CANARY not in response, f"{seed['id']} leaked from the hardened target"


def test_exfiltration_seeds_are_the_defence_in_depth_case():
    """Several exfiltration payloads pass the request gate by design and are
    caught only by the response DLP gate. That asymmetry is declared, not hidden."""
    allowed_at_request = 0
    for seed in all_seeds():
        if seed["category"] != "exfiltration_channel":
            continue
        if inspect_request(seed["prompt"], [])["action"] == "ALLOW":
            allowed_at_request += 1
            response = generate("internal://tinyllama", seed["prompt"], CANARY)["text"]
            assert inspect_response(response, [], [], CANARY)["action"] == "REDACT"
    assert allowed_at_request >= 1


def test_session_memory_window_is_bounded_to_thirty_minutes():
    assert session_windows.ttl_seconds == 1800
    assert session_windows.max_messages > 1
