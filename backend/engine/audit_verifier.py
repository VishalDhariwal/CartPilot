import json
from backend.db import get_db
from backend.engine.audit_hash import compute_audit_hash, GENESIS_PREV_HASH


def verify_audit_chain() -> dict:
    """
    Cryptographically verifies the entire audit_log chain from genesis to head.
    Performs a strict dual-check on every record:
      1. Content Integrity: Recomputes the row's hash from its own content and checks stored hash.
      2. Chain Linkage: Verifies row.prev_hash strictly matches the previous row's stored hash.
    
    Returns structured verification results:
      - If valid: {"is_valid": True, "total_records": N, "head_hash": "..."}
      - If tampered: {"is_valid": False, "failed_at_id": id, "reason": "...", "detail": "..."}
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, ref_type, ref_id, event, detail, prev_hash, hash, created_at FROM audit_log ORDER BY id ASC")
        rows = cursor.fetchall()
        
        if not rows:
            return {
                "is_valid": True,
                "total_records": 0,
                "head_hash": GENESIS_PREV_HASH,
                "message": "Audit log is empty. Genesis chain intact."
            }
        
        prev_stored_hash = GENESIS_PREV_HASH
        
        for idx, row in enumerate(rows):
            row_id = row["id"]
            ref_type = row["ref_type"]
            ref_id = row["ref_id"]
            event = row["event"]
            detail = row["detail"]
            created_at = row["created_at"]
            stored_prev_hash = row["prev_hash"] or GENESIS_PREV_HASH
            stored_hash = row["hash"] or ""
            
            # Check 1: Chain Linkage Check
            if stored_prev_hash != prev_stored_hash:
                return {
                    "is_valid": False,
                    "failed_at_id": row_id,
                    "record_index": idx,
                    "reason": "Chain linkage broken (prev_hash mismatch)",
                    "expected_prev_hash": prev_stored_hash,
                    "found_prev_hash": stored_prev_hash,
                    "detail": f"Audit record #{row_id} has invalid prev_hash linkage."
                }
            
            # Check 2: Content Integrity Check
            recomputed_hash = compute_audit_hash(
                ref_type=ref_type,
                ref_id=ref_id,
                event=event,
                detail=detail,
                created_at=created_at,
                prev_hash=stored_prev_hash
            )
            
            if recomputed_hash != stored_hash:
                return {
                    "is_valid": False,
                    "failed_at_id": row_id,
                    "record_index": idx,
                    "reason": "Content tampered (hash mismatch)",
                    "expected_hash": recomputed_hash,
                    "found_hash": stored_hash,
                    "detail": f"Audit record #{row_id} content was modified after hash generation."
                }
            
            prev_stored_hash = stored_hash
            
        return {
            "is_valid": True,
            "total_records": len(rows),
            "head_hash": prev_stored_hash,
            "message": f"Successfully verified cryptographic integrity across all {len(rows)} audit log records."
        }
    finally:
        conn.close()
