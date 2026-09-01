import hashlib
import json

GENESIS_PREV_HASH = "GENESIS_00000000000000000000000000000000"

def compute_audit_hash(
    ref_type: str,
    ref_id: str,
    event: str,
    detail: str,
    created_at: str,
    prev_hash: str
) -> str:
    """
    Computes a deterministic, canonical SHA-256 hash for an audit log entry.
    Used identically by both writer (mandates.py) and verifier (audit_verifier.py)
    to eliminate any possibility of hash serialization drift.
    """
    payload = {
        "ref_type": str(ref_type or ""),
        "ref_id": str(ref_id or ""),
        "event": str(event or ""),
        "detail": str(detail or ""),
        "created_at": str(created_at or ""),
        "prev_hash": str(prev_hash or GENESIS_PREV_HASH)
    }
    canonical_bytes = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(canonical_bytes).hexdigest()
