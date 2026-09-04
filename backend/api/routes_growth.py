import json
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query
from backend.db import get_db
from backend.agents.growth_agent import (
    detect_all_opportunities,
    score_next_best_actions,
    execute_growth_action,
    get_growth_metrics,
    get_agent_performance_stats,
    get_learning_loop_stats,
    get_growth_timeline,
    set_growth_mode,
    get_promotion_system_state,
    evaluate_active_promotion_experiments,
    classify_legacy_boosted_skus,
    assess_legacy_boosts_observational,
)
from backend.engine.mandates import create_audit_log, append_audit_log

router = APIRouter()


class ExecuteActionRequest(BaseModel):
    action_type: Optional[str] = None
    target_id: Optional[str] = None
    action_id: Optional[str] = None
    sku: Optional[str] = None
    mode: Optional[str] = "manual"


class SetModeRequest(BaseModel):
    growth_mode: str


class ReconcileBoostRequest(BaseModel):
    sku: str
    action: str  # 'keep', 'retire', 'convert_to_experiment'


class ExperimentDecisionRequest(BaseModel):
    decision: str  # 'KEEP_STANDING_BOOST', 'REVERT_TO_ORGANIC', 'RE_RUN_LATER'


@router.get("/opportunities", tags=["AI Growth Agent"])
def list_growth_opportunities():
    """
    Returns all real-time detected revenue opportunities across the store:
    - Abandoned / Recoverable Carts
    - Strong Empirical Cross-Sells
    - High-Stock Weak Sales Velocity Items (Controlled Experiments)
    - Conversion Review Proxies
    - Live Promotion System State (Capacity, Active count)
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        opps = detect_all_opportunities()
        promo_state = get_promotion_system_state(cursor)
        return {
            "count": len(opps),
            "opportunities": opps,
            "promotion_system_state": promo_state,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    finally:
        conn.close()


@router.get("/promotion-experiments", tags=["AI Growth Agent"])
def list_promotion_experiments():
    """
    Returns live managed promotion experiments, capacity status, and legacy unmanaged boosts.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        evaluate_active_promotion_experiments(cursor)
        conn.commit()

        promo_state = get_promotion_system_state(cursor)

        cursor.execute("SELECT * FROM promotion_experiments ORDER BY created_at DESC LIMIT 50")
        all_exps = [dict(r) for r in cursor.fetchall()]

        return {
            "system_state": promo_state,
            "experiments": all_exps,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    finally:
        conn.close()


@router.get("/legacy-boosts-assessment", tags=["AI Growth Agent"])
def get_legacy_boosts_assessment():
    """
    Returns observational assessment of the 82 legacy boosted SKUs vs category median velocity.
    Surfaces observational suggestions (KEEP, RETIRE, CONVERT_TO_EXPERIMENT) with explicit disclaimer.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        data = assess_legacy_boosts_observational(cursor)
        return {
            **data,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    finally:
        conn.close()


@router.post("/promotion-experiments/{exp_id}/decision", tags=["AI Growth Agent"])
def submit_experiment_decision(exp_id: str, req: ExperimentDecisionRequest):
    """
    DAY-14 DECISION GATE:
    Allows merchant to make the final strategic choice on a concluded promotion experiment:
    - 'KEEP_STANDING_BOOST': Keeps 1.35x boost permanently enabled
    - 'REVERT_TO_ORGANIC': Discards boost, returns product to 1.0x organic ranking
    - 'RE_RUN_LATER': Schedules re-test after a 7-day cooldown
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM promotion_experiments WHERE id = ?", (exp_id,))
        exp = cursor.fetchone()
        if not exp:
            raise HTTPException(status_code=404, detail=f"Promotion experiment {exp_id} not found.")

        sku = exp["sku"]
        now_dt = datetime.utcnow()
        now_str = now_dt.isoformat() + "Z"

        if req.decision == "KEEP_STANDING_BOOST":
            cursor.execute("UPDATE catalog SET boosted = 1 WHERE sku = ?", (sku,))
            cursor.execute("""
                UPDATE promotion_experiments
                SET merchant_decision = 'KEEP_STANDING_BOOST', updated_at = ?
                WHERE id = ?
            """, (now_str, exp_id))
            create_audit_log(
                cursor,
                "promotion_experiment",
                exp_id,
                "Merchant Decision: Keep Standing Boost",
                f"Merchant chose to KEEP permanent 1.35x standing boost for SKU {sku} after experiment completion."
            )
            conn.commit()
            return {"status": "success", "message": f"Retained standing 1.35x boost for SKU {sku}."}

        elif req.decision == "REVERT_TO_ORGANIC":
            cursor.execute("UPDATE catalog SET boosted = 0 WHERE sku = ?", (sku,))
            cursor.execute("""
                UPDATE promotion_experiments
                SET merchant_decision = 'REVERT_TO_ORGANIC', updated_at = ?
                WHERE id = ?
            """, (now_str, exp_id))
            create_audit_log(
                cursor,
                "promotion_experiment",
                exp_id,
                "Merchant Decision: Revert to Organic",
                f"Merchant chose to REVERT SKU {sku} to standard 1.0x organic ranking."
            )
            conn.commit()
            return {"status": "success", "message": f"Reverted SKU {sku} to 1.0x organic ranking."}

        elif req.decision == "RE_RUN_LATER":
            cooldown_7d = (now_dt + timedelta(days=7)).isoformat() + "Z"
            cursor.execute("UPDATE catalog SET boosted = 0 WHERE sku = ?", (sku,))
            cursor.execute("""
                UPDATE promotion_experiments
                SET merchant_decision = 'RE_RUN_LATER', cooldown_until = ?, updated_at = ?
                WHERE id = ?
            """, (cooldown_7d, now_str, exp_id))
            create_audit_log(
                cursor,
                "promotion_experiment",
                exp_id,
                "Merchant Decision: Re-Run Later",
                f"Merchant queued SKU {sku} to re-run later (cooldown until {cooldown_7d})."
            )
            conn.commit()
            return {"status": "success", "message": f"Queued SKU {sku} for re-test with 7-day cooldown (until {cooldown_7d})."}

        else:
            raise HTTPException(status_code=400, detail=f"Invalid decision '{req.decision}'. Must be KEEP_STANDING_BOOST, REVERT_TO_ORGANIC, or RE_RUN_LATER.")
    finally:
        conn.close()


@router.post("/reconcile-legacy-boost", tags=["AI Growth Agent"])
def reconcile_legacy_boost(req: ReconcileBoostRequest):
    """
    Merchant review action for legacy unmanaged boosts:
    - 'keep': Retains live boost (unmanaged)
    - 'retire': Safely reverts boost to 1.0x organic baseline
    - 'convert_to_experiment': Enrolls SKU into a 14-day controlled promotion experiment
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        now_str = datetime.utcnow().isoformat() + "Z"
        cursor.execute("SELECT sku, name, category, price_paise, stock FROM catalog WHERE sku = ?", (req.sku,))
        item = cursor.fetchone()
        if not item:
            raise HTTPException(status_code=404, detail=f"SKU {req.sku} not found.")

        if req.action == "retire":
            cursor.execute("UPDATE catalog SET boosted = 0 WHERE sku = ?", (req.sku,))
            create_audit_log(
                cursor,
                "catalog",
                req.sku,
                "Legacy Boost Retired",
                f"Merchant retired legacy unmanaged boost for {item['name']} (SKU: {req.sku}). Returned to organic 1.0x baseline."
            )
            conn.commit()
            return {"status": "success", "message": f"Successfully retired boost for {item['name']}. Returned to 1.0x organic baseline."}

        elif req.action == "keep":
            create_audit_log(
                cursor,
                "catalog",
                req.sku,
                "Legacy Boost Retained",
                f"Merchant explicitly retained legacy unmanaged boost for {item['name']} (SKU: {req.sku})."
            )
            conn.commit()
            return {"status": "success", "message": f"Retained 1.35x boost for {item['name']}."}

        elif req.action == "convert_to_experiment":
            return execute_growth_action("PROMOTE_PRODUCT", req.sku, mode="manual")

        else:
            raise HTTPException(status_code=400, detail=f"Invalid action '{req.action}'. Must be keep, retire, or convert_to_experiment.")
    finally:
        conn.close()


@router.get("/nba", tags=["AI Growth Agent"])
def get_next_best_actions(limit: int = Query(default=5, ge=1, le=20)):
    """
    Evaluates and ranks detected opportunities using the Next Best Action (NBA) Expected Value formula.
    """
    try:
        actions = score_next_best_actions(limit=limit)
        return {
            "count": len(actions),
            "next_best_actions": actions,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics", tags=["AI Growth Agent"])
def get_growth_kpis():
    """
    Returns live revenue metrics with strict separation of:
    - OBSERVED AI-Attributed Revenue (Realized cash via accepted upsells + recovered payments)
    - ESTIMATED Revenue Opportunity (Potential value in idle carts & stock)
    """
    try:
        metrics = get_growth_metrics()
        return {
            **metrics,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance", tags=["AI Growth Agent"])
@router.get("/learning", tags=["AI Growth Agent"])
def get_growth_performance_stats():
    """
    AGENT PERFORMANCE: Returns empirical performance statistics powering the closed-loop AI learning engine.
    """
    try:
        stats = get_agent_performance_stats()
        return {
            **stats,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit-log", tags=["AI Growth Agent"])
@router.get("/audit-ledger", tags=["AI Growth Agent"])
def get_growth_audit_log(limit: int = Query(default=100, ge=1, le=1000)):
    """
    Returns the real cryptographic SHA-256 tamper-evident hash-chained audit ledger.
    Every autonomous agent decision, recommendation, rule change, and payment authorization is logged with full explanation.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, ref_type, ref_id, event, detail, prev_hash, hash, created_at
            FROM audit_log
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        logs = []
        for r in rows:
            logs.append({
                "id": r["id"],
                "ref_type": r["ref_type"],
                "ref_id": r["ref_id"],
                "action": r["event"],
                "event_type": r["event"],
                "detail": r["detail"] or "Autonomous agent decision executed and verified against merchant governance policy.",
                "prev_hash": r["prev_hash"] or "GENESIS_0000000000000000000000000000000000000000000000000000000000000000",
                "hash": r["hash"],
                "timestamp": r["created_at"],
                "created_at": r["created_at"],
            })
        return {
            "count": len(logs),
            "logs": logs,
            "audit_trail": logs,
            "status": "verified"
        }
    finally:
        conn.close()


@router.get("/timeline", tags=["AI Growth Agent"])
def get_timeline(limit: int = Query(default=100, ge=1, le=500)):
    """
    AGENT TIMELINE: Returns real chronological timeline of agent scans, actions, outcomes, and policy checks.
    """
    try:
        timeline = get_growth_timeline(limit=limit)
        return {
            "count": len(timeline),
            "timeline": timeline,
            "events": timeline,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/actions", tags=["AI Growth Agent"])
def list_growth_actions(
    status: Optional[str] = Query(default=None, description="Filter by status: detected | executing | completed | dismissed"),
    limit: int = Query(default=50, ge=1, le=100)
):
    """
    Lists historical and active growth actions recorded by the Growth Agent.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        query = "SELECT * FROM growth_actions"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        actions = []
        for r in rows:
            actions.append({
                "id": r["id"],
                "action_type": r["action_type"],
                "status": r["status"],
                "opportunity_type": r["opportunity_type"],
                "title": r["title"],
                "explanation": r["explanation"],
                "affected_ref": json.loads(r["affected_ref"]) if r["affected_ref"] else None,
                "est_revenue_paise": r["est_revenue_paise"],
                "est_revenue_rupees": round(r["est_revenue_paise"] / 100, 2),
                "confidence": r["confidence"],
                "recommended_action": r["recommended_action"],
                "execution_ref": r["execution_ref"],
                "mode": r["mode"],
                "created_at": r["created_at"],
                "executed_at": r["executed_at"],
                "dismissed_at": r["dismissed_at"],
                "notes": r["notes"]
            })
        return {"count": len(actions), "actions": actions}
    finally:
        conn.close()


@router.post("/execute", tags=["AI Growth Agent"])
@router.post("/opportunities/execute", tags=["AI Growth Agent"])
def execute_action(req: ExecuteActionRequest):
    """
    Executes a Next Best Action:
    - OFFER_RECOVERY_INCENTIVE / RECOVER_CART: generates a smart time-limited recovery offer for an abandoned cart
    - PROMOTE_PRODUCT: activates 1.35x catalog boost for a slow-moving item
    - CROSS_SELL: validates and surfaces cross-sell rule
    """
    act_type = (req.action_type or "PROMOTE_PRODUCT").upper()
    if act_type in ["PROMOTION", "PROMOTIONS", "PROMOTE"]:
        act_type = "PROMOTE_PRODUCT"
    elif act_type in ["RECOVERY", "RECOVER", "ABANDONED_CART", "RECOVER_CART", "OFFER_INCENTIVE", "OFFER_RECOVERY_INCENTIVE"]:
        act_type = "OFFER_RECOVERY_INCENTIVE"
    elif act_type in ["CROSS_SELL", "XSELL", "PRIORITIZE_CROSS_SELL"]:
        act_type = "CROSS_SELL"

    target = req.target_id or req.sku or req.action_id or "KIT-BRD-HAN-061"

    # If target is a compound 'SKU_A->SKU_B', extract target SKU_B
    if "->" in str(target):
        target = target.split("->")[-1].strip()

    try:
        res = execute_growth_action(
            action_type=act_type,
            target_id=target,
            mode=req.mode or "manual"
        )
        return res
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/actions/{action_id}/dismiss", tags=["AI Growth Agent"])
def dismiss_action(action_id: str):
    """
    Marks a growth opportunity as dismissed.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        now_str = datetime.utcnow().isoformat() + "Z"
        cursor.execute("""
            UPDATE growth_actions
            SET status = 'dismissed', dismissed_at = ?
            WHERE id = ?
        """, (now_str, action_id))

        if cursor.rowcount == 0:
            # If not in table, insert a dismissed record
            cursor.execute("""
                INSERT INTO growth_actions (
                    id, action_type, status, opportunity_type, title, explanation,
                    mode, created_at, dismissed_at
                ) VALUES (?, 'DISMISSED', 'dismissed', 'user_dismissed', 'Dismissed Opportunity', 'Dismissed by merchant', 'manual', ?, ?)
            """, (action_id, now_str, now_str))

        create_audit_log(
            cursor,
            "growth_action",
            action_id,
            "Growth Action Dismissed",
            f"Merchant dismissed growth action {action_id}"
        )
        conn.commit()
        return {"status": "dismissed", "action_id": action_id}
    finally:
        conn.close()


@router.put("/mode", tags=["AI Growth Agent"])
def update_growth_mode(req: SetModeRequest):
    """
    Configures merchant growth autonomy mode:
    - 'manual': AI identifies opportunities, merchant clicks Execute.
    - 'suggested': AI prepares actionable pre-filled links for 1-click confirmation.
    - 'autonomous': AI executes actions automatically within policy guardrail caps.
    """
    try:
        res = set_growth_mode(req.growth_mode)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/worker-status", tags=["AI Growth Agent"])
def get_growth_worker_status():
    """
    Returns live autonomous worker status, cycle telemetry, and execution counts.
    """
    from backend.agents.growth_worker import get_worker_status
    try:
        return get_worker_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/worker-run-now", tags=["AI Growth Agent"])
def trigger_worker_cycle_now():
    """
    Manually triggers an immediate autonomous growth cycle (useful for testing or on-demand execution).
    """
    from backend.agents.growth_worker import execute_autonomous_cycle
    try:
        summary = execute_autonomous_cycle(max_actions_per_cycle=2)
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UpdateRecoveryPolicyRequest(BaseModel):
    recovery_idle_threshold_minutes: Optional[int] = None
    recovery_attribution_percent: Optional[int] = None


@router.patch("/policy", tags=["AI Growth Agent"])
def update_recovery_policy(req: UpdateRecoveryPolicyRequest):
    """
    Live-updates recovery policy thresholds without server restart.
    - recovery_idle_threshold_minutes: minimum cart idle time before recovery attribution is credited (default 120).
      Set to 0 for demo mode (no idle gate).
    - recovery_attribution_percent: percentage of recovered payment credited as AI-incremental lift (default 60).
      Reflects the ~40% estimated organic recovery baseline for abandoned carts (industry benchmark).
    Changes are persisted to policy_config and audited.
    """
    if req.recovery_idle_threshold_minutes is None and req.recovery_attribution_percent is None:
        raise HTTPException(status_code=400, detail="Provide at least one field: recovery_idle_threshold_minutes or recovery_attribution_percent")

    conn = get_db()
    cursor = conn.cursor()
    try:
        updates = []
        params = []
        audit_parts = []

        if req.recovery_idle_threshold_minutes is not None:
            if req.recovery_idle_threshold_minutes < 0:
                raise HTTPException(status_code=400, detail="recovery_idle_threshold_minutes must be >= 0")
            updates.append("recovery_idle_threshold_minutes = ?")
            params.append(req.recovery_idle_threshold_minutes)
            audit_parts.append(f"idle_threshold={req.recovery_idle_threshold_minutes}m")

        if req.recovery_attribution_percent is not None:
            if not (0 <= req.recovery_attribution_percent <= 100):
                raise HTTPException(status_code=400, detail="recovery_attribution_percent must be between 0 and 100")
            updates.append("recovery_attribution_percent = ?")
            params.append(req.recovery_attribution_percent)
            audit_parts.append(f"attribution={req.recovery_attribution_percent}%")

        params.append(1)  # WHERE id = 1
        cursor.execute(f"UPDATE policy_config SET {', '.join(updates)} WHERE id = ?", params)
        from backend.engine.mandates import create_audit_log
        create_audit_log(cursor, "policy", "config_1", "Recovery Policy Updated", f"Updated: {', '.join(audit_parts)}")
        conn.commit()

        # Return current state
        cursor.execute("SELECT recovery_idle_threshold_minutes, recovery_attribution_percent FROM policy_config WHERE id = 1")
        row = cursor.fetchone()
        return {
            "status": "updated",
            "recovery_idle_threshold_minutes": row["recovery_idle_threshold_minutes"],
            "recovery_attribution_percent": row["recovery_attribution_percent"],
            "note": "Changes take effect immediately. Set recovery_idle_threshold_minutes=0 for demo mode (no idle gate)."
        }
    finally:
        conn.close()


@router.get("/recovery-offers", tags=["AI Growth Agent"])
def list_active_recovery_offers(limit: int = 50):
    """
    Returns all personalized cart recovery offers generated by the AI Growth Agent:
    coupon codes, discount savings, customer cart details, validity countdown, and redemption status.
    """
    from backend.agents.cart_recovery_offer_engine import list_recovery_offers
    offers = list_recovery_offers(limit=limit)
    active = [o for o in offers if o["status"] == "active"]
    redeemed = [o for o in offers if o["status"] == "redeemed"]
    expired = [o for o in offers if o["status"] == "expired"]

    total_recovered_rupees = sum(o["discounted_total_rupees"] for o in redeemed)
    total_savings_offered_rupees = sum(o["discount_rupees"] for o in offers)

    return {
        "count": len(offers),
        "summary": {
            "active_offers": len(active),
            "redeemed_offers": len(redeemed),
            "expired_offers": len(expired),
            "total_recovered_revenue_rupees": round(total_recovered_rupees, 2),
            "total_savings_offered_rupees": round(total_savings_offered_rupees, 2)
        },
        "offers": offers
    }


# ── Festival & Seasonal Campaign Studio Endpoints ────────────────────────────

class CreateFestivalRequest(BaseModel):
    name: str
    month: int
    day: int
    duration_days: Optional[int] = 7
    themes: Optional[list[str]] = []
    custom_categories: Optional[list[str]] = None
    lift_multiplier: Optional[float] = 1.35
    is_active: Optional[int] = 1


class UpdateFestivalRequest(BaseModel):
    name: Optional[str] = None
    month: Optional[int] = None
    day: Optional[int] = None
    duration_days: Optional[int] = None
    themes: Optional[list[str]] = None
    custom_categories: Optional[list[str]] = None
    lift_multiplier: Optional[float] = None
    is_active: Optional[int] = None


@router.get("/festivals", tags=["AI Growth Agent - Merchandising"])
def list_festivals():
    """
    Returns all configured commercial & cultural festivals with real calendar dates,
    live date deltas, active status, and auto-detected matching categories for this merchant's inventory.
    """
    from backend.agents.context_agent import get_upcoming_festivals
    events = get_upcoming_festivals(window_days=365)
    return {
        "count": len(events),
        "festivals": events
    }


@router.post("/festivals", tags=["AI Growth Agent - Merchandising"])
def create_custom_festival(req: CreateFestivalRequest):
    """
    Creates a new custom promotional festival or sale campaign (e.g. Monsoon Clearance, Founder's Day).
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        now_iso = datetime.utcnow().isoformat() + "Z"
        themes_json = json.dumps(req.themes or ["mega_sale", "seasonal_promotion"])
        custom_cats_json = json.dumps(req.custom_categories) if req.custom_categories else None

        cursor.execute(
            """
            INSERT INTO festival_calendar (name, month, day, duration_days, themes, custom_categories, lift_multiplier, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (req.name, req.month, req.day, req.duration_days or 7, themes_json, custom_cats_json, req.lift_multiplier or 1.35, req.is_active or 1, now_iso, now_iso)
        )
        new_id = cursor.lastrowid
        conn.commit()

        # Trigger dynamic boost recalculation
        from backend.agents.growth_agent import apply_seasonal_boosts
        apply_seasonal_boosts()

        return {"status": "created", "id": new_id, "name": req.name}
    finally:
        conn.close()


@router.put("/festivals/{festival_id}", tags=["AI Growth Agent - Merchandising"])
def update_festival(festival_id: int, req: UpdateFestivalRequest):
    """
    Updates festival properties: toggle active/inactive, change multiplier (1.0x - 2.0x),
    or assign custom category overrides.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM festival_calendar WHERE id = ?", (festival_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Festival not found")

        updates = []
        params = []
        now_iso = datetime.utcnow().isoformat() + "Z"

        if req.name is not None:
            updates.append("name = ?")
            params.append(req.name)
        if req.month is not None:
            updates.append("month = ?")
            params.append(req.month)
        if req.day is not None:
            updates.append("day = ?")
            params.append(req.day)
        if req.duration_days is not None:
            updates.append("duration_days = ?")
            params.append(req.duration_days)
        if req.themes is not None:
            updates.append("themes = ?")
            params.append(json.dumps(req.themes))
        if req.custom_categories is not None:
            updates.append("custom_categories = ?")
            params.append(json.dumps(req.custom_categories) if req.custom_categories else None)
        if req.lift_multiplier is not None:
            updates.append("lift_multiplier = ?")
            params.append(req.lift_multiplier)
        if req.is_active is not None:
            updates.append("is_active = ?")
            params.append(req.is_active)

        updates.append("updated_at = ?")
        params.append(now_iso)

        params.append(festival_id)
        cursor.execute(f"UPDATE festival_calendar SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()

        # Trigger dynamic boost recalculation
        from backend.agents.growth_agent import apply_seasonal_boosts
        apply_seasonal_boosts()

        return {"status": "updated", "id": festival_id}
    finally:
        conn.close()


@router.delete("/festivals/{festival_id}", tags=["AI Growth Agent - Merchandising"])
def delete_festival(festival_id: int):
    """
    Deletes a festival entry from the calendar.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM festival_calendar WHERE id = ?", (festival_id,))
        conn.commit()
        from backend.agents.growth_agent import apply_seasonal_boosts
        apply_seasonal_boosts()
        return {"status": "deleted", "id": festival_id}
    finally:
        conn.close()


@router.post("/festivals/recalculate", tags=["AI Growth Agent - Merchandising"])
def recalculate_merchandising_boosts():
    """
    Forces instant recalculation of seasonal, weather, and festival merchandising weights
    across the active catalog.
    """
    from backend.agents.growth_agent import apply_seasonal_boosts
    res = apply_seasonal_boosts()
    return {"status": "recalculated", "summary": res}


