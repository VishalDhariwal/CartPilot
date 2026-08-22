import { useEffect, useState, useMemo } from 'react';
import {
  CheckCircle, XCircle, ShoppingBag, Banknote, RefreshCcw,
  FileText, Sparkles, AlertCircle, RotateCcw, Activity
} from 'lucide-react';

const BASE_URL = 'http://127.0.0.1:8000';

/* ─── Helpers ──────────────────────────────────────────────────────── */
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

/* ─── Event classification ─────────────────────────────────────────── */
function classifyEvent(event) {
  const e = event.toLowerCase();
  if (e.includes('blocked') || e.includes('failed') || e.includes('error'))
    return 'error';
  if (e.includes('approved') || e.includes('captured') || e.includes('succeeded') || e.includes('refunded'))
    return 'success';
  if (e.includes('upsell offered') || e.includes('upsell accepted'))
    return 'upsell';
  if (e.includes('upsell declined') || e.includes('upsell blocked'))
    return 'warning';
  return 'info';
}

function TlIcon({ eventClass }) {
  const cls = `timeline-icon tl-${eventClass}`;
  const size = 15;
  return (
    <div className={cls}>
      {eventClass === 'success' ? <CheckCircle size={size} /> :
       eventClass === 'error'   ? <XCircle size={size} /> :
       eventClass === 'upsell'  ? <Sparkles size={size} /> :
       eventClass === 'warning' ? <AlertCircle size={size} /> :
       <FileText size={size} />}
    </div>
  );
}

