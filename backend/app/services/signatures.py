"""
Advanced Signature Engine — 19 deterministic runtime signatures.

Every signature is a pure regex + weight pair evaluated against the *normalized*
text (NFKC-reduced, multi-pass decoded, de-homoglyphed, de-leetspeaked). No model
call, no network, no per-request state: the same input always produces the same
signature set, which is what makes the fusion score reproducible and the audit
chain meaningful.

`weight` feeds R in the fusion engine (R = min(100, sum of matching weights)).
"""
from __future__ import annotations

import re
from typing import Any

# id, category, pattern, weight, human description
_SPEC: list[tuple[str, str, re.Pattern[str], int, str]] = [
    ("ignore-instructions", "instruction_override",
     re.compile(r"ignore (all |any )?(previous|prior|above) instructions?", re.I), 70,
     "Canonical instruction-override phrasing."),
    ("role-change", "role_manipulation",
     re.compile(r"you are now|pretend (?:you are|to be)|developer mode|\bDAN\b|act as (?:an? )?(?:system|backend|unrestricted|developer|administrator|auditor|debugger)", re.I), 58,
     "Attempts to reassign the assistant's role or persona."),
    ("prompt-extraction", "system_prompt_extraction",
     re.compile(r"system prompt|repeat (?:your|the) instructions|what were you told|hidden instructions", re.I), 62,
     "Direct request for the system prompt or initialization text."),
    ("delimiter", "delimiter_manipulation",
     re.compile(r"```\s*(system|developer)|###\s*(system|developer)|<system>", re.I), 65,
     "Forged channel delimiters that imitate a privileged message."),
    ("hierarchy", "instruction_hierarchy",
     re.compile(r"higher priority|supersede|most important instruction|developer message", re.I), 58,
     "Claims of precedence over the real instruction hierarchy."),
    ("secret-request", "system_prompt_extraction",
     re.compile(r"reveal|print|output|exfiltrate", re.I), 28,
     "Weak disclosure verb; only meaningful alongside another signal."),
    ("override-synonym", "instruction_override",
     re.compile(r"set aside|disregard|replace (?:the|your|current)|obsolete|suspend|bypass|supersede|outranks?|restrictions? (?:do|does) not apply", re.I), 55,
     "Override phrased without the word 'ignore'."),
    ("protected-object", "system_prompt_extraction",
     re.compile(r"private|protected|confidential|internal|hidden|system (?:message|instructions?)|operating rules?|initiali[sz]ed your behavior|setup text", re.I), 42,
     "Names the protected object the attacker is after."),
    ("disclosure-intent", "system_prompt_extraction",
     re.compile(r"disclos(?:e|ure)|dump|emit|expose|reconstruct|reproduce|return the exact|numbered checklist", re.I), 45,
     "Verbs that describe verbatim reproduction of protected text."),
    ("authority-claim", "instruction_hierarchy",
     re.compile(r"administrator|operator|authority update|granted permission|backend diagnostic|developer>", re.I), 38,
     "Fabricated authority or elevated-permission claim."),
    ("indirect-command", "indirect_injection",
     re.compile(r"retrieved (?:web)?page says|document says|execute the phrase|instruction (?:inside|in) (?:the )?(?:document|page|email)", re.I), 48,
     "Instructions attributed to retrieved third-party content."),
    ("payload-variables", "payload_splitting",
     re.compile(r"(?:part|fragment|variable)\s*[1-9a-z]\s*=|concatenate|join (?:the )?(?:parts|fragments|variables)|execute .{0,20}(?:a\+b|stored instruction|combined)", re.I), 58,
     "Payload assembled from named fragments to defeat literal matching."),
    ("fake-history", "context_manipulation",
     re.compile(r"(?:conversation|chat) (?:history|recap)|(?:user|assistant)\s*:.{0,160}(?:user|assistant)\s*:|previously (?:approved|agreed|authorized)", re.I | re.S), 86,
     "Forged transcript that manufactures prior consent."),
    ("prefix-coercion", "instruction_override",
     re.compile(r"(?:begin|start|prefix) (?:your|the) (?:answer|response|reply).{0,60}(?:with|by saying)|respond only with|must first say", re.I), 52,
     "Forces a compliance prefix that suppresses the refusal path."),
    ("refusal-suppression", "jailbreak",
     re.compile(r"(?:do not|don't|never|must not) (?:say|use|include|mention).{0,80}(?:sorry|cannot|can't|unable|refus|warning|policy|safety)|without (?:a |any )?(?:warning|refusal|disclaimer)", re.I), 62,
     "Explicitly forbids refusal language."),
    ("nested-instruction", "indirect_injection",
     re.compile(r"(?:todo|note|instruction|comment)\s*:.{0,120}(?:ignore|reveal|override|bypass)|<(?:document|retrieved|context)>.*(?:ignore|reveal|override)", re.I | re.S), 56,
     "Instruction nested inside data the model is asked to process."),
    ("known-jailbreak-persona", "jailbreak",
     re.compile(r"\b(?:DAN|STAN|DUDE|AIM|AntiGPT|Developer Mode|Anarchy Mode|unfiltered (?:AI|model)|no restrictions? (?:AI|model))\b", re.I), 64,
     "Named jailbreak persona from public corpora."),
    ("fictional-policy-bypass", "jailbreak",
     re.compile(r"(?:fictional|hypothetical|roleplay|simulate).{0,100}(?:no (?:rules|restrictions|filters)|unfiltered|policy does not apply|always (?:comply|obey|answer))", re.I | re.S), 55,
     "Fiction framing used to argue that policy does not apply."),
    ("policy-bypass-command", "instruction_override",
     re.compile(r"forget (?:everything|all).{0,50}(?:told|rules|instructions)|override (?:(?:all|your)\s+){0,2}(?:safety |ethical )?(?:guidelines|instructions|rules)|ignore (?:all )?(?:your )?(?:training|safety protocols?|safeguards)|(?:start fresh|act as if).{0,50}(?:without (?:rules|restrictions)|jailbroken|no ethical constraints)|must comply.{0,60}(?:regardless|programming)|without (?:limitations|restrictions)", re.I | re.S), 82,
     "Direct command to discard safety configuration."),
]

