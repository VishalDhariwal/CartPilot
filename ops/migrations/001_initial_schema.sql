-- ============================================================================
-- CartPilot Enterprise PostgreSQL Schema (Azure Flexible Server)
-- Migration: 001_initial_schema.sql
-- ============================================================================

-- Catalog table with metadata and vector embeddings
CREATE TABLE IF NOT EXISTS catalog (
    sku VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    price_paise BIGINT NOT NULL,
    stock INTEGER NOT NULL,
    category VARCHAR(128) NOT NULL,
    merchant VARCHAR(128) NOT NULL,
    boosted INTEGER NOT NULL DEFAULT 0,
    image_url TEXT,
    description TEXT,
    tags TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    embedding TEXT
);

CREATE INDEX IF NOT EXISTS idx_catalog_category ON catalog(category);
CREATE INDEX IF NOT EXISTS idx_catalog_merchant ON catalog(merchant);

-- Merchant Deterministic Guardrail Policy Configuration
CREATE TABLE IF NOT EXISTS policy_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    spend_cap_paise BIGINT NOT NULL,
    allowed_categories TEXT NOT NULL,
    autonomy_threshold_paise BIGINT NOT NULL DEFAULT 500000
);

-- Intent Mandates (Immutable capture of buyer procurement requests)
CREATE TABLE IF NOT EXISTS intent_mandates (
    id VARCHAR(64) PRIMARY KEY,
    raw_request TEXT NOT NULL,
    goal TEXT NOT NULL,
    spend_cap_paise BIGINT NOT NULL,
    channel VARCHAR(32) NOT NULL DEFAULT 'web_chat',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_intent_mandates_created ON intent_mandates(created_at DESC);

-- Cart Mandates (Proposals built by LangGraph buyer journey)
CREATE TABLE IF NOT EXISTS cart_mandates (
    id VARCHAR(64) PRIMARY KEY,
    intent_id VARCHAR(64) NOT NULL REFERENCES intent_mandates(id) ON DELETE CASCADE,
    items JSONB NOT NULL,
    total_paise BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL,
    reason TEXT NOT NULL,
    reversible INTEGER NOT NULL DEFAULT 1,
    order_status VARCHAR(32) NOT NULL DEFAULT 'CREATED',
    cancellation_status VARCHAR(32) NOT NULL DEFAULT 'NONE',
    fulfillment_status VARCHAR(32) NOT NULL DEFAULT 'UNFULFILLED',
    return_status VARCHAR(32) NOT NULL DEFAULT 'NONE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cart_mandates_intent ON cart_mandates(intent_id);
CREATE INDEX IF NOT EXISTS idx_cart_mandates_status ON cart_mandates(status);
CREATE INDEX IF NOT EXISTS idx_cart_mandates_order_status ON cart_mandates(order_status);

-- Payment Mandates (Authoritative Razorpay settlement records)
CREATE TABLE IF NOT EXISTS payment_mandates (
    id VARCHAR(64) PRIMARY KEY,
    cart_id VARCHAR(64) NOT NULL REFERENCES cart_mandates(id) ON DELETE CASCADE,
    razorpay_order_id VARCHAR(64),
    razorpay_payment_id VARCHAR(64),
    amount_paise BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL,
    failure_reason TEXT,
    recovery_action VARCHAR(64),
    refund_status VARCHAR(32) NOT NULL DEFAULT 'NONE',
    refund_amount_paise BIGINT NOT NULL DEFAULT 0,
    refunded_amount_paise BIGINT NOT NULL DEFAULT 0,
    razorpay_refund_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payment_mandates_cart ON payment_mandates(cart_id);
CREATE INDEX IF NOT EXISTS idx_payment_mandates_status ON payment_mandates(status);
CREATE INDEX IF NOT EXISTS idx_payment_mandates_refund_status ON payment_mandates(refund_status);

-- Post-Purchase Refunds Ledger
CREATE TABLE IF NOT EXISTS refunds (
    id VARCHAR(64) PRIMARY KEY,
    payment_id VARCHAR(64) NOT NULL REFERENCES payment_mandates(id) ON DELETE CASCADE,
    cart_id VARCHAR(64) NOT NULL REFERENCES cart_mandates(id) ON DELETE CASCADE,
    requested_amount_paise BIGINT NOT NULL,
    processed_amount_paise BIGINT NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'REFUND_REQUESTED',
    razorpay_refund_id VARCHAR(64),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_refunds_payment ON refunds(payment_id);

-- Immutable Audit Log
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    ref_type VARCHAR(64) NOT NULL,
    ref_id VARCHAR(64) NOT NULL,
    event VARCHAR(128) NOT NULL,
    detail TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_ref ON audit_log(ref_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_event ON audit_log(event);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at DESC);

-- Historical Orders for Item2Vec and Market Basket Analysis
CREATE TABLE IF NOT EXISTS historical_orders (
    order_id VARCHAR(64) PRIMARY KEY,
    items JSONB NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Market Basket Association Pairs (4-Tier RecSys)
CREATE TABLE IF NOT EXISTS basket_pairs (
    sku_a VARCHAR(64) NOT NULL,
    sku_b VARCHAR(64) NOT NULL,
    lift DOUBLE PRECISION,
    support DOUBLE PRECISION,
    confidence DOUBLE PRECISION,
    source VARCHAR(64) NOT NULL DEFAULT 'ai_suggested',
    reasoning TEXT,
    co_occurrence_count INTEGER DEFAULT 0,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    muted INTEGER NOT NULL DEFAULT 0,
    retired INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (sku_a, sku_b)
);

CREATE INDEX IF NOT EXISTS idx_basket_pairs_sku_a ON basket_pairs(sku_a);

-- Cross-Device Chat Sessions
CREATE TABLE IF NOT EXISTS chat_sessions (
    id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    session_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Upsell Events Attribution Table
CREATE TABLE IF NOT EXISTS upsell_events (
    id BIGSERIAL PRIMARY KEY,
    cart_id VARCHAR(64) NOT NULL,
    suggested_sku VARCHAR(64) NOT NULL,
    accepted INTEGER NOT NULL,
    cart_total_before_paise BIGINT NOT NULL,
    cart_total_after_paise BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_upsell_events_cart ON upsell_events(cart_id);

-- Category Compatibility Graph
CREATE TABLE IF NOT EXISTS category_compatibility (
    category_a VARCHAR(128) NOT NULL,
    category_b VARCHAR(128) NOT NULL,
    reasoning TEXT NOT NULL,
    editable INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (category_a, category_b)
);

-- AI Growth Agent: Actions & Opportunities Ledger
CREATE TABLE IF NOT EXISTS growth_actions (
    id VARCHAR(64) PRIMARY KEY,
    action_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'detected',
    opportunity_type VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    explanation TEXT NOT NULL,
    affected_ref VARCHAR(64),
    est_revenue_paise BIGINT DEFAULT 0,
    confidence DOUBLE PRECISION DEFAULT 0.0,
    recommended_action TEXT,
    execution_ref VARCHAR(64),
    mode VARCHAR(32) DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    executed_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_growth_actions_status ON growth_actions(status);

-- AI Growth Agent: Verified Revenue Attribution Outcomes
CREATE TABLE IF NOT EXISTS growth_outcomes (
    id VARCHAR(64) PRIMARY KEY,
    action_id VARCHAR(64),
    outcome_type VARCHAR(32) NOT NULL,
    before_paise BIGINT DEFAULT 0,
    after_paise BIGINT DEFAULT 0,
    incremental_paise BIGINT DEFAULT 0,
    revenue_type VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_growth_outcomes_action ON growth_outcomes(action_id);
CREATE INDEX IF NOT EXISTS idx_growth_outcomes_type ON growth_outcomes(outcome_type);

-- AI Growth Agent: Managed Promotion Experiments
CREATE TABLE IF NOT EXISTS promotion_experiments (
    id VARCHAR(64) PRIMARY KEY,
    sku VARCHAR(64) NOT NULL REFERENCES catalog(sku),
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    action_id VARCHAR(64),
    baseline_stock INTEGER NOT NULL,
    baseline_velocity_daily DOUBLE PRECISION NOT NULL,
    baseline_days_of_inventory DOUBLE PRECISION NOT NULL,
    baseline_orders_30d INTEGER NOT NULL,
    buyer_relevance_score DOUBLE PRECISION NOT NULL,
    experiment_horizon_days INTEGER NOT NULL DEFAULT 14,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ends_at TIMESTAMPTZ NOT NULL,
    cooldown_until TIMESTAMPTZ NOT NULL,
    current_stock INTEGER,
    units_liquidated INTEGER DEFAULT 0,
    orders_during_experiment INTEGER DEFAULT 0,
    realized_revenue_paise BIGINT DEFAULT 0,
    outcome_status VARCHAR(32),
    control_skus JSONB DEFAULT '[]'::jsonb,
    treatment_baseline_velocity DOUBLE PRECISION DEFAULT 0.0,
    control_baseline_velocity DOUBLE PRECISION DEFAULT 0.0,
    treatment_current_velocity DOUBLE PRECISION DEFAULT 0.0,
    control_current_velocity DOUBLE PRECISION DEFAULT 0.0,
    treatment_lift DOUBLE PRECISION,
    control_lift DOUBLE PRECISION,
    matched_control_lift_estimate DOUBLE PRECISION,
    zero_baseline_treatment INTEGER DEFAULT 0,
    opportunity_reason VARCHAR(128) DEFAULT 'INVENTORY_RISK_WITH_DEMAND',
    product_state VARCHAR(128) DEFAULT 'UNDER_DISCOVERED',
    stage1_score DOUBLE PRECISION DEFAULT 0.0,
    stage2_llm_decision VARCHAR(64) DEFAULT 'ACCEPT_FALLBACK',
    stage2_llm_reasoning TEXT,
    final_suitability_score DOUBLE PRECISION DEFAULT 0.0,
    decision_confidence DOUBLE PRECISION DEFAULT 0.5,
    decision_confidence_reason TEXT,
    probability_source VARCHAR(64) DEFAULT 'cold_start_heuristic',
    is_empirical_probability INTEGER DEFAULT 0,
    early_killed INTEGER DEFAULT 0,
    early_kill_reason TEXT,
    merchant_decision VARCHAR(32) DEFAULT 'PENDING',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_promotion_experiments_sku ON promotion_experiments(sku);
CREATE INDEX IF NOT EXISTS idx_promotion_experiments_status ON promotion_experiments(status);