/* ─── Order Card ─────────────────────────────────────────────────────── */
function OrderCard({ order }) {
  const { intent, carts, payments, logs } = order;

  // Determine overall status
  const latestPayment = payments[payments.length - 1];
  const latestCart = carts[carts.length - 1];

  let cardClass = 'order-pending';
  let headerStatus = 'Intent Logged';
  let headerStatusClass = 'status-info';

  if (latestPayment) {
    const ps = latestPayment.status;
    if (ps === 'succeeded') {
      if (latestPayment.recovery_action === 'refunded') {
        cardClass = 'order-refunded'; headerStatus = 'Refunded'; headerStatusClass = 'status-info';
      } else {
        cardClass = 'order-success'; headerStatus = 'Completed'; headerStatusClass = 'status-success';
      }
    } else if (ps === 'failed') {
      cardClass = 'order-failed'; headerStatus = 'Payment Failed'; headerStatusClass = 'status-error';
    } else {
      cardClass = 'order-pending'; headerStatus = 'Awaiting Payment'; headerStatusClass = 'status-warning';
    }
  } else if (latestCart) {
    if (latestCart.status === 'blocked') {
      cardClass = 'order-blocked'; headerStatus = 'Blocked by Guardrail'; headerStatusClass = 'status-error';
    } else {
      cardClass = 'order-pending'; headerStatus = 'Pending Payment'; headerStatusClass = 'status-warning';
    }
  }

  // Parse cart items from the last approved cart
  const approvedCart = carts.find(c => c.status === 'approved') || carts[0];
  const items = approvedCart ? parseItems(approvedCart.items) : [];

  return (
    <div className={`order-card ${cardClass}`}>
      {/* Header */}
      <div className="order-card-header">
        <div>
          <div className="order-goal">{intent.goal}</div>
          <div className="order-meta">
            {intent.id.slice(0, 24)}… &nbsp;·&nbsp; Cap: {fmtRupees(intent.spend_cap_paise)}
            {latestCart && ` · Total: ${fmtRupees(latestCart.total_paise)}`}
          </div>
        </div>
        <span className={`status-badge ${headerStatusClass}`}>
          {headerStatus}
        </span>
      </div>

      {/* Cart items preview */}
      {items.length > 0 && (
        <div className="order-items-preview">
          <ShoppingBag size={13} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
          {items.map((item, i) => (
            <span key={i} className="item-chip">
              {item.sku} × {item.qty} — {fmtRupees(item.price_paise * item.qty)}
            </span>
          ))}
        </div>
      )}

      {/* Payment info row */}
      {latestPayment && (
        <div style={{
          padding: '0.5rem 1.5rem',
          borderBottom: '1px solid var(--border-color)',
          fontSize: '0.78rem',
          color: 'var(--text-muted)',
          display: 'flex',
          gap: '1.5rem',
          flexWrap: 'wrap'
        }}>
          <span><Banknote size={11} style={{ display: 'inline', marginRight: 4 }} />
            {latestPayment.razorpay_order_id || '—'}
          </span>
          {latestPayment.razorpay_payment_id && (
            <span>Payment ID: {latestPayment.razorpay_payment_id}</span>
          )}
          {latestPayment.failure_reason && (
            <span style={{ color: 'var(--color-error)' }}>
              Failure: {latestPayment.failure_reason}
            </span>
          )}
          {latestPayment.recovery_action && latestPayment.recovery_action !== 'refunded' && (
            <span style={{ color: 'var(--color-warning)' }}>
              Recovery: {latestPayment.recovery_action.slice(0, 80)}{latestPayment.recovery_action.length > 80 ? '…' : ''}
            </span>
          )}
        </div>
      )}

      {/* Audit timeline */}
      <div className="timeline">
        {logs.map(log => {
          const ec = classifyEvent(log.event);
          return (
            <div key={log.id} className="timeline-item">
              <TlIcon eventClass={ec} />
              <div className="timeline-content">
                <div className="timeline-event" style={{
                  color: ec === 'error' ? 'var(--color-error)'
                    : ec === 'success' ? 'var(--color-success)'
                    : ec === 'upsell'  ? 'var(--color-upsell)'
                    : ec === 'warning' ? 'var(--color-warning)'
                    : 'var(--text-main)'
                }}>
                  {log.event}
                </div>
                <div className="timeline-detail">{log.detail}</div>
                <div className="timeline-time">{fmtTime(log.created_at)}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Main Dashboard ─────────────────────────────────────────────────── */
export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [upsellStats, setUpsellStats] = useState(null);

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
    }, 5000);
    return () => clearInterval(interval);
  }, []);


  // Group everything by intent
  const orders = useMemo(() => {
    if (!data) return [];
    return data.intents.map(intent => {
      const carts = data.carts.filter(c => c.intent_id === intent.id);
      const cartIds = carts.map(c => c.id);
      const payments = data.payments.filter(p => cartIds.includes(p.cart_id));
      const payIds = payments.map(p => p.id);
      const refIds = [intent.id, ...cartIds, ...payIds];
      const logs = data.audit_logs.filter(l => refIds.includes(l.ref_id));
      return { intent, carts, payments, logs };
    });
  }, [data]);

  // Stats
  const stats = useMemo(() => {
    if (!orders.length) return { total: 0, completed: 0, blocked: 0, failed: 0, refunded: 0 };
    let completed = 0, blocked = 0, failed = 0, refunded = 0;
    orders.forEach(o => {
      const lp = o.payments[o.payments.length - 1];
      const lc = o.carts[o.carts.length - 1];
      if (lp?.status === 'succeeded' && lp?.recovery_action === 'refunded') refunded++;
      else if (lp?.status === 'succeeded') completed++;
      else if (lp?.status === 'failed') failed++;
      else if (lc?.status === 'blocked') blocked++;
    });
    return { total: orders.length, completed, blocked, failed, refunded };
  }, [orders]);

  // Filter
  const filteredOrders = useMemo(() => {
    if (filter === 'all') return orders;
    return orders.filter(o => {
      const lp = o.payments[o.payments.length - 1];
      const lc = o.carts[o.carts.length - 1];
      if (filter === 'completed') return lp?.status === 'succeeded' && lp?.recovery_action !== 'refunded';
      if (filter === 'blocked')   return !lp && lc?.status === 'blocked';
      if (filter === 'failed')    return lp?.status === 'failed';
      if (filter === 'refunded')  return lp?.recovery_action === 'refunded';
      return true;
    });
  }, [orders, filter]);

  if (loading && !data) {
    return (
      <div className="dashboard-page">
        <div className="empty-state">
          <div className="empty-state-icon"><Activity /></div>
          <div>Loading audit trail…</div>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-page">
      {/* Header */}
      <div className="dashboard-header">
        <div>
          <h1 className="dashboard-title">Mandate Audit Dashboard</h1>
          <div className="dashboard-subtitle">
            Every money action — explained, bounded, and gated.
          </div>
        </div>
        <button
          id="btn-refresh-dashboard"
          className="btn btn-ghost btn-sm"
          onClick={fetchDashboard}
        >
          <RefreshCcw size={14} /> Refresh
        </button>
      </div>

      {/* Stats bar */}
      <div className="stats-bar">
        <div className="stat-card">
          <span className="stat-value" style={{ color: 'var(--text-main)' }}>{stats.total}</span>
          <span className="stat-label">Total Orders</span>
        </div>
        <div className="stat-card">
          <span className="stat-value" style={{ color: 'var(--color-success)' }}>{stats.completed}</span>
          <span className="stat-label">Completed</span>
        </div>
        <div className="stat-card">
          <span className="stat-value" style={{ color: 'var(--color-error)' }}>
            {stats.blocked + stats.failed}
          </span>
          <span className="stat-label">Blocked / Failed</span>
        </div>
        <div className="stat-card">
          <span className="stat-value" style={{ color: 'var(--color-refund)' }}>{stats.refunded}</span>
          <span className="stat-label">Refunded</span>
        </div>
      </div>

      {/* Growth Metrics card */}
      {upsellStats && upsellStats.total_offered > 0 && (
        <div style={{
          marginBottom: '1.5rem',
          padding: '1rem 1.5rem',
          borderRadius: 'var(--radius-md)',
          background: 'var(--color-upsell-bg)',
          border: '1px solid var(--color-upsell-border)',
          display: 'flex',
          gap: '2rem',
          flexWrap: 'wrap',
          alignItems: 'center'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem',
            color: 'var(--color-upsell)', fontWeight: 700, fontSize: '0.85rem',
            textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            <Sparkles size={15} /> Growth Metrics
          </div>
          <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap', flex: 1 }}>
            <div>
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--color-upsell)' }}>
                {upsellStats.acceptance_rate_pct}%
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                Acceptance Rate
              </div>
            </div>
            <div>
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--text-main)' }}>
                {upsellStats.total_offered}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                Offers Made
              </div>
            </div>
            <div>
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--color-success)' }}>
                {upsellStats.total_accepted}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                Accepted
              </div>
            </div>
            {upsellStats.avg_uplift_rupees > 0 && (
              <div>
                <div style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--color-success)' }}>
                  ₹{upsellStats.avg_uplift_rupees}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                  Avg AOV Uplift
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Filter bar */}
      <div className="filter-bar">
        {['all', 'completed', 'blocked', 'failed', 'refunded'].map(f => (
          <button
            key={f}
            id={`filter-${f}`}
            className={`filter-chip ${filter === f ? 'active' : ''}`}
            onClick={() => setFilter(f)}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
            {f === 'all' ? ` (${stats.total})`
              : f === 'completed' ? ` (${stats.completed})`
              : f === 'blocked' ? ` (${stats.blocked})`
              : f === 'failed' ? ` (${stats.failed})`
              : f === 'refunded' ? ` (${stats.refunded})` : ''}
          </button>
        ))}
      </div>

      {/* Order list */}
      {filteredOrders.length === 0 ? (
        <div className="empty-state glass" style={{ padding: '3rem', marginTop: '1rem' }}>
          <div className="empty-state-icon">📋</div>
          <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>
            {filter === 'all' ? 'No orders yet' : `No ${filter} orders`}
          </div>
          <div style={{ fontSize: '0.85rem' }}>
            {filter === 'all'
              ? 'Start a conversation in the Buyer Chat to create your first order.'
              : `Switch to "All" to see all orders.`}
          </div>
        </div>
      ) : (
        filteredOrders.map(order => (
          <OrderCard key={order.intent.id} order={order} />
        ))
      )}
    </div>
  );
}