# Back-compatible tuple form consumed by the request inspector.
RULES: list[tuple[str, str, re.Pattern[str], int]] = [(i, c, p, w) for i, c, p, w, _ in _SPEC]

SIGNATURE_COUNT = len(_SPEC)

TECHNIQUE_SOURCES = {
    "payload-variables": "GK-002", "delimiter": "GK-003", "prefix-coercion": "GK-004",
    "fake-history": "GK-005", "nested-instruction": "GK-006", "refusal-suppression": "GK-007",
    "known-jailbreak-persona": "GK-011..GK-018", "fictional-policy-bypass": "GK-017",
    "policy-bypass-command": "GK-007/GK-017",
}

OWASP_BY_CATEGORY = {
    "instruction_override": "LLM01: Prompt Injection",
    "role_manipulation": "LLM01: Prompt Injection (Role Manipulation)",
    "system_prompt_extraction": "LLM06: Sensitive Information Disclosure",
    "delimiter_manipulation": "LLM01: Prompt Injection (Delimiter Smuggling)",
    "instruction_hierarchy": "LLM01: Prompt Injection (Priority Overrides)",
    "indirect_injection": "LLM01: Indirect Prompt Injection",
    "payload_splitting": "LLM01: Prompt Injection (Multi-turn Payload Splitting)",
    "context_manipulation": "LLM01: Prompt Injection (Context Manipulation)",
    "jailbreak": "LLM01: Prompt Injection (Jailbreak Persona)",
}


def catalog() -> list[dict[str, Any]]:
    """Machine-readable signature list for /signatures and the report appendix."""
    return [
        {
            "id": sid,
            "category": category,
            "weight": weight,
            "description": description,
            "technique_source": TECHNIQUE_SOURCES.get(sid),
            "owasp": OWASP_BY_CATEGORY.get(category, "LLM01: Prompt Injection"),
            "pattern": pattern.pattern,
        }
        for sid, category, pattern, weight, description in _SPEC
    ]


def evaluate(normalized_text: str) -> list[dict[str, Any]]:
    """Run every signature against already-normalized text."""
    hits = []
    for sid, category, pattern, weight in RULES:
        match = pattern.search(normalized_text)
        if match:
            hits.append({
                "name": sid,
                "category": category,
                "weight": weight,
                "match": match.group(0)[:240],
                "technique_source": TECHNIQUE_SOURCES.get(sid),
            })
    return hits
