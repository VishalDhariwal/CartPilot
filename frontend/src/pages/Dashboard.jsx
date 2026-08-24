import React, { useEffect, useState, useMemo } from 'react';
import {
  CheckCircle, XCircle, ShoppingBag, Banknote, RefreshCcw,
  FileText, Sparkles, AlertCircle, RotateCcw, Activity, Shield,
  ArrowUpRight, Clock, PackageCheck, Layers, ChevronDown, ChevronUp
} from 'lucide-react';

const BASE_URL = 'http://127.0.0.1:8000';

/* ─── Formatters ─────────────────────────────────────────────────────── */
function fmtTime(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('en-IN', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      day: '2-digit', month: 'short'
    });
  } catch (_) { return iso; }
}

function fmtRupees(paise) {
  if (paise == null) return '—';
  return `₹${(paise / 100).toFixed(0)}`;
}

function parseItems(itemsJson) {
  try {
    if (typeof itemsJson === 'string') return JSON.parse(itemsJson);
    return itemsJson || [];
  } catch (_) { return []; }
}

/* ─── Event Classification & Icons ───────────────────────────────────── */
function classifyEvent(event) {
  const e = event.toLowerCase();
  if (e.includes('blocked') || e.includes('failed') || e.includes('error'))
    return 'error';
  if (e.includes('approved') || e.includes('captured') || e.includes('succeeded') || e.includes('refunded'))
    return 'success';
  if (e.includes('upsell') || e.includes('growth') || e.includes('substitute'))
    return 'upsell';
  return 'info';
}

function TimelineDotIcon({ eventClass }) {
  if (eventClass === 'success') return <CheckCircle size={13} />;
  if (eventClass === 'error') return <XCircle size={13} />;
  if (eventClass === 'upsell') return <Sparkles size={12} />;
  return <FileText size={12} />;
}

/* ─── Reusable Telemetry KPI Tooltip Component (1.2s delay) ───────── */
function KpiTooltip({ title, category, description, formula, source, align }) {
  return (
    <div className={`kpi-hover-tooltip ${align ? `align-${align}` : ''}`}>
      <div className="kpi-tooltip-header">
        <div className="kpi-tooltip-title">{title}</div>
        {category && <span className="kpi-tooltip-badge">{category}</span>}
      </div>
      <div className="kpi-tooltip-desc">{description}</div>
      {formula && (
        <div className="kpi-tooltip-formula-box">
          <div className="kpi-tooltip-formula-label">CALCULATION / FORMULA</div>
          <code>{formula}</code>
        </div>
      )}
      {source && (
        <div className="kpi-tooltip-source">
          <span>Source:</span> <strong>{source}</strong>
        </div>
      )}
    </div>
  );
}

