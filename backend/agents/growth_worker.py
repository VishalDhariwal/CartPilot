import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from backend.db import get_db
from backend.agents.growth_agent import (
    detect_all_opportunities,
    score_next_best_actions,
    execute_growth_action,
    evaluate_active_promotion_experiments,
    apply_seasonal_boosts
)

logger = logging.getLogger("cartpilot.growth_worker")

# In-memory worker telemetry state
_worker_state: Dict[str, Any] = {
    "is_running": False,
    "last_cycle_at": None,
    "last_action_at": None,
    "next_cycle_at": None,
    "actions_executed_total": 0,
    "last_cycle_summary": {
        "mode": "manual",
        "opportunities_detected": 0,
        "candidates_scored": 0,
        "executed_actions": [],
        "skipped_actions": [],
        "timestamp": None
    }
}


def get_worker_status() -> Dict[str, Any]:
    """
    Returns live autonomous worker status and execution telemetry.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT growth_mode, autonomy_threshold_paise, spend_cap_paise FROM policy_config WHERE id = 1")
        pol = cursor.fetchone()
        growth_mode = pol["growth_mode"] if pol else "manual"
        threshold_paise = pol["autonomy_threshold_paise"] if pol else 250000
        spend_cap_paise = pol["spend_cap_paise"] if pol else 1000000

        cursor.execute("SELECT COUNT(*) FROM growth_actions WHERE mode = 'autonomous'")
        autonomous_actions_count = cursor.fetchone()[0] or 0

        return {
            "enabled": growth_mode == "autonomous",
            "is_running": _worker_state["is_running"],
            "growth_mode": growth_mode,
            "autonomy_threshold_paise": threshold_paise,
            "autonomy_threshold_rupees": round(threshold_paise / 100, 2),
            "spend_cap_paise": spend_cap_paise,
            "spend_cap_rupees": round(spend_cap_paise / 100, 2),
            "last_cycle_at": _worker_state["last_cycle_at"],
            "last_action_at": _worker_state["last_action_at"],
            "next_cycle_at": _worker_state["next_cycle_at"],
            "actions_executed_total": autonomous_actions_count,
            "last_cycle_summary": _worker_state["last_cycle_summary"]
        }
    finally:
        conn.close()


def check_action_idempotency(action_type: str, target_id: str, cursor) -> tuple[bool, str]:
    """
    Ensures that an action is not duplicated across autonomous cycles.
    - RECOVER_CART: Check if cart was already dispatched a recovery link within last 24 hours.
    - PROMOTE_PRODUCT: Check if SKU is already boosted in the catalog.
    - CROSS_SELL: Check if cross-sell priority action was already executed recently.
    """
    now = datetime.utcnow()
    cutoff_24h = (now - timedelta(hours=24)).isoformat() + "Z"

    if action_type == "RECOVER_CART":
        # Check payment_mandates recovery_action
        cursor.execute("""
            SELECT id, status, recovery_action, updated_at 
            FROM payment_mandates 
            WHERE cart_id = ? AND recovery_action = 'recovery_link_sent' AND updated_at >= ?
        """, (target_id, cutoff_24h))
        if cursor.fetchone():
            return False, f"Recovery link for cart {target_id[-8:]} already dispatched within last 24h"

        # Check growth_actions records
        cursor.execute("""
            SELECT id, created_at, status 
            FROM growth_actions 
            WHERE action_type = 'RECOVER_CART' AND execution_ref LIKE ? AND created_at >= ?
        """, (f"%{target_id}%", cutoff_24h))
        if cursor.fetchone():
            return False, f"Recovery action for cart {target_id[-8:]} already logged in last 24h"

        return True, "Idempotency check passed"

    elif action_type == "PROMOTE_PRODUCT":
        cursor.execute("SELECT sku, boosted, stock FROM catalog WHERE sku = ?", (target_id,))
        item = cursor.fetchone()
        if not item:
            return False, f"SKU {target_id} not found in catalog"
        if (item["stock"] or 0) <= 0:
            return False, f"SKU {target_id} is out of stock ({item['stock']})"

        # Check active experiment capacity
        cursor.execute("SELECT max_active_promotions FROM policy_config WHERE id = 1")
        pol = cursor.fetchone()
        max_active = pol["max_active_promotions"] if pol and pol["max_active_promotions"] is not None else 5

        cursor.execute("SELECT COUNT(*) FROM promotion_experiments WHERE status = 'ACTIVE'")
        active_count = cursor.fetchone()[0] or 0
        if active_count >= max_active:
            return False, f"Promotion capacity full ({active_count}/{max_active} active experiments)"

        # Check if SKU is already in an active experiment
        cursor.execute("SELECT id FROM promotion_experiments WHERE sku = ? AND status = 'ACTIVE'", (target_id,))
        if cursor.fetchone():
            return False, f"SKU {target_id} is already in an ACTIVE promotion experiment"

        # Check if SKU is an active matched control for another active experiment
        cursor.execute("SELECT id, control_skus FROM promotion_experiments WHERE status = 'ACTIVE'")
        for r in cursor.fetchall():
            try:
                ctrls = json.loads(r["control_skus"]) if r["control_skus"] else []
                ctrl_skus = [c["sku"] if isinstance(c, dict) else c for c in ctrls]
                if target_id in ctrl_skus:
                    return False, f"SKU {target_id} is currently an active control SKU protecting experiment {r['id']}"
            except Exception:
                pass

        # Check if SKU is in cooldown
        now_str = datetime.utcnow().isoformat() + "Z"
        cursor.execute("SELECT id, cooldown_until FROM promotion_experiments WHERE sku = ? AND cooldown_until > ?", (target_id, now_str))
        cool = cursor.fetchone()
        if cool:
            return False, f"SKU {target_id} is in promotion cooldown until {cool['cooldown_until']}"

        return True, "Idempotency check passed"

    elif action_type == "CROSS_SELL":
        cursor.execute("""
            SELECT id FROM growth_actions 
            WHERE action_type = 'CROSS_SELL' AND execution_ref = ? AND created_at >= ?
        """, (target_id, cutoff_24h))
        if cursor.fetchone():
            return False, f"Cross-sell rule for SKU {target_id} already active"

        return True, "Idempotency check passed"

    return False, f"Unknown action_type: {action_type}"


def check_action_guardrails(action: Dict[str, Any], policy: Dict[str, Any], cursor) -> tuple[bool, str]:
    """
    Evaluates policy guardrails before autonomous execution:
    1. Financial exposure / action cost <= spend cap
    2. Product category in allowed categories
    3. Product in stock
    """
    spend_cap = policy.get("spend_cap_paise", 1000000)
    allowed_categories = policy.get("allowed_categories", [])

    action_cost = action.get("selected_action", {}).get("action_cost_paise", 0)
    financial_exposure = action.get("selected_action", {}).get("financial_exposure_paise", 0)

    # Threshold check on financial exposure, NOT gross cart value
    if financial_exposure > spend_cap:
        return False, f"Financial exposure (₹{financial_exposure/100:.2f}) exceeds merchant spend cap (₹{spend_cap/100:.2f})"

    # Category guardrail for product-scoped actions
    action_type = action.get("action_type") or action.get("type")
    target_id = action.get("action_target_id") or action.get("selected_action", {}).get("target_id")

    if action_type == "PROMOTE_PRODUCT" or action_type == "CROSS_SELL":
        cursor.execute("SELECT category, stock FROM catalog WHERE sku = ?", (target_id,))
        cat_row = cursor.fetchone()
        if cat_row:
            cat = cat_row["category"]
            if allowed_categories and cat not in allowed_categories:
                return False, f"Category '{cat}' is not in merchant allowed categories"
            if (cat_row["stock"] or 0) <= 0:
                return False, f"Product {target_id} is out of stock"

    return True, "Guardrail checks passed"


def execute_autonomous_cycle(max_actions_per_cycle: int = 2) -> Dict[str, Any]:
    """
    Executes a single autonomous growth cycle:
    1. Read policy configuration.
    2. Verify growth_mode == 'autonomous'.
    3. Detect opportunities and score Next Best Actions.
    4. Select top candidates by Expected Value.
    5. Enforce strict idempotency and policy guardrails.
    6. Execute at most 1–3 eligible actions.
    7. Record cycle summary to worker telemetry.
    """
    now_str = datetime.utcnow().isoformat() + "Z"
    conn = get_db()
    cursor = conn.cursor()

    executed_actions: List[Dict[str, Any]] = []
    skipped_actions: List[Dict[str, Any]] = []

    try:
        cursor.execute("SELECT growth_mode, autonomy_threshold_paise, spend_cap_paise, allowed_categories FROM policy_config WHERE id = 1")
        pol_row = cursor.fetchone()
        if not pol_row:
            return {"status": "skipped", "reason": "policy_config not found", "timestamp": now_str}

        growth_mode = pol_row["growth_mode"]
        autonomy_threshold = pol_row["autonomy_threshold_paise"]
        allowed_cats_raw = pol_row["allowed_categories"]
        allowed_categories = json.loads(allowed_cats_raw) if allowed_cats_raw else []

        policy_ctx = {
            "growth_mode": growth_mode,
            "autonomy_threshold_paise": autonomy_threshold,
            "spend_cap_paise": pol_row["spend_cap_paise"],
            "allowed_categories": allowed_categories
        }

        # Step 1b: Evaluate active promotion experiments and record telemetry
        evaluate_active_promotion_experiments(cursor)
        conn.commit()

        # Step 1c: Synchronize seasonal, weather & festival merchandise weights
        try:
            apply_seasonal_boosts()
        except Exception as e:
            logger.warning(f"Seasonal boost synchronization skipped: {e}")

        # Step 2: Only execute if growth_mode == 'autonomous'
        if growth_mode != "autonomous":
            summary = {
                "mode": growth_mode,
                "status": "idle",
                "reason": f"growth_mode is '{growth_mode}', autonomous execution skipped",
                "opportunities_detected": 0,
                "candidates_scored": 0,
                "executed_actions": [],
                "skipped_actions": [],
                "timestamp": now_str
            }
            _worker_state["last_cycle_at"] = now_str
            _worker_state["last_cycle_summary"] = summary
            return summary

        # Step 3: Detect & Score
        opps = detect_all_opportunities()
        nbas = score_next_best_actions(limit=6)

        # Step 4: Evaluate candidates ranked by Expected Value
        executed_count = 0
        for nba in nbas:
            act_type = nba.get("action_type") or nba.get("type")
            tgt_id = nba.get("action_target_id") or nba.get("selected_action", {}).get("target_id")
            ev_rupees = nba.get("expected_value_rupees", 0)

            if act_type == "NO_ACTION" or not nba.get("action_executable", True):
                skipped_actions.append({
                    "action_type": act_type,
                    "target_id": tgt_id,
                    "reason": "Diagnostic or NO_ACTION (requires merchant manual review)"
                })
                continue

            if executed_count >= max_actions_per_cycle:
                skipped_actions.append({
                    "action_type": act_type,
                    "target_id": tgt_id,
                    "reason": f"Cycle execution limit reached ({max_actions_per_cycle} max per cycle)"
                })
                continue

            # Idempotency check
            is_idem, idem_reason = check_action_idempotency(
                action_type=act_type,
                target_id=tgt_id,
                cursor=cursor
            )
            if not is_idem:
                skipped_actions.append({
                    "action_type": act_type,
                    "target_id": tgt_id,
                    "reason": f"Idempotency check failed: {idem_reason}"
                })
                continue

            # Guardrail check
            is_safe, guard_reason = check_action_guardrails(
                action=nba,
                policy=policy_ctx,
                cursor=cursor
            )
            if not is_safe:
                skipped_actions.append({
                    "action_type": act_type,
                    "target_id": tgt_id,
                    "reason": f"Guardrail check failed: {guard_reason}"
                })
                continue

            # Step 5: Execute action autonomously
            try:
                print(f"🤖 [Autonomous Worker] Executing {act_type} on {tgt_id} (EV: ₹{ev_rupees})")
                res = execute_growth_action(
                    action_type=act_type,
                    target_id=tgt_id,
                    mode="autonomous"
                )
                executed_actions.append({
                    "action_type": act_type,
                    "target_id": tgt_id,
                    "title": nba.get("title") or nba.get("business_problem"),
                    "expected_value_rupees": ev_rupees,
                    "result": res
                })
                executed_count += 1
                _worker_state["last_action_at"] = datetime.utcnow().isoformat() + "Z"
                _worker_state["actions_executed_total"] += 1
            except Exception as ex:
                skipped_actions.append({
                    "action_type": act_type,
                    "target_id": tgt_id,
                    "reason": f"Execution error: {str(ex)}"
                })

        summary = {
            "mode": growth_mode,

            "status": "completed",
            "opportunities_detected": len(opps),
            "candidates_scored": len(nbas),
            "executed_actions": executed_actions,
            "skipped_actions": skipped_actions,
            "timestamp": now_str
        }

        _worker_state["last_cycle_at"] = now_str
        _worker_state["last_cycle_summary"] = summary
        return summary

    finally:
        conn.close()


async def run_autonomous_growth_worker(interval_seconds: int = 300):
    """
    Continuous background loop for autonomous Next Best Action execution.
    Runs every interval_seconds (default: 5 minutes).
    Gracefully handles exceptions and cancellation.
    """
    _worker_state["is_running"] = True
    print(f"🚀 [Autonomous Growth Worker] Started (interval: {interval_seconds}s, mode: autonomous loop)")

    try:
        while True:
            cycle_start = datetime.utcnow()
            _worker_state["next_cycle_at"] = (cycle_start + timedelta(seconds=interval_seconds)).isoformat() + "Z"

            try:
                summary = execute_autonomous_cycle(max_actions_per_cycle=2)
                if summary.get("executed_actions"):
                    print(f"✅ [Autonomous Growth Worker] Cycle completed: executed {len(summary['executed_actions'])} action(s)")
            except Exception as e:
                print(f"⚠️ [Autonomous Growth Worker] Error in cycle: {e}")

            await asyncio.sleep(interval_seconds)

    except asyncio.CancelledError:
        print("🛑 [Autonomous Growth Worker] Worker task cancelled. Shutting down gracefully.")
        _worker_state["is_running"] = False
    finally:
        _worker_state["is_running"] = False
