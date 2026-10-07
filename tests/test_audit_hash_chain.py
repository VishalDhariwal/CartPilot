import pytest
from backend.db import get_db, init_db
from backend.engine.mandates import create_audit_log
from backend.engine.audit_hash import compute_audit_hash
from backend.engine.audit_verifier import verify_audit_chain


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM audit_log")
    conn.commit()
    conn.close()


def test_audit_hash_chain_valid():
    conn = get_db()
    cursor = conn.cursor()
    
    create_audit_log(cursor, "intent", "intent_001", "Intent Created", "Goal: buy coffee")
    create_audit_log(cursor, "cart", "cart_001", "Cart Approved", "Total 5000 paise")
    create_audit_log(cursor, "payment", "pay_001", "Payment Succeeded", "Captured ₹50.00")
    
    conn.commit()
    conn.close()

    result = verify_audit_chain()
    assert result["is_valid"] is True
    assert result["total_records"] == 3
    assert result["head_hash"] is not None


def test_audit_content_tampering_detected():
    """
    Simulates an attacker modifying the detail text in a historical audit record.
    The verifier MUST detect content tampering.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    create_audit_log(cursor, "intent", "intent_001", "Intent Created", "Goal: buy coffee")
    create_audit_log(cursor, "cart", "cart_001", "Cart Approved", "Total 5000 paise")
    create_audit_log(cursor, "payment", "pay_001", "Payment Succeeded", "Captured ₹50.00")
    conn.commit()

    # Fetch second row id dynamically
    cursor.execute("SELECT id FROM audit_log ORDER BY id LIMIT 1 OFFSET 1")
    r2_id = cursor.fetchone()["id"]

    # Attacker tampers with row #2's detail
    cursor.execute("UPDATE audit_log SET detail = 'FORGED: Cart Approved with unlimited cap' WHERE id = ?", (r2_id,))
    conn.commit()
    conn.close()

    result = verify_audit_chain()
    assert result["is_valid"] is False
    assert result["failed_at_id"] == r2_id
    assert "Content tampered" in result["reason"]


def test_audit_chain_linkage_tampering_detected():
    """
    Simulates a sophisticated attacker who edits row #2's detail AND recomputes row #2's hash
    to hide the change. The verifier MUST catch that row #3's stored prev_hash no longer matches.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    create_audit_log(cursor, "intent", "intent_001", "Intent Created", "Goal: buy coffee")
    create_audit_log(cursor, "cart", "cart_001", "Cart Approved", "Total 5000 paise")
    create_audit_log(cursor, "payment", "pay_001", "Payment Succeeded", "Captured ₹50.00")
    conn.commit()

    # Fetch row 2 and row 3
    cursor.execute("SELECT * FROM audit_log ORDER BY id LIMIT 1 OFFSET 1")
    r2 = cursor.fetchone()
    r2_id = r2["id"]

    cursor.execute("SELECT id FROM audit_log ORDER BY id LIMIT 1 OFFSET 2")
    r3_id = cursor.fetchone()["id"]
    
    forged_detail = "FORGED: Total was 10 paise"
    forged_hash = compute_audit_hash(
        ref_type=r2["ref_type"],
        ref_id=r2["ref_id"],
        event=r2["event"],
        detail=forged_detail,
        created_at=r2["created_at"],
        prev_hash=r2["prev_hash"]
    )

    # Attacker updates detail AND hash of row 2
    cursor.execute("UPDATE audit_log SET detail = ?, hash = ? WHERE id = ?", (forged_detail, forged_hash, r2_id))
    conn.commit()
    conn.close()

    result = verify_audit_chain()
    assert result["is_valid"] is False
    # Row #3's prev_hash check will fail because row #2's hash changed!
    assert result["failed_at_id"] == r3_id
    assert "Chain linkage broken" in result["reason"]
