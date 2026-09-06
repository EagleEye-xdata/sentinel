"""PLANE 4 — HMAC-SHA256 authenticated chain and atomic key publication."""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import AuditEvent
from backend.app.services.audit import GENESIS_HASH, AuditChain, compute_mac


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'audit.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture()
def chain(tmp_path):
    return AuditChain(key_dir=tmp_path / "keys")


def test_chain_links_each_entry_to_the_previous_one(chain, db):
    first = chain.append(db, "run.started", {"run_id": 1})
    second = chain.append(db, "execution.decision", {"run_id": 1, "seq": 1})
    assert first["prev_hash"] == GENESIS_HASH
    assert second["prev_hash"] == first["entry_hash"]
    assert second["seq"] == first["seq"] + 1


def test_verify_accepts_an_untouched_chain(chain, db):
    for i in range(5):
        chain.append(db, "execution.decision", {"run_id": 1, "seq": i})
    result = chain.verify(db)
    assert result["valid"] is True
    assert result["entries"] == 5 and result["verified"] == 5


def test_tampering_with_a_payload_is_detected(chain, db):
    for i in range(4):
        chain.append(db, "execution.decision", {"run_id": 1, "seq": i, "outcome": "RESISTED"})
    row = db.query(AuditEvent).filter_by(seq=2).one()
    row.payload = {**row.payload, "outcome": "SUCCESSFUL"}   # rewrite history
    db.commit()

    result = chain.verify(db)
    assert result["valid"] is False
    assert result["corrupted_seq"] == 2
    assert result["reason"] == "mac_mismatch"


def test_recomputing_the_hash_without_the_key_does_not_repair_the_chain(chain, db):
    """A plain SHA-256 chain could be re-stitched by the writer; an HMAC one cannot."""
    chain.append(db, "execution.decision", {"run_id": 1, "outcome": "RESISTED"})
    chain.append(db, "execution.decision", {"run_id": 1, "outcome": "RESISTED"})
    row = db.query(AuditEvent).filter_by(seq=2).one()
    row.payload = {"run_id": 1, "outcome": "SUCCESSFUL"}
    # An attacker without the segment key can only guess at a MAC.
    row.entry_hash = compute_mac(b"\x00" * 32, row.seq, row.ts, row.event_type, row.prev_hash, row.payload)
    db.commit()
    assert chain.verify(db)["valid"] is False


def test_deleting_an_entry_is_detected_as_a_sequence_gap(chain, db):
    for i in range(4):
        chain.append(db, "execution.decision", {"run_id": 1, "seq": i})
    db.delete(db.query(AuditEvent).filter_by(seq=2).one())
    db.commit()
    result = chain.verify(db)
    assert result["valid"] is False
    assert result["reason"] in {"sequence_gap", "chain_link_mismatch"}


def test_publishing_seals_the_segment_and_rotates_the_key(chain, db, tmp_path):
    for i in range(3):
        chain.append(db, "execution.decision", {"run_id": 7, "seq": i})
    sealed_id = chain.key_id

    result = chain.publish_segment(db)
    assert result["published"] is True
    assert result["key_id"] == sealed_id
    assert result["events"] == 3
    assert chain.key_id != sealed_id, "the open segment must rotate to a fresh key"

    record = json.loads((tmp_path / "keys" / f"{sealed_id}.key.json").read_text())
    assert record["algorithm"] == "HMAC-SHA256"
    assert record["head_seq"] == 3
    assert len(bytes.fromhex(record["key"])) == 32


def test_a_published_segment_stays_verifiable_after_rotation(chain, db):
    for i in range(3):
        chain.append(db, "execution.decision", {"run_id": 7, "seq": i})
    chain.publish_segment(db)
    chain.append(db, "run.completed", {"run_id": 7})

    result = chain.verify(db)
    assert result["valid"] is True
    assert result["verified"] == 4
    assert len(result["published_segments"]) == 1


def test_publication_leaves_no_partial_file_behind(chain, db, tmp_path):
    chain.append(db, "run.started", {"run_id": 1})
    chain.publish_segment(db)
    leftovers = list((tmp_path / "keys").glob(".pub-*.tmp"))
    assert leftovers == [], "atomic publication must not leave temp files"


def test_publishing_an_empty_segment_is_a_no_op(chain, db):
    assert chain.publish_segment(db)["published"] is False


def test_run_scoped_verification(chain, db):
    chain.append(db, "execution.decision", {"run_id": 1})
    chain.append(db, "execution.decision", {"run_id": 2})
    chain.append(db, "execution.decision", {"run_id": 1})
    assert chain.verify(db, run_id=1)["entries"] == 2
