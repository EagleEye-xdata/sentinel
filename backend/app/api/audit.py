"""PLANE 4 endpoints — append-only chain inspection, sealing, and verification."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditEvent
from ..services.audit import audit_chain, record

router = APIRouter(tags=["audit"])


@router.get("/audit/events")
def list_events(limit: int = 100, event_type: str | None = None, db: Session = Depends(get_db)):
    query = db.query(AuditEvent)
    if event_type:
        query = query.filter_by(event_type=event_type)
    rows = query.order_by(AuditEvent.seq.desc()).limit(min(limit, 1000)).all()
    return [
        {
            "seq": r.seq,
            "ts": r.ts,
            "event_type": r.event_type,
            "key_id": r.key_id,
            "payload": r.payload,
            "prev_hash": r.prev_hash,
            "entry_hash": r.entry_hash,
        }
        for r in rows
    ]


@router.get("/audit/verify")
def verify_chain(run_id: int | None = None, db: Session = Depends(get_db)):
    """Re-walk the chain and recompute every HMAC. Names the first corrupted seq."""
    return audit_chain.verify(db, run_id)


@router.post("/audit/publish-key")
def publish_key(db: Session = Depends(get_db)):
    """Seal the open segment: publish its key atomically, then rotate.

    After this call the sealed segment is independently verifiable by anyone
    holding the published key file, and it can no longer be rewritten -- the
    published record commits to the segment's head hash.
    """
    result = audit_chain.publish_segment(db)
    if result.get("published"):
        record(db, "audit.key_published", {
            "sealed_key_id": result["key_id"],
            "head_seq": result["head_seq"],
            "head_hash": result["head_hash"],
            "events": result["events"],
        })
    return result


@router.get("/audit/keys")
def published_keys(db: Session = Depends(get_db)):
    return {
        "open_segment": audit_chain.key_id,
        "published_segments": sorted(audit_chain.published_keys()),
        "key_dir": str(audit_chain.key_dir),
        "algorithm": "HMAC-SHA256",
    }