/* ─── Single Order Ledger Slip Component (Click to Expand) ─────────── */
function OrderLedgerCard({ order, defaultExpanded = false }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const { intent, carts, payments, logs } = order;

  const latestPayment = payments[payments.length - 1];
  const latestCart = carts[carts.length - 1];

  let statusType = 'pending';
  let statusLabel = 'Intent Logged';

  if (latestPayment) {
    const ps = latestPayment.status;
    if (ps === 'succeeded') {
      if (latestPayment.recovery_action === 'refunded') {
        statusType = 'refunded';
        statusLabel = 'Refunded Reversal';
      } else {
        statusType = 'completed';
        statusLabel = 'Settled & Captured ✓';
      }
    } else if (ps === 'failed') {
      statusType = 'blocked';
      statusLabel = 'Payment Failed';
    } else {
      statusType = 'pending';
      statusLabel = 'Awaiting Settlement';
    }
  } else if (latestCart) {
    if (latestCart.status === 'blocked') {
      statusType = 'blocked';
      statusLabel = 'Guardrail Intercepted';
    } else {
      statusType = 'pending';
      statusLabel = 'Cart Gated';
    }
  }

  // Parse items from the latest approved cart
  const approvedCart = carts.find(c => c.status === 'approved') || carts[carts.length - 1];
  const items = approvedCart ? parseItems(approvedCart.items) : [];

  return (
    <div className={`ledger-card ${expanded ? 'expanded' : 'collapsed'}`}>
      {/* Clickable Header Headline */}
      <div
        className="ledger-card-header"
        onClick={() => setExpanded(!expanded)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setExpanded(!expanded); }}
        title={expanded ? "Click to collapse details" : "Click to expand audit timeline & items"}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px', flexWrap: 'wrap' }}>
            <div className="ledger-goal-title">{intent.goal || intent.raw_request}</div>
            <span className={`channel-badge ${intent.channel === 'mcp_agent' ? 'mcp' : 'web'}`}>
              {intent.channel === 'mcp_agent' ? '🤖 MCP External Agent' : '🌐 Buyer Web Chat'}
            </span>
          </div>
          <div className="ledger-submeta">
            <span>ID: <strong>{intent.id.slice(-8).toUpperCase()}</strong></span>
            <span>•</span>
            <span>Spend Cap: {fmtRupees(intent.spend_cap_paise)}</span>
            {latestCart && (
              <>
                <span>•</span>
                <span>Final Value: <strong>{fmtRupees(latestCart.total_paise)}</strong></span>
              </>
            )}
            {items.length > 0 && (
              <>
                <span>•</span>
                <span>{items.length} {items.length === 1 ? 'item' : 'items'}</span>
              </>
            )}
            <span>•</span>
            <span>{logs.length} audit {logs.length === 1 ? 'event' : 'events'}</span>
            <span>•</span>
            <span>{fmtTime(intent.created_at)}</span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
          <div className={`status-pill ${statusType}`}>
            {statusType === 'completed' && <CheckCircle size={12} />}
            {statusType === 'blocked' && <Shield size={12} />}
            {statusType === 'refunded' && <RotateCcw size={12} />}
            <span>{statusLabel}</span>
          </div>

          <div className="ledger-expand-chevron">
            {expanded ? <ChevronUp size={16} color="var(--ink-secondary)" /> : <ChevronDown size={16} color="var(--ink-secondary)" />}
          </div>
        </div>
      </div>

      {/* Expanded Details Body */}
      {expanded && (
        <div className="ledger-card-body">
          {/* Items Strip with Real Image Thumbnails */}
          {items.length > 0 && (
            <div className="ledger-items-strip">
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--ink-muted)', flexShrink: 0 }}>
                ITEMS ({items.length}):
              </span>
              {items.map((item, idx) => (
                <div key={item.sku + idx} className="ledger-item-chip">
                  {item.image_url && (
                    <img
                      src={item.image_url}
                      alt={item.name}
                      className="ledger-item-thumb"
                      onError={(e) => { e.target.style.display = 'none'; }}
                    />
                  )}
                  <span className="ledger-item-title" title={item.name || item.sku}>
                    {item.name || item.sku}
                  </span>
                  <span className="ledger-item-amt">
                    {item.qty > 1 ? `×${item.qty} ` : ''}{fmtRupees(item.price_paise * (item.qty || 1))}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Razorpay Mandate strip */}
          {latestPayment && (
            <div className="ledger-mandate-strip">
              <span>Razorpay Order: <strong>{latestPayment.razorpay_order_id || '—'}</strong></span>
              {latestPayment.razorpay_payment_id && (
                <span>Payment ID: <strong>{latestPayment.razorpay_payment_id}</strong></span>
              )}
              {latestPayment.failure_reason && (
                <span style={{ color: 'var(--alert-brick)' }}>
                  Failure: {latestPayment.failure_reason}
                </span>
              )}
              {latestPayment.recovery_action && latestPayment.recovery_action !== 'refunded' && (
                <span style={{ color: '#8C5B14' }}>
                  Recovery Advice: {latestPayment.recovery_action}
                </span>
              )}
            </div>
          )}

          {/* Audit Timeline */}
          <div className="ledger-timeline">
            {logs.map((log) => {
              const ec = classifyEvent(log.event);
              return (
                <div key={log.id} className="timeline-row">
                  <div className={`timeline-dot ${ec}`}>
                    <TimelineDotIcon eventClass={ec} />
                  </div>
                  <div className="timeline-body">
                    <div className="timeline-event-name">
                      <span>{log.event}</span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--ink-muted)', fontWeight: 400 }}>
                        ref: {log.ref_id.slice(-8)}
                      </span>
                    </div>
                    <div className="timeline-detail-text">{log.detail}</div>
                    <div className="timeline-timestamp">{fmtTime(log.created_at)}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Main Dashboard Page ────────────────────────────────────────────── */
export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [upsellStats, setUpsellStats] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(new Date());
  const [expandAll, setExpandAll] = useState(false);

  const fetchUpsellStats = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/upsell-stats`);
      const json = await res.json();
      setUpsellStats(json);
    } catch (_) {}
  };

  const fetchDashboard = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/dashboard`);
      const json = await res.json();
      setData(json);
      setLastUpdated(new Date());
    } catch (e) {
      console.error('Dashboard fetch error:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboard();
    fetchUpsellStats();
    const interval = setInterval(() => {
      fetchDashboard();
      fetchUpsellStats();
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  // Group everything by intent (Newest first at top)
  const orders = useMemo(() => {
    if (!data) return [];
    return data.intents.map(intent => {
      const carts = data.carts.filter(c => c.intent_id === intent.id);
      const cartIds = carts.map(c => c.id);
      const payments = data.payments.filter(p => cartIds.includes(p.cart_id));
      const payIds = payments.map(p => p.id);
      const refIds = [intent.id, ...cartIds, ...payIds];
      const logs = data.audit_logs
        .filter(l => refIds.includes(l.ref_id))
        .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0)); // Newest logs first at top
      return { intent, carts, payments, logs };
    }).sort((a, b) => new Date(b.intent.created_at || 0) - new Date(a.intent.created_at || 0)); // Newest orders first at top
  }, [data]);


  // Aggregate stats
  const stats = useMemo(() => {
    if (!orders.length) {
      return { total: 0, totalPaise: 0, completed: 0, blocked: 0, failed: 0, refunded: 0 };
    }
    let completed = 0, blocked = 0, failed = 0, refunded = 0, totalPaise = 0;
    let mcpCount = 0, webCount = 0;
    orders.forEach(o => {
      const lp = o.payments[o.payments.length - 1];
      const lc = o.carts[o.carts.length - 1];
      if (o.intent.channel === 'mcp_agent') {
        mcpCount++;
      } else {
        webCount++;
      }
      if (lc?.status === 'approved') {
        totalPaise += (lc.total_paise || 0);
      }
      if (lp?.status === 'succeeded' && lp?.recovery_action === 'refunded') {
        refunded++;
      } else if (lp?.status === 'succeeded') {
        completed++;
      } else if (lp?.status === 'failed') {
        failed++;
      }
      
      const isBlocked = o.carts.some(c => c.status === 'blocked') ||
        o.logs.some(l => l.event.toLowerCase().includes('blocked') || l.event.toLowerCase().includes('intercepted'));
      if (isBlocked) {
        blocked++;
      }
    });
    return { total: orders.length, totalPaise, completed, blocked, failed, refunded, mcpCount, webCount };
  }, [orders]);

  // Filtered orders
  const filteredOrders = useMemo(() => {
    if (filter === 'all') return orders;
    if (filter === 'completed') {
      return orders.filter(o => o.payments.some(p => p.status === 'succeeded' && p.recovery_action !== 'refunded'));
    }
    if (filter === 'blocked') {
      return orders.filter(o => o.carts.some(c => c.status === 'blocked') ||
        o.logs.some(l => l.event.toLowerCase().includes('blocked') || l.event.toLowerCase().includes('intercepted')));
    }
    if (filter === 'refunded') {
      return orders.filter(o => o.payments.some(p => p.recovery_action === 'refunded'));
    }
    if (filter === 'upsell') {
      return orders.filter(o => o.logs.some(l => l.event.includes('Upsell Accepted') || l.event.includes('Substitute Accepted') || l.event.includes('Post-Purchase Add-on Created')));
    }
    if (filter === 'mcp') {
      return orders.filter(o => o.intent.channel === 'mcp_agent');
    }
    if (filter === 'web') {
      return orders.filter(o => o.intent.channel !== 'mcp_agent');
    }
    return orders;
  }, [orders, filter]);


  return (
    <div className="dashboard-layout">
      {/* ── Header ── */}
      <div className="dashboard-hero">
        <div>
          <div className="dashboard-title">Merchant Ledger & Audit Trail</div>
          <div className="dashboard-subtitle">
            Immutable timeline of AI buyer intents, guardrail policy evaluations, basket upsells, and Razorpay transactions.
          </div>
        </div>

        <button className="btn-refresh-dashboard" onClick={() => { fetchDashboard(); fetchUpsellStats(); }}>
          <RefreshCcw size={13} className={loading ? 'animate-spin' : ''} />
          <span>Synced {lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
        </button>
      </div>

      {/* ── KPI Summary Cards ── */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-header">
            <span>Gross Order Volume</span>
            <Banknote size={15} color="var(--ink-secondary)" />
          </div>
          <div className="kpi-value">₹{(stats.totalPaise / 100).toFixed(0)}</div>
          <div className="kpi-badge">
            <span>{stats.total} total agent intent mandates</span>
          </div>

          <KpiTooltip
            title="Gross Order Intent Volume (GMV)"
            category="Intent Volume"
            description="Total gross rupee value of all approved shopping carts initiated by human shoppers and autonomous MCP agents."
            formula="∑(cart_mandates.total_paise WHERE status='approved')"
            source="cart_mandates • intent_mandates"
            align="left"
          />
        </div>

        <div className="kpi-card">
          <div className="kpi-header">
            <span>AI Growth & Upsells</span>
            <Sparkles size={15} color="var(--ink-secondary)" />
          </div>
          <div className="kpi-value">
            {upsellStats?.total_revenue_lift_rupees != null && upsellStats.total_revenue_lift_rupees > 0
              ? `+₹${Math.round(upsellStats.total_revenue_lift_rupees).toLocaleString('en-IN')}`
              : '+₹0'}
          </div>
          <div className="kpi-badge">
            <span>{upsellStats?.accepted_count || 0} upsells picked ({upsellStats?.conversion_rate_pct || 0}% attach)</span>
          </div>

          <KpiTooltip
            title="Incremental AI Revenue Lift"
            category="AI Growth Attribution"
            description="Net additional basket revenue generated directly by Item2Vec and market basket cross-sell recommendations."
            formula="∑(accepted_upsell_price_paise × qty)"
            source="upsell_events • basket_pairs"
          />
        </div>

        <div className="kpi-card">
          <div className="kpi-header">
            <span>Settled Orders</span>
            <CheckCircle size={15} color="var(--ink-secondary)" />
          </div>
          <div className="kpi-value">
            {stats.completed}
          </div>
          <div className="kpi-badge">
            <span>Razorpay test payments captured ✓</span>
          </div>

          <KpiTooltip
            title="Settled & Captured Payments"
            category="Payment Settlement"
            description="Successfully completed transactions verified via HMAC signature on Razorpay capture webhooks."
            formula="COUNT(payment_mandates WHERE status='succeeded')"
            source="payment_mandates • Razorpay Webhook"
          />
        </div>

        <div className="kpi-card">
          <div className="kpi-header">
            <span>Guardrail Interceptions</span>
            <Shield size={15} color="var(--ink-secondary)" />
          </div>
          <div className="kpi-value">
            {stats.blocked}
          </div>
          <div className="kpi-badge">
            <span>Spend cap & policy breaches prevented</span>
          </div>

          <KpiTooltip
            title="Guardrail Interceptions"
            category="Deterministic Safety"
            description="High-risk transactions mathematically blocked for spend cap overruns, category restrictions, or out-of-stock items."
            formula="COUNT(cart_mandates WHERE status='blocked')"
            source="guardrail_policy • audit_log"
          />
        </div>

        <div className="kpi-card">
          <div className="kpi-header">
            <span>Resolution Reversals</span>
            <RotateCcw size={15} color="var(--ink-secondary)" />
          </div>
          <div className="kpi-value">
            {stats.refunded}
          </div>
          <div className="kpi-badge">
            <span>Refunded via AI Resolution Agent</span>
          </div>

          <KpiTooltip
            title="Resolution Reversals (Refunds)"
            category="Autonomous Resolution"
            description="Customer orders safely cancelled and refunded through the LLM Resolution Agent policy verification."
            formula="COUNT(payment_mandates WHERE recovery_action='refunded')"
            source="resolution_mandates • Razorpay Refunds"
            align="right"
          />
        </div>
      </div>

      {/* ── Filter Bar ── */}
      <div className="filter-bar">
        <button
          className={`filter-pill ${filter === 'all' ? 'active' : ''}`}
          onClick={() => setFilter('all')}
        >
          All Orders ({orders.length})
        </button>
        <button
          className={`filter-pill ${filter === 'completed' ? 'active' : ''}`}
          onClick={() => setFilter('completed')}
        >
          Settled ({stats.completed})
        </button>
        <button
          className={`filter-pill ${filter === 'upsell' ? 'active' : ''}`}
          onClick={() => setFilter('upsell')}
        >
          ✨ AI Growth ({upsellStats?.accepted_count || 0})
        </button>
        <button
          className={`filter-pill ${filter === 'blocked' ? 'active' : ''}`}
          onClick={() => setFilter('blocked')}
        >
          🚫 Guardrail Intercepted ({stats.blocked})
        </button>
        <button
          className={`filter-pill ${filter === 'refunded' ? 'active' : ''}`}
          onClick={() => setFilter('refunded')}
        >
          ↩ Refunded ({stats.refunded})
        </button>
        <button
          className={`filter-pill ${filter === 'mcp' ? 'active' : ''}`}
          onClick={() => setFilter('mcp')}
          style={{ borderColor: filter === 'mcp' ? '#6B46C1' : undefined, color: filter === 'mcp' ? '#FFF' : '#6B46C1', background: filter === 'mcp' ? '#6B46C1' : '#F3E8FF' }}
        >
          🤖 MCP Agent ({stats.mcpCount || 0})
        </button>
        <button
          className={`filter-pill ${filter === 'web' ? 'active' : ''}`}
          onClick={() => setFilter('web')}
        >
          🌐 Web Chat ({stats.webCount || 0})
        </button>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center' }}>
          <button
            className="filter-pill"
            style={{ fontWeight: 500, fontSize: '0.78rem' }}
            onClick={() => setExpandAll(!expandAll)}
          >
            {expandAll ? 'Collapse All' : 'Expand All'}
          </button>
        </div>
      </div>

      {/* ── Order Ledger List ── */}
      {filteredOrders.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '3rem 1rem', background: '#FFF',
          border: '1px dashed var(--hairline-dark)', borderRadius: 'var(--radius-md)'
        }}>
          <p style={{ fontFamily: 'var(--font-serif)', fontSize: '1.1rem', color: 'var(--ink-secondary)' }}>
            No orders found matching this filter.
          </p>
        </div>
      ) : (
        <div className="ledger-orders-stack">
          {filteredOrders.map(order => (
            <OrderLedgerCard
              key={`${order.intent.id}_${expandAll}`}
              order={order}
              defaultExpanded={expandAll}
            />
          ))}
        </div>
      )}
    </div>
  );
}
