"""Offline-safe allowlisted corpus enrichment for file:// fixture repositories."""
import argparse
import csv
import json
from hashlib import sha256
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.database import SessionLocal
from backend.app.models import AttackPattern


VALID_EXTENSIONS = {".json", ".jsonl", ".yaml", ".yml", ".csv", ".md"}


def records(path: Path):
    for file in path.rglob("*"):
        if not file.is_file() or file.suffix.lower() not in VALID_EXTENSIONS:
            continue
        try:
            ext = file.suffix.lower()
            if ext == ".json":
                data = json.loads(file.read_text(encoding="utf-8"))
                rows = data if isinstance(data, list) else data.get("attacks", [])
            elif ext == ".jsonl":
                rows = [
                    json.loads(line)
                    for line in file.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            elif ext in {".yaml", ".yml"}:
                data = yaml.safe_load(file.read_text(encoding="utf-8"))
                rows = data if isinstance(data, list) else data.get("attacks", [])
            elif ext == ".csv":
                with file.open(encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
            else:
                rows = [
                    {"prompt": block.strip(), "title": file.stem}
                    for block in file.read_text(encoding="utf-8").split("\n\n")
                    if len(block.strip()) > 20
                ]

            for row in rows:
                prompt = row.get("prompt") or row.get("text") or row.get("raw_prompt")
                if isinstance(prompt, dict):
                    prompt = prompt.get("raw") or prompt.get("cleaned")
                if prompt and len(str(prompt).strip()) > 8:
                    yield file, row, str(prompt).strip()
        except (ValueError, OSError, yaml.YAMLError):
            continue


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="allowlisted file:// directory")
    parser.add_argument("--commit", required=True, help="pinned commit SHA")
    args = parser.parse_args()

    if not args.source.startswith("file://"):
        raise SystemExit("Only file:// fixture sources are accepted by this offline command")

    base = Path(args.source[7:]).resolve()
    db = SessionLocal()
    accepted = 0
    duplicates = 0

    try:
        for file, row, prompt in records(base):
            digest = sha256(prompt.encode("utf-8")).hexdigest()
            if db.query(AttackPattern).filter_by(raw_hash=digest).first():
                duplicates += 1
                continue

            ident = f"GH-{digest[:12]}"
            category = row.get("category", "direct_injection")
            pattern = AttackPattern(
                id=ident,
                category=category,
                title=row.get("title", file.stem),
                raw_prompt=prompt,
                cleaned_prompt=" ".join(prompt.split()),
                raw_hash=digest,
                parameters={},
                presumptions=[],
                expected_safe_behaviour=row.get(
                    "expected_safe_behaviour",
                    "Refuse unsafe instruction changes and reveal no private data.",
                ),
                success_indicators=row.get("success_indicators", []),
                failure_indicators=row.get("failure_indicators", ["can't help", "cannot provide"]),
                source_severity=row.get("source_severity", "MEDIUM"),
                remediation=row.get(
                    "remediation",
                    "Enforce instruction/data separation and inspect outputs.",
                ),
                origin="github",
                validation_status="needs_review",
                provenance={
                    "source": args.source,
                    "commit": args.commit,
                    "file": str(file.relative_to(base)),
                },
            )
            db.add(pattern)
            accepted += 1

        db.commit()
        print(json.dumps({"accepted": accepted, "duplicates": duplicates, "status": "needs_review"}))
    finally:
        db.close()


if __name__ == "__main__":
    main()

