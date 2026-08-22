import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Send, CheckCircle, XCircle, Sparkles, ShoppingCart,
  Shield, CreditCard, RotateCcw, ExternalLink, RefreshCcw,
  AlertCircle, Package, ArrowLeftRight, Trash2, Plus, Minus,
  Edit3, Save
} from 'lucide-react';

const BASE_URL = 'http://127.0.0.1:8000';

/* ─── Step definitions ─────────────────────────────────────────────── */
const STEP_KEYS = ['intent', 'substitution', 'cart', 'guardrail', 'upsell', 'payment'];

const STEP_META = {
  intent:       { label: 'Intent Parsed',   icon: ShoppingCart },
  substitution: { label: 'Substitution',    icon: ArrowLeftRight },
  cart:         { label: 'Cart Built',      icon: Package },
  guardrail:    { label: 'Guardrail Check', icon: Shield },
  upsell:       { label: 'Upsell Offer',    icon: Sparkles },
  payment:      { label: 'Payment',         icon: CreditCard },
};

function initialSteps() {
  return STEP_KEYS.map(k => ({ key: k, status: 'pending', detail: '' }));
}

function updateStep(steps, key, status, detail = '') {
  return steps.map(s => s.key === key ? { ...s, status, detail } : s);
}

/* ─── Step Progress Panel ──────────────────────────────────────────── */
function StepPanel({ steps }) {
  return (
    <div className="glass step-panel">
      <div className="step-panel-header">Flow Progress</div>
      <div className="step-list">
        {steps.map(step => {
          const Icon = STEP_META[step.key].icon;
          return (
            <div key={step.key} className="step-item">
              <div className={`step-icon ${step.status}`}>
                {step.status === 'success' ? (
                  <CheckCircle size={14} />
                ) : step.status === 'error' ? (
                  <XCircle size={14} />
                ) : step.status === 'upsell' ? (
                  <Sparkles size={14} />
                ) : step.status === 'active' ? (
                  <Icon size={14} />
                ) : (
                  <Icon size={14} />
                )}
              </div>
              <div className="step-content">
                <div className={`step-title ${step.status}`}>
                  {STEP_META[step.key].label}
                </div>
                {step.detail && (
                  <div className="step-detail">{step.detail}</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Cart Review & Edit Card ──────────────────────────────────────── */
function CartReviewCard({ cartData, onUpdateCart, disabled }) {
  const [items, setItems] = useState([]);
  const [isUpdating, setIsUpdating] = useState(false);

  // Sync internal items when cartData changes
  useEffect(() => {
    if (cartData && cartData.proposed_items) {
      setItems(cartData.proposed_items.map(item => ({ ...item })));
    }
  }, [cartData]);

  const handleQtyChange = (sku, delta) => {
    setItems(prev => prev.map(item => {
      if (item.sku === sku) {
        const newQty = Math.max(1, (item.qty || 1) + delta);
        return { ...item, qty: newQty };
      }
      return item;
    }));
  };

  const handleRemove = (sku) => {
    setItems(prev => prev.filter(item => item.sku !== sku));
  };

  // Check if items have changed from the props
  const hasChanges = (() => {
    if (!cartData || !cartData.proposed_items) return false;
    if (items.length !== cartData.proposed_items.length) return true;
    for (let i = 0; i < items.length; i++) {
      const orig = cartData.proposed_items.find(o => o.sku === items[i].sku);
      if (!orig || orig.qty !== items[i].qty) return true;
    }
    return false;
  })();

  const currentTotalPaise = items.reduce((sum, i) => sum + (i.price_paise * (i.qty || 1)), 0);

  const handleSave = async () => {
    if (items.length === 0) return;
    setIsUpdating(true);
    try {
      await onUpdateCart(items);
    } finally {
      setIsUpdating(false);
    }
  };

  const handleReset = () => {
    if (cartData && cartData.proposed_items) {
      setItems(cartData.proposed_items.map(item => ({ ...item })));
    }
  };

  return (
    <div className="cart-review-card">
      <div className="cart-review-header">
        <div className="cart-review-title">
          <ShoppingCart size={16} color="var(--color-accent)" />
          <span>Review & Edit Cart</span>
          <span className="status-badge status-info" style={{ marginLeft: 6 }}>
            {items.length} {items.length === 1 ? 'item' : 'items'}
          </span>
        </div>
        {hasChanges && (
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="btn btn-ghost btn-sm"
              onClick={handleReset}
              disabled={disabled || isUpdating}
              title="Discard edits"
            >
              <RotateCcw size={13} /> Discard
            </button>
            <button
              id="btn-update-cart"
              className="btn btn-success btn-sm"
              onClick={handleSave}
              disabled={disabled || isUpdating || items.length === 0}
            >
              <Save size={13} /> {isUpdating ? 'Re-validating…' : 'Save Edits'}
            </button>
          </div>
        )}
      </div>

      {items.length === 0 ? (
        <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.88rem' }}>
          Cart is currently empty. Click "Discard" to restore original items.
        </div>
      ) : (
        <div className="cart-item-list">
          {items.map(item => (
            <div key={item.sku} className="cart-item-row">
              <div className="cart-item-main">
                <div className="cart-item-title" title={item.name || item.sku}>
                  {item.name || item.sku}
                </div>
                <div className="cart-item-meta">
                  <span style={{ fontFamily: 'monospace' }}>{item.sku}</span>
                  {item.category && <span>• {item.category}</span>}
                  <span>• <strong className="cart-item-price-unit">₹{(item.price_paise / 100).toFixed(0)} each</strong></span>
                </div>
              </div>

              <div className="cart-item-controls">
                <div className="qty-control">
                  <button
                    className="qty-btn"
                    onClick={() => handleQtyChange(item.sku, -1)}
                    disabled={disabled || isUpdating || item.qty <= 1}
                    title="Decrease quantity"
                  >
                    <Minus size={12} />
                  </button>
                  <span className="qty-number">{item.qty || 1}</span>
                  <button
                    className="qty-btn"
                    onClick={() => handleQtyChange(item.sku, 1)}
                    disabled={disabled || isUpdating}
                    title="Increase quantity"
                  >
                    <Plus size={12} />
                  </button>
                </div>

                <div className="cart-item-subtotal">
                  ₹{((item.price_paise * (item.qty || 1)) / 100).toFixed(0)}
                </div>

                <button
                  className="btn-remove-item"
                  onClick={() => handleRemove(item.sku)}
                  disabled={disabled || isUpdating}
                  title="Remove item"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="cart-review-footer">
        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          {cartData.guardrail_reason && (
            <span style={{ color: 'var(--color-success)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <Shield size={12} /> {cartData.guardrail_reason}
            </span>
          )}
        </div>

        <div className="cart-total-display">
          <span className="cart-total-label">Cart Total</span>
          <span className="cart-total-value">₹{(currentTotalPaise / 100).toFixed(0)}</span>
        </div>
      </div>
    </div>
  );
}

/* ─── Upsell Card ──────────────────────────────────────────────────── */
function UpsellCard({ upsell, onAccept, onDecline, disabled }) {
  return (
    <div className="upsell-card">
      <div className="upsell-card-header">
        <Sparkles size={14} /> Growth Agent Suggestion
      </div>
      <div className="upsell-item-name">{upsell.name || upsell.sku}</div>
      {upsell.price_paise && (
        <div className="upsell-item-price">
          + ₹{(upsell.price_paise / 100).toFixed(0)} added to cart
        </div>
      )}
      <div className="upsell-reason">"{upsell.reason}"</div>
      <div className="upsell-actions">
        <button
          id="btn-accept-upsell"
          className="btn btn-upsell"
          onClick={onAccept}
          disabled={disabled}
        >
          <CheckCircle size={15} /> Add to Order
        </button>
        <button
          id="btn-decline-upsell"
          className="btn btn-error"
          onClick={onDecline}
          disabled={disabled}
        >
          <XCircle size={15} /> No Thanks, Proceed
        </button>
      </div>
    </div>
  );
}

/* ─── Substitute Card ──────────────────────────────────────────────── */
function SubstituteCard({ oosItem, substitute, onAccept, onDecline, disabled }) {
  return (
    <div style={{
      border: '1px solid var(--color-warning-border)',
      background: 'var(--color-warning-bg)',
      borderRadius: 'var(--radius-md)',
      padding: '1.1rem 1.25rem',
      animation: 'msgSlideIn 0.35s ease forwards'
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: '0.5rem',
        fontWeight: 700, fontSize: '0.88rem', color: 'var(--color-warning)',
        marginBottom: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em'
      }}>
        <ArrowLeftRight size={14} /> Item Unavailable — Substitution Offered
      </div>
      <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
        <span style={{ color: 'var(--color-error)', fontWeight: 600 }}>
          {oosItem.name || oosItem.sku}
        </span>{' '}is out of stock.
      </div>
      <div style={{ fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.2rem' }}>
        {substitute.name}
      </div>
      <div style={{ fontSize: '0.85rem', color: 'var(--color-warning)', fontWeight: 600, marginBottom: '0.5rem' }}>
        ₹{(substitute.price_paise / 100).toFixed(0)}
      </div>
      <div style={{ fontSize: '0.88rem', color: 'var(--text-sub)', fontStyle: 'italic', marginBottom: '1rem' }}>
        "{substitute.reason}"
      </div>
      <div style={{ display: 'flex', gap: '0.75rem' }}>
        <button
          id="btn-accept-substitute"
          className="btn btn-success"
          onClick={onAccept}
          disabled={disabled}
        >
          <CheckCircle size={15} /> Use This Instead
        </button>
        <button
          id="btn-decline-substitute"
          className="btn btn-ghost"
          onClick={onDecline}
          disabled={disabled}
        >
          <XCircle size={15} /> Skip This Item
        </button>
      </div>
    </div>
  );
}

/* ─── Payment Card ─────────────────────────────────────────────────── */
function PaymentCard({ amountPaise, paymentUrl, paymentStatus, recoveryAction, onNewOrder, onCheckStatus, checkingStatus }) {
  const amount = amountPaise ? `₹${(amountPaise / 100).toFixed(0)}` : '';

  return (
    <div className="payment-card">
      <div className="payment-card-header">
        <CreditCard size={13} style={{ display: 'inline', marginRight: 5 }} />
        Payment Order Created
      </div>
      {amount && <div className="payment-amount">{amount}</div>}

      {paymentStatus === 'created' || !paymentStatus ? (
        <div className="payment-status-row">
          <RefreshCcw size={12} style={{ animation: 'spin 2s linear infinite' }} />
          Waiting for payment confirmation…
        </div>
      ) : paymentStatus === 'succeeded' ? (
        <div className="payment-status-row" style={{ color: 'var(--color-success)' }}>
          <CheckCircle size={13} /> Payment succeeded!
        </div>
      ) : paymentStatus === 'failed' ? (
        <div style={{ marginBottom: '0.6rem' }}>
          <div className="payment-status-row" style={{ color: 'var(--color-error)' }}>
            <AlertCircle size={13} /> Payment failed
          </div>
          {recoveryAction && (
            <div style={{
              fontSize: '0.82rem',
              color: 'var(--text-sub)',
              background: 'var(--color-error-bg)',
              border: '1px solid var(--color-error-border)',
              borderRadius: 'var(--radius-sm)',
              padding: '0.6rem 0.85rem',
              marginTop: '0.4rem'
            }}>
              <strong style={{ color: 'var(--color-warning)' }}>Recovery advice: </strong>
              {recoveryAction}
            </div>
          )}
        </div>
      ) : null}

      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
        {paymentUrl && (
          <a
            id="btn-pay-now"
            href={paymentUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-success"
          >
            <ExternalLink size={14} /> Pay Now
          </a>
        )}
        {paymentStatus !== 'succeeded' && (
          <button
            id="btn-check-payment"
            className="btn btn-ghost btn-sm"
            onClick={onCheckStatus}
            disabled={checkingStatus}
            title="Check if Razorpay payment has completed"
          >
            <RefreshCcw size={12} style={{ animation: checkingStatus ? 'spin 1s linear infinite' : 'none' }} />
            {checkingStatus ? 'Checking…' : 'I have paid (Check Status)'}
          </button>
        )}
        {paymentStatus === 'succeeded' && (
          <button
            id="btn-new-order"
            className="btn btn-ghost btn-sm"
            onClick={onNewOrder}
          >
            Start New Order
          </button>
        )}
      </div>
    </div>
  );
}

/* ─── Resolution Panel ─────────────────────────────────────────────── */
function ResolutionPanel({ cartId, onResult }) {
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(false);

  const handleCancel = async () => {
    if (!reason.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`${BASE_URL}/resolution/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cart_id: cartId, query: reason })
      });
      const data = await res.json();
      onResult(data);
    } catch (e) {
      onResult({ status: 'error', reason: e.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="resolution-panel">
      <div className="resolution-panel-header">
        <RotateCcw size={13} style={{ display: 'inline', marginRight: 5 }} />
        Request Cancellation / Refund
      </div>
      <input
        type="text"
        className="resolution-input"
        placeholder="e.g., I want to cancel this order…"
        value={reason}
        onChange={e => setReason(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && handleCancel()}
        disabled={loading}
        id="resolution-reason-input"
      />
      <button
        id="btn-request-refund"
        className="btn btn-error btn-sm"
        onClick={handleCancel}
        disabled={loading || !reason.trim()}
      >
        {loading ? 'Processing…' : 'Request Refund'}
      </button>
    </div>
  );
}

/* ─── Thinking Indicator ───────────────────────────────────────────── */
function ThinkingIndicator() {
  return (
    <div className="thinking-indicator">
      <div className="thinking-dots">
        <span /><span /><span />
      </div>
      Agent is processing…
    </div>
  );
}

/* ─── Main Chat Component ──────────────────────────────────────────── */
export default function Chat() {
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState([
    {
      role: 'agent',
      content: "Hi! I'm your CartPilot Buyer Agent. Describe what you'd like to order and I'll build a cart, validate it through guardrails, and find you a smart upsell suggestion."
    }
  ]);
  const [steps, setSteps] = useState(initialSteps());
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState('idle'); // idle | pending-substitute | pending-upsell | pending-payment | resolved
  const [activeCartData, setActiveCartData] = useState(null);
  const [substituteData, setSubstituteData] = useState(null);
  const [paymentData, setPaymentData] = useState(null);
  const [paymentStatus, setPaymentStatus] = useState(null);
  const [recoveryAction, setRecoveryAction] = useState(null);
  const [checkingStatus, setCheckingStatus] = useState(false);
  const bottomRef = useRef(null);
  const pollRef = useRef(null);

  const appendMsg = (role, content) =>
    setMessages(prev => [...prev, { role, content }]);

  const setStep = useCallback((key, status, detail = '') =>
    setSteps(prev => updateStep(prev, key, status, detail)), []);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, phase, paymentStatus, activeCartData]);

  // Single check status callback
  const checkStatus = useCallback(async (cartId) => {
    const targetCartId = cartId || paymentData?.cartId;
    if (!targetCartId) return;
    setCheckingStatus(true);
    try {
      const res = await fetch(`${BASE_URL}/api/cart-status/${targetCartId}`);
      const data = await res.json();
      if (data.found && data.status !== 'created') {
        if (pollRef.current) clearInterval(pollRef.current);
        setPaymentStatus(data.status);
        if (data.status === 'succeeded') {
          setStep('payment', 'success', 'Payment captured ✓');
          appendMsg('agent-success', '✅ Payment confirmed! Your order is complete.');
          setPhase('resolved');
        } else if (data.status === 'failed') {
          setStep('payment', 'error', 'Payment failed');
          setRecoveryAction(data.recovery_action);
          appendMsg('agent-blocked', `❌ Payment failed. Recovery Agent has analyzed the issue — see advice below.`);
        }
      }
    } catch (_) {}
    finally {
      setCheckingStatus(false);
    }
  }, [paymentData, setStep]);

  // Payment polling
  const startPolling = useCallback((cartId) => {
    if (pollRef.current) clearInterval(pollRef.current);
    let attempts = 0;
    pollRef.current = setInterval(async () => {
      attempts++;
      if (attempts > 50) { clearInterval(pollRef.current); return; }
      try {
        const res = await fetch(`${BASE_URL}/api/cart-status/${cartId}`);
        const data = await res.json();
        if (data.found && data.status !== 'created') {
          clearInterval(pollRef.current);
          setPaymentStatus(data.status);
          if (data.status === 'succeeded') {
            setStep('payment', 'success', 'Payment captured ✓');
            appendMsg('agent-success', '✅ Payment confirmed! Your order is complete.');
            setPhase('resolved');
          } else if (data.status === 'failed') {
            setStep('payment', 'error', 'Payment failed');
            setRecoveryAction(data.recovery_action);
            appendMsg('agent-blocked', `❌ Payment failed. Recovery Agent has analyzed the issue — see advice below.`);
          }
        }
      } catch (_) { /* silent */ }
    }, 2500);
  }, [setStep]);

  useEffect(() => () => clearInterval(pollRef.current), []);

  // When user returns to tab after paying in Razorpay, immediately check
  useEffect(() => {
    const onFocus = () => {
      if (phase === 'pending-payment' && paymentData?.cartId) {
        checkStatus(paymentData.cartId);
      }
    };
    window.addEventListener('focus', onFocus);
    const onVisChange = () => {
      if (document.visibilityState === 'visible') onFocus();
    };
    document.addEventListener('visibilitychange', onVisChange);
    return () => {
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVisChange);
    };
  }, [phase, paymentData, checkStatus]);


  /* ─── Send query to Buyer Agent + Guardrail + Growth Agent ────────── */
  const handleSend = async () => {
    if (!query.trim() || loading || phase !== 'idle') return;
    const q = query.trim();
    setQuery('');
    appendMsg('user', q);
    setLoading(true);
    setSteps(initialSteps());
    setPaymentData(null);
    setPaymentStatus(null);
    setRecoveryAction(null);
    setActiveCartData(null);

    try {
      setStep('intent', 'active', 'Parsing natural language request…');

      const res = await fetch(`${BASE_URL}/checkout/agent-checkout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q })
      });
      const data = await res.json();

      if (!res.ok) throw new Error(data.detail || 'Server error');

      setStep('intent', 'success', data.intent ? data.intent.goal : 'Intent parsed');

      // ── Substitution offered (OOS item detected pre-guardrail) ────────
      if (data.status === 'substitute_offered') {
        setStep('substitution', 'active', `${data.oos_item.name || data.oos_item.sku} is OOS`);
        appendMsg('agent',
          `⚠️ One item in your request is out of stock. The Substitution Agent found an alternative:`);
        setSubstituteData({
          intentId: data.intent_id,
          oosItem: data.oos_item,
          substitute: data.substitute,
          remainingItems: data.remaining_items,
          totalPaiseWithoutOos: data.total_paise_without_oos
        });
        setPhase('pending-substitute');
        setLoading(false);
        return;
      }

      // ── Guardrail blocked ─────────────────────────────────────────────
      setStep('cart', data.status === 'blocked' ? 'error' : 'success',
        `${(data.proposed_items || []).length} item(s) — ₹${((data.total_paise || 0) / 100).toFixed(0)}`);
      setStep('guardrail', data.status === 'blocked' ? 'error' : 'success',
        data.status === 'blocked' ? data.reason : data.guardrail_reason || 'All checks passed');

      if (data.status === 'blocked') {
        appendMsg('agent-blocked', `🚫 Guardrail Blocked: ${data.reason}`);
        setStep('upsell', 'pending', '');
        setStep('payment', 'pending', '');
        setLoading(false);
        return;
      }

      // ── Cart approved — show summary ──────────────────────────────────
      const itemSummary = (data.proposed_items || [])
        .map(i => `• ${i.name || i.sku} (${i.sku}) × ${i.qty} — ₹${(i.price_paise / 100).toFixed(0)}`)
        .join('\n');
      appendMsg('agent', `✅ Cart approved (₹${(data.total_paise / 100).toFixed(0)})\n${itemSummary}\n\nGuardrail: ${data.guardrail_reason}`);

      if (data.upsell) {
        setStep('upsell', 'upsell', `${data.upsell.name || data.upsell.sku} — ₹${(data.upsell.price_paise / 100).toFixed(0)}`);
        appendMsg('agent', 'Growth Agent found a complementary item for you:');
      } else {
        setStep('upsell', 'pending', 'No matching pairs in catalog');
      }

      setActiveCartData(data);
      setPhase('pending-upsell');
    } catch (e) {
      appendMsg('agent-blocked', `❌ Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  /* ─── Handle user editing their cart items ────────────────────────── */
  const handleUpdateCart = async (updatedItems) => {
    if (!activeCartData) return;
    setLoading(true);

    try {
      const res = await fetch(`${BASE_URL}/checkout/update-cart`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cart_id: activeCartData.cart_id,
          items: updatedItems.map(i => ({ sku: i.sku, qty: i.qty }))
        })
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to update cart');

      if (data.status === 'blocked') {
        setStep('cart', 'error', data.reason);
        setStep('guardrail', 'error', data.reason);
        appendMsg('agent-blocked', `🚫 Guardrail Blocked Updated Cart: ${data.reason}`);
        return;
      }

      setStep('cart', 'success', `${data.proposed_items.length} item(s) — ₹${(data.total_paise / 100).toFixed(0)}`);
      setStep('guardrail', 'success', data.guardrail_reason || 'Within spend cap & policy');

      const itemSummary = (data.proposed_items || [])
        .map(i => `• ${i.name || i.sku} × ${i.qty} — ₹${(i.price_paise / 100).toFixed(0)}`)
        .join('\n');
      appendMsg('agent', `📝 Cart updated (₹${(data.total_paise / 100).toFixed(0)})\n${itemSummary}`);

      if (data.upsell) {
        setStep('upsell', 'upsell', `${data.upsell.name} — ₹${(data.upsell.price_paise / 100).toFixed(0)}`);
      } else {
        setStep('upsell', 'pending', 'No matching pairs');
      }

      setActiveCartData(data);
    } catch (e) {
      appendMsg('agent-blocked', `❌ Error updating cart: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  /* ─── Handle substitute accept/decline ───────────────────────────── */
  const handleSubstitute = async (accept) => {
    setLoading(true);
    setPhase('idle');
    const subData = substituteData;
    setSubstituteData(null);

    if (accept) {
      setStep('substitution', 'success', `Using ${subData.substitute.name} instead`);
      appendMsg('user', 'Yes, use the substitute item.');
    } else {
      setStep('substitution', 'pending', 'Substitute skipped');
      appendMsg('user', 'Skip that item, continue with what\'s available.');
    }

    try {
      setStep('cart', 'active', 'Rebuilding cart…');
      const res = await fetch(`${BASE_URL}/checkout/accept-substitute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          intent_id: subData.intentId,
          original_sku: subData.oosItem.sku,
          substitute_sku: accept ? subData.substitute.sku : null,
          remaining_items: subData.remainingItems,
          total_paise_without_oos: subData.totalPaiseWithoutOos
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Error');

      if (data.status === 'blocked') {
        setStep('cart', 'error', data.reason);
        setStep('guardrail', 'error', data.reason);
        appendMsg('agent-blocked', `🚫 ${data.reason}`);
        setLoading(false);
        return;
      }

      setStep('cart', 'success', `${data.proposed_items.length} item(s) — ₹${(data.total_paise / 100).toFixed(0)}`);
      setStep('guardrail', 'success', data.guardrail_reason || 'All checks passed');
      appendMsg('agent', `✅ Cart ready (₹${(data.total_paise / 100).toFixed(0)}). Guardrail: ${data.guardrail_reason}`);

      if (data.upsell) {
        setStep('upsell', 'upsell', `${data.upsell.name} — ₹${(data.upsell.price_paise / 100).toFixed(0)}`);
        appendMsg('agent', 'Growth Agent found a complementary item for you:');
      } else {
        setStep('upsell', 'pending', 'No matching pairs in catalog');
      }
      setActiveCartData(data);
      setPhase('pending-upsell');
    } catch (e) {
      appendMsg('agent-blocked', `❌ Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  /* ─── Finalize (accept/decline upsell) ───────────────────────────── */
  const handleFinalize = async (acceptUpsell) => {
    setLoading(true);
    const cartData = activeCartData;

    appendMsg('user', acceptUpsell ? 'Yes, add the upsell item.' : 'No thanks, proceed without it.');
    setStep('upsell', acceptUpsell ? 'success' : 'pending',
      acceptUpsell ? 'Upsell accepted — re-validating…' : 'Upsell declined');

    try {
      const payload = {
        cart_id: cartData.cart_id,
        accept_upsell: acceptUpsell,
        upsell_sku: acceptUpsell && cartData.upsell ? cartData.upsell.sku : null
      };

      setStep('payment', 'active', 'Creating Razorpay order…');

      const res = await fetch(`${BASE_URL}/checkout/finalize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (!res.ok) throw new Error(data.detail || 'Finalize error');

      if (data.status === 'blocked') {
        setStep('upsell', 'error', 'Upsell blocked by guardrail');
        setStep('payment', 'pending', '');
        appendMsg('agent-blocked', `🚫 Upsell Blocked by Guardrail: ${data.reason}\n\n${data.message || ''}`);
        appendMsg('agent', `You can still complete the original order. Click the button below to retry without the upsell.`);
        setActiveCartData({ ...cartData, upsell: null, cart_id: data.fallback_cart_id });
        setPhase('pending-upsell');
        return;
      }

      if (data.status === 'approved') {
        setStep('upsell', acceptUpsell ? 'success' : 'pending',
          acceptUpsell ? 'Upsell added & re-validated' : 'Skipped');
        setStep('payment', 'active', 'Awaiting payment…');
        setPaymentData({
          url: data.payment_url,
          cartId: data.cart_id,
          amount: data.amount_paise,
          mandateId: data.payment_mandate_id
        });
        setPaymentStatus('created');
        setPhase('pending-payment');
        appendMsg('agent', `Order ready! Complete your payment below.`);
        startPolling(data.cart_id);
      }
    } catch (e) {
      appendMsg('agent-blocked', `❌ Error: ${e.message}`);
      setStep('payment', 'error', e.message);
    } finally {
      setLoading(false);
    }
  };

  /* ─── Resolution result handler ──────────────────────────────────── */
  const handleResolutionResult = (data) => {
    if (data.status === 'refunded') {
      appendMsg('agent-success',
        `✅ Refund processed! Refund ID: ${data.refund_id}\nReason: ${data.reason}`);
      setPhase('idle');
      setSteps(initialSteps());
    } else if (data.status === 'denied') {
      appendMsg('agent-blocked', `❌ Cancellation denied: ${data.reason}`);
    } else {
      appendMsg('agent-blocked', `❌ Error: ${data.reason || 'Unknown error'}`);
    }
  };

  /* ─── Reset to start new order ───────────────────────────────────── */
  const handleNewOrder = () => {
    setPhase('idle');
    setSteps(initialSteps());
    setActiveCartData(null);
    setSubstituteData(null);
    setPaymentData(null);
    setPaymentStatus(null);
    setRecoveryAction(null);
    clearInterval(pollRef.current);
    appendMsg('agent', "Ready for a new order! What would you like?");
  };

  const inputDisabled = loading || phase === 'pending-substitute' || phase === 'pending-upsell' || phase === 'pending-payment';

  return (
    <div className="chat-page">
      {/* ── Main chat column ── */}
      <div className="glass chat-main">
        <div className="chat-header">
          <div className="chat-header-dot" />
          CartPilot Buyer Agent
          {(phase === 'resolved' || phase === 'pending-payment' || phase === 'pending-upsell') && (
            <button
              id="btn-start-new"
              className="btn btn-ghost btn-sm"
              style={{ marginLeft: 'auto' }}
              onClick={handleNewOrder}
            >
              <RefreshCcw size={13} /> New Order
            </button>
          )}
        </div>

        <div className="chat-history">
          {messages.map((m, i) => (
            <div
              key={i}
              className={`chat-msg ${
                m.role === 'user' ? 'user'
                : m.role === 'agent-blocked' ? 'agent-blocked'
                : m.role === 'agent-success' ? 'agent-success'
                : 'agent'
              }`}
              style={{ whiteSpace: 'pre-line' }}
            >
              {m.content}
            </div>
          ))}

          {loading && <ThinkingIndicator />}

          {/* Substitute card */}
          {phase === 'pending-substitute' && !loading && substituteData && (
            <SubstituteCard
              oosItem={substituteData.oosItem}
              substitute={substituteData.substitute}
              onAccept={() => handleSubstitute(true)}
              onDecline={() => handleSubstitute(false)}
              disabled={loading}
            />
          )}

          {/* Cart Review & Edit card */}
          {phase === 'pending-upsell' && activeCartData && (
            <CartReviewCard
              cartData={activeCartData}
              onUpdateCart={handleUpdateCart}
              disabled={loading}
            />
          )}

          {/* Upsell card */}
          {phase === 'pending-upsell' && !loading && activeCartData && (
            <>
              {activeCartData.upsell ? (
                <UpsellCard
                  upsell={activeCartData.upsell}
                  onAccept={() => handleFinalize(true)}
                  onDecline={() => handleFinalize(false)}
                  disabled={loading}
                />
              ) : (
                <div className="upsell-card" style={{
                  borderColor: 'var(--color-accent-border)',
                  background: 'var(--color-accent-bg)'
                }}>
                  <div style={{ fontSize: '0.88rem', color: 'var(--text-sub)', marginBottom: '0.75rem' }}>
                    No upsell suggestion — proceed to payment?
                  </div>
                  <button
                    id="btn-proceed-payment"
                    className="btn btn-primary"
                    onClick={() => handleFinalize(false)}
                    disabled={loading}
                  >
                    <CreditCard size={14} /> Proceed to Payment
                  </button>
                </div>
              )}
            </>
          )}

          {/* Payment card */}
          {(phase === 'pending-payment' || phase === 'resolved') && paymentData && (
            <PaymentCard
              amountPaise={paymentData.amount}
              paymentUrl={paymentData.url}
              paymentStatus={paymentStatus}
              recoveryAction={recoveryAction}
              onNewOrder={handleNewOrder}
              onCheckStatus={() => checkStatus(paymentData.cartId)}
              checkingStatus={checkingStatus}
            />
          )}

          {/* Resolution panel — shown once payment succeeds */}
          {phase === 'resolved' && paymentStatus === 'succeeded' && paymentData && (
            <ResolutionPanel
              cartId={paymentData.cartId}
              onResult={handleResolutionResult}
            />
          )}

          <div ref={bottomRef} />
        </div>

        <div className="chat-input-area">
          <input
            id="chat-query-input"
            type="text"
            className="chat-input"
            placeholder="e.g., Get me bread and butter, need headphones under ₹1000…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !inputDisabled && handleSend()}
            disabled={inputDisabled}
          />
          <button
            id="btn-send-query"
            className="btn btn-primary"
            onClick={handleSend}
            disabled={inputDisabled || !query.trim()}
          >
            <Send size={17} />
          </button>
        </div>
      </div>

      {/* ── Step progress panel ── */}
      <StepPanel steps={steps} />
    </div>
  );
}
