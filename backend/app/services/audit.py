"""
PLANE 4 — Cryptographic Audit.

An append-only, HMAC-SHA256 authenticated hash chain with *atomic key publication*.

Why HMAC and not a bare SHA-256 chain
-------------------------------------
A plain hash chain proves nothing against the process that wrote it: whoever can
edit a row can also recompute every hash after it. Chaining under an HMAC keyed
with a secret the writer holds only while a segment is *open* raises the bar --
forging history requires the key, not just write access to the database.

Atomic key publication
----------------------
A segment's key lives in memory only. `publish_segment()` seals the segment: it
writes {key_id, key, sealed_at, head_seq, head_hash} to disk with a temp-file +
os.replace (atomic rename -- a reader sees either the old file or the whole new
one, never a half-written one), then rotates in a fresh key for the next segment.

After publication anyone can verify the sealed segment, and nobody -- including
the operator -- can rewrite it, because the key that authenticated it is now
public and the head hash it commits to is fixed. Verification is offline: no
network, no service, just the published key file and the event rows.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import settings

GENESIS_HASH = "0" * 64


def canonical(payload: Any) -> str:
    """Deterministic JSON so the same payload always hashes to the same bytes."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_mac(key: bytes, seq: int, ts: str, event_type: str, prev_hash: str, payload: Any) -> str:
    message = "|".join([str(seq), ts, event_type, prev_hash, canonical(payload)])
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


class AuditChain:
    """Process-wide chain writer. Thread-safe; one open segment at a time."""

    def __init__(self, key_dir: Path | None = None):
        self._lock = threading.Lock()
        self.key_dir = Path(key_dir or settings.audit_key_dir)
        self.key_dir.mkdir(parents=True, exist_ok=True)
        self._key_id, self._key = self._new_segment_key()

    # ---------------------------------------------------------------- keys

    @staticmethod
    def _new_segment_key() -> tuple[str, bytes]:
        return f"seg-{secrets.token_hex(6)}", secrets.token_bytes(32)

    @property
    def key_id(self) -> str:
        return self._key_id

    def _published_path(self, key_id: str) -> Path:
        return self.key_dir / f"{key_id}.key.json"

    def published_keys(self) -> dict[str, bytes]:
        out: dict[str, bytes] = {}
        for path in sorted(self.key_dir.glob("*.key.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                out[record["key_id"]] = bytes.fromhex(record["key"])
            except (ValueError, KeyError, OSError):
                continue
        return out

    def _key_for(self, key_id: str) -> bytes | None:
        if key_id == self._key_id:
            return self._key
        return self.published_keys().get(key_id)

    # -------------------------------------------------------------- append

    def append(self, db, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Append one authenticated event. Never raises into the caller's path."""
        from ..models import AuditEvent  # local import: avoids a circular import at module load

        with self._lock:
            last = db.query(AuditEvent).order_by(AuditEvent.seq.desc()).first()
            seq = (last.seq + 1) if last else 1
            prev_hash = last.entry_hash if last else GENESIS_HASH
            ts = datetime.now(timezone.utc).isoformat()
            entry_hash = compute_mac(self._key, seq, ts, event_type, prev_hash, payload)
            row = AuditEvent(
                seq=seq,
                ts=ts,
                event_type=event_type,
                key_id=self._key_id,
                payload=payload,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
            )
            db.add(row)
            db.commit()
            return {
                "seq": seq,
                "ts": ts,
                "event_type": event_type,
                "key_id": self._key_id,
                "prev_hash": prev_hash,
                "entry_hash": entry_hash,
            }

    # ------------------------------------------------------------- publish

    def publish_segment(self, db) -> dict[str, Any]:
        """Seal the open segment: atomically publish its key, then rotate."""
        from ..models import AuditEvent

        with self._lock:
            rows = db.query(AuditEvent).filter_by(key_id=self._key_id).order_by(AuditEvent.seq).all()
            if not rows:
                return {"published": False, "reason": "segment_empty", "key_id": self._key_id}

            record = {
                "key_id": self._key_id,
                "key": self._key.hex(),
                "algorithm": "HMAC-SHA256",
                "sealed_at": datetime.now(timezone.utc).isoformat(),
                "first_seq": rows[0].seq,
                "head_seq": rows[-1].seq,
                "head_hash": rows[-1].entry_hash,
                "events": len(rows),
            }
            path = self._published_path(self._key_id)
            # Atomic publication: write a temp file in the same directory, fsync,
            # then os.replace() it into place. Readers never observe a partial key.
            fd, tmp_name = tempfile.mkstemp(dir=str(self.key_dir), prefix=".pub-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(record, handle, indent=2, sort_keys=True)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_name, path)
            except BaseException:
                Path(tmp_name).unlink(missing_ok=True)
                raise

            sealed = dict(record)
            sealed.pop("key")
            self._key_id, self._key = self._new_segment_key()
            return {"published": True, "path": str(path), "rotated_to": self._key_id, **sealed}

    # -------------------------------------------------------------- verify

    def verify(self, db, run_id: int | None = None) -> dict[str, Any]:
        """Re-walk the chain and recompute every MAC. Reports the first break."""
        from ..models import AuditEvent

        rows = db.query(AuditEvent).order_by(AuditEvent.seq).all()
        if run_id is not None:
            rows = [r for r in rows if (r.payload or {}).get("run_id") == run_id]

        checked = 0
        unverifiable = 0
        prev_hash = GENESIS_HASH
        expected_seq = None

        for row in rows:
            if expected_seq is not None and row.seq != expected_seq:
                return self._broken(row.seq, "sequence_gap", checked, len(rows),
                                    f"expected seq {expected_seq}, found {row.seq}")
            expected_seq = row.seq + 1

            if run_id is None and row.prev_hash != prev_hash:
                return self._broken(row.seq, "chain_link_mismatch", checked, len(rows),
                                    "prev_hash does not match the previous entry's hash")

            key = self._key_for(row.key_id)
            if key is None:
                unverifiable += 1
                prev_hash = row.entry_hash
                continue

            recomputed = compute_mac(key, row.seq, row.ts, row.event_type, row.prev_hash, row.payload)
            if not hmac.compare_digest(recomputed, row.entry_hash):
                return self._broken(row.seq, "mac_mismatch", checked, len(rows),
                                    "recomputed HMAC does not match the stored entry hash")
            checked += 1
            prev_hash = row.entry_hash

        return {
            "valid": True,
            "algorithm": "HMAC-SHA256",
            "entries": len(rows),
            "verified": checked,
            "unverifiable_segments": unverifiable,
            "head_hash": rows[-1].entry_hash if rows else GENESIS_HASH,
            "open_segment": self._key_id,
            "published_segments": sorted(self.published_keys()),
            "detail": "chain intact" if not unverifiable else
                      f"{unverifiable} entr{'y' if unverifiable == 1 else 'ies'} in an unpublished foreign segment",
        }

    @staticmethod
    def _broken(seq: int, reason: str, checked: int, total: int, detail: str) -> dict[str, Any]:
        return {
            "valid": False,
            "algorithm": "HMAC-SHA256",
            "entries": total,
            "verified": checked,
            "corrupted_seq": seq,
            "reason": reason,
            "detail": detail,
        }


audit_chain = AuditChain()


def record(db, event_type: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Best-effort append. The audit plane must never break the security path."""
    try:
        return audit_chain.append(db, event_type, payload)
    except Exception:  # pragma: no cover - defensive
        try:
            db.rollback()
        except Exception:
            pass
        return None
