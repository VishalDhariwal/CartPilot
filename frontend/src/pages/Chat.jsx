import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Send, Sparkles, Shield, AlertTriangle, CheckCircle, RefreshCcw,
  ExternalLink, Trash2, Plus, Minus, ArrowRight, CornerDownLeft,
  RotateCcw, PackageCheck, ShoppingBag, DollarSign
} from 'lucide-react';

const BASE_URL = 'http://127.0.0.1:8000';

/* ─── Initial Step Pipeline ─────────────────────────────────────────── */
const initialSteps = () => [
  { id: 'intent', label: 'Intent Parsing', subtext: 'Extracting items & budget', status: 'pending' },
  { id: 'substitution', label: 'Semantic Discovery', subtext: 'Stock & similarity match', status: 'pending' },
  { id: 'guardrail', label: 'Guardrail Engine', subtext: 'Spend cap & category policy', status: 'pending' },
  { id: 'upsell', label: 'Growth Agent', subtext: 'Market basket lift mining', status: 'pending' },
  { id: 'payment', label: 'Razorpay Mandate', subtext: 'Test-mode payment capture', status: 'pending' },
];

/* ─── Dotted-Leader Receipt Line Component ───────────────────────────── */
function ReceiptItemRow({ item, onSelectDetail }) {
  const totalItemRupees = ((item.price_paise * (item.qty || 1)) / 100).toFixed(2);

  return (
    <div className="receipt-line-row product-card-clickable" onClick={() => onSelectDetail?.(item)} title="Click to view product details & sizing">
      {item.image_url ? (
        <img
          src={item.image_url}
          alt={item.name}
          className="receipt-item-thumb"
          onError={(e) => { e.target.style.display = 'none'; }}
        />
      ) : null}
      <span className="receipt-item-label" title={item.name}>
        {item.name || item.sku}
      </span>
      <span className="receipt-item-qty">×{item.qty || 1}</span>
      <div className="receipt-dotted-leader" />
      <span className="receipt-item-price">₹{totalItemRupees}</span>
    </div>
  );
}

/* ─── Dotted-Leader Receipt Card Component ───────────────────────────── */
function ReceiptCard({ cartData, spendCapPaise, onSelectDetail }) {
  if (!cartData || !cartData.proposed_items) return null;

  const totalRupees = ((cartData.total_paise || 0) / 100).toFixed(2);
  const capRupees = spendCapPaise ? (spendCapPaise / 100).toFixed(0) : '10,000';

  return (
    <div className="receipt-card">
      <div className="receipt-header">
        <div className="receipt-merchant-title">CARTPILOT RECEIPT</div>
        <div className="receipt-submeta">
          ID: {cartData.cart_id ? cartData.cart_id.slice(-8).toUpperCase() : 'PENDING'} • {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>

      <div className="receipt-items-list">
        {cartData.proposed_items.map((item, idx) => (
          <ReceiptItemRow key={item.sku + idx} item={item} onSelectDetail={onSelectDetail} />
        ))}
      </div>

      <div className="receipt-divider" />

      <div className="receipt-total-row">
        <span className="receipt-total-label">Total Amount</span>
        <span className="receipt-total-value">₹{totalRupees}</span>
      </div>

      {cartData.guardrail_reason && (
        <div className="receipt-guardrail-tag">
          <Shield size={13} />
          <span>Guardrail: {cartData.guardrail_reason} (Spend Cap: ₹{capRupees})</span>
        </div>
      )}
    </div>
  );
}

/* ─── Scroll-Snap Multi-Card Carousel Component ──────────────────────── */
function ScrollSnapCarousel({ title, candidates, onAddItem, onSelectDetail, currentCartTotalPaise, spendCapPaise, addingSku }) {
  if (!candidates || candidates.length === 0) return null;

  return (
    <div className="carousel-wrapper">
      <div className="carousel-title-row">
        <div className="carousel-heading">
          <Sparkles size={14} color="var(--accent-mustard)" />
          <span>{title || 'Complementary Recommendations'}</span>
        </div>
        <span className="carousel-hint">Tap card for details · Swipe to explore</span>
      </div>

      <div className="carousel-track">
        {candidates.map((cand) => {
          const itemPriceRupees = (cand.price_paise / 100).toFixed(0);
          const wouldExceed = (currentCartTotalPaise + cand.price_paise) > spendCapPaise;
          const remainingBudgetPaise = Math.max(0, spendCapPaise - currentCartTotalPaise);
          const isAddingThis = addingSku === cand.sku;

          return (
            <div key={cand.sku} className={`carousel-card ${wouldExceed ? 'blocked-card' : ''}`}>
              <div className="product-card-clickable" onClick={() => onSelectDetail?.(cand)} title="Click for details, sizing & specifications">
                <div className="carousel-img-container">
                  {cand.image_url ? (
                    <img
                      src={cand.image_url}
                      alt={cand.name}
                      className="carousel-img"
                      onError={(e) => {
                        e.target.src = 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=300';
                      }}
                    />
                  ) : (
                    <ShoppingBag size={28} color="var(--ink-muted)" />
                  )}
                </div>

                <div>
                  <div className="carousel-product-name" title={cand.name}>{cand.name}</div>
                  <div className="carousel-product-price">₹{itemPriceRupees}</div>
                  <div className="carousel-reason-badge">
                    {cand.reason || (cand.lift ? `${cand.lift.toFixed(1)}x basket lift` : 'Semantic match')}
                  </div>
                </div>
              </div>

              <div>
                <button
                  className="btn-carousel-add"
                  disabled={wouldExceed || Boolean(addingSku)}
                  onClick={() => onAddItem(cand)}
                  title={wouldExceed ? `Exceeds spend cap by ₹${((cand.price_paise - remainingBudgetPaise)/100).toFixed(0)}` : 'Add to your cart'}
                >
                  {isAddingThis ? (
                    <span className="flex-center gap-1"><RefreshCcw size={12} className="animate-spin" /> Adding…</span>
                  ) : wouldExceed ? (
                    'Spend Cap Limit'
                  ) : (
                    <><Plus size={13} /> Add to Order</>
                  )}
                </button>
                {wouldExceed && (
                  <div className="carousel-blocked-reason">
                    Exceeds max budget (₹{(spendCapPaise / 100).toFixed(0)})
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Interactive Cart Review Card (Edit Quantities & Remove) ───────── */
function CartEditReviewCard({ cartData, onUpdateQty, onRemoveItem, onProceedPayment, onSelectDetail, isUpdating }) {
  if (!cartData || !cartData.proposed_items || cartData.proposed_items.length === 0) return null;

  const totalPaise = cartData.proposed_items.reduce((sum, i) => sum + (i.price_paise * (i.qty || 1)), 0);

  return (
    <div className="cart-edit-card">
      <div className="cart-edit-header">
        <span>Review & Edit Cart</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: 'var(--ink-secondary)' }}>
          {cartData.proposed_items.length} item(s)
        </span>
      </div>

      <div className="cart-edit-list">
        {cartData.proposed_items.map((item) => (
          <div key={item.sku} className="cart-edit-item-row">
            <div className="cart-edit-item-info product-card-clickable" onClick={() => onSelectDetail?.(item)} title="Click to view details & specifications">
              {item.image_url && (
                <img
                  src={item.image_url}
                  alt={item.name}
                  className="cart-edit-thumb"
                  onError={(e) => { e.target.style.display = 'none'; }}
                />
              )}
              <div style={{ minWidth: 0 }}>
                <div className="cart-edit-name" title={item.name}>{item.name || item.sku}</div>
                <div className="cart-edit-price-unit">₹{(item.price_paise / 100).toFixed(0)} each</div>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div className="cart-edit-qty-ctrl">
                <button
                  className="qty-btn"
                  onClick={() => onUpdateQty(item.sku, Math.max(0, (item.qty || 1) - 1))}
                  disabled={isUpdating}
                  title="Decrease quantity"
                >
                  <Minus size={11} />
                </button>
                <span className="qty-val">{item.qty || 1}</span>
                <button
                  className="qty-btn"
                  onClick={() => onUpdateQty(item.sku, (item.qty || 1) + 1)}
                  disabled={isUpdating}
                  title="Increase quantity"
                >
                  <Plus size={11} />
                </button>
              </div>

              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: '0.88rem', minWidth: 50, textAlign: 'right' }}>
                ₹{((item.price_paise * (item.qty || 1)) / 100).toFixed(0)}
              </span>

              <button
                className="btn-remove-cart-item"
                onClick={() => onRemoveItem(item.sku)}
                disabled={isUpdating}
                title="Remove item"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="cart-edit-footer">
        <div>
          <span style={{ fontSize: '0.8rem', color: 'var(--ink-muted)' }}>Subtotal: </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '1.05rem' }}>
            ₹{(totalPaise / 100).toFixed(0)}
          </span>
        </div>

        <button
          className="btn-checkout-primary"
          onClick={onProceedPayment}
          disabled={isUpdating}
        >
          <span>Proceed to Payment</span>
          <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
}

/* ─── Product Detail Modal Component ─────────────────────────────────── */
function ProductDetailModal({ product, isOpen, onClose, onAddToCart, currentCartTotalPaise, spendCapPaise, isAdding }) {
  if (!isOpen || !product) return null;

  const metadata = product.metadata || {};
  const sizes = metadata.sizes || ['Standard'];
  const [selectedSize, setSelectedSize] = useState(sizes[0]);

  const pricePaise = product.price_paise || 0;
  const priceRupees = (pricePaise / 100).toFixed(0);
  const remainingBudgetPaise = Math.max(0, spendCapPaise - currentCartTotalPaise);
  const wouldExceed = pricePaise > remainingBudgetPaise;

  const handleAdd = () => {
    onAddToCart({ ...product, selectedSize });
    onClose();
  };

  return (
    <div className="product-detail-overlay" onClick={onClose}>
      <div className="product-detail-modal" onClick={e => e.stopPropagation()}>
        <div className="product-detail-header">
          <div className="product-detail-title-row">
            <span className="product-detail-category-tag">{product.category || 'Product'}</span>
            {metadata.brand && (
              <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--ink-secondary)' }}>
                by {metadata.brand}
              </span>
            )}
          </div>
          <button className="btn-close-modal" onClick={onClose}>✕</button>
        </div>

        <div className="product-detail-scroll-content">
          <div className="product-detail-grid">
            <div className="product-detail-img-wrap">
              <img
                src={product.image_url || 'https://via.placeholder.com/240'}
                alt={product.name}
                className="product-detail-img-main"
                onError={(e) => { e.target.src = 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400'; }}
              />
            </div>

            <div className="product-detail-info">
              <div className="product-detail-name">{product.name}</div>
              
              <div className="product-detail-meta-row">
                <div className="product-rating-badge">
                  ★ {metadata.rating || 4.5} / 5.0
                </div>
                <div className="product-stock-badge">
                  <CheckCircle size={13} />
                  <span>{metadata.availabilityStatus || 'In Stock'} ({product.stock || 25} units)</span>
                </div>
              </div>

              <div className="product-detail-price">₹{priceRupees}</div>

              {product.description && (
                <div className="product-detail-description">
                  {product.description}
                </div>
              )}
            </div>
          </div>

          {/* Size / Variant Options */}
          {sizes.length > 0 && (
            <div className="product-size-section">
              <div className="size-section-label">
                <span>Select {metadata.variantLabel || 'Size / Variant'}:</span>
                <span style={{ color: 'var(--accent-teal)', fontWeight: 600 }}>{selectedSize}</span>
              </div>
              <div className="size-chips-grid">
                {sizes.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={`size-chip ${selectedSize === s ? 'active' : ''}`}
                    onClick={() => setSelectedSize(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Detailed Product Specifications */}
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.74rem', fontWeight: 700, color: 'var(--ink-muted)', marginBottom: '0.4rem', textTransform: 'uppercase' }}>
              Product Specifications & Details
            </div>
            <table className="specs-table">
              <tbody>
                <tr>
                  <td className="specs-key">SKU Code</td>
                  <td className="specs-val" style={{ fontFamily: 'var(--font-mono)' }}>{product.sku}</td>
                </tr>
                {metadata.brand && (
                  <tr>
                    <td className="specs-key">Brand / Manufacturer</td>
                    <td className="specs-val">{metadata.brand}</td>
                  </tr>
                )}
                {metadata.warranty && (
                  <tr>
                    <td className="specs-key">Warranty</td>
                    <td className="specs-val">{metadata.warranty}</td>
                  </tr>
                )}
                {metadata.shipping && (
                  <tr>
                    <td className="specs-key">Shipping</td>
                    <td className="specs-val">{metadata.shipping}</td>
                  </tr>
                )}
                {metadata.returnPolicy && (
                  <tr>
                    <td className="specs-key">Returns</td>
                    <td className="specs-val">{metadata.returnPolicy}</td>
                  </tr>
                )}
                {metadata.dimensions && metadata.dimensions.width && (
                  <tr>
                    <td className="specs-key">Dimensions (W×H×D)</td>
                    <td className="specs-val">{metadata.dimensions.width} × {metadata.dimensions.height} × {metadata.dimensions.depth} cm</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Modal Action Bar */}
        <div className="product-detail-footer">
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--ink-muted)' }}>Item Price:</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.15rem', fontWeight: 700, color: 'var(--ink)' }}>
              ₹{priceRupees}
            </div>
          </div>

          <button
            type="button"
            className="btn-modal-add-cart"
            disabled={wouldExceed || isAdding}
            onClick={handleAdd}
          >
            {isAdding ? (
              <span className="flex-center gap-1"><RefreshCcw size={13} className="animate-spin" /> Adding…</span>
            ) : wouldExceed ? (
              <span>Exceeds Spend Cap (₹{(spendCapPaise / 100).toFixed(0)})</span>
            ) : (
              <>
                <Plus size={14} />
                <span>Add to Order ({selectedSize})</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Razorpay Payment Card Component ────────────────────────────────── */
function RazorpayPaymentCard({ paymentData, paymentStatus, onCheckStatus, isChecking }) {
  if (!paymentData) return null;

  return (
    <div className="razorpay-pay-card">
      <div className="pay-card-header">
        <div className="pay-card-title">Razorpay Test Mandate Ready</div>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--ink-muted)' }}>
          Order: {paymentData.orderId}
        </span>
      </div>

      <p style={{ fontSize: '0.88rem', color: 'var(--ink-secondary)', marginBottom: '0.5rem' }}>
        Complete test-mode payment for <strong>₹{(paymentData.amountPaise / 100).toFixed(2)}</strong>.
      </p>

      {paymentData.paymentLink && paymentStatus !== 'succeeded' && (
        <a
          href={paymentData.paymentLink}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-razorpay-link"
        >
          <ExternalLink size={16} />
          <span>Pay ₹{(paymentData.amountPaise / 100).toFixed(0)} on Razorpay Test Checkout</span>
        </a>
      )}

      <div className="pay-poll-status">
        <div className="live-indicator-dot" />
        <span>
          {paymentStatus === 'succeeded'
            ? '✅ Payment confirmed & captured in Razorpay!'
            : 'Listening for Razorpay webhook / auto-polling…'}
        </span>
        {paymentStatus !== 'succeeded' && (
          <button
            onClick={onCheckStatus}
            disabled={isChecking}
            style={{
              marginLeft: 'auto', background: 'none', border: '1px solid var(--hairline-dark)',
              borderRadius: 'var(--radius-xs)', padding: '2px 8px', fontSize: '0.7rem',
              cursor: 'pointer', fontFamily: 'var(--font-mono)'
            }}
          >
            {isChecking ? 'Checking…' : 'Check Status'}
          </button>
        )}
      </div>
    </div>
  );
}

/* ─── Spend Cap Adjustment Modal Component ───────────────────────────── */
function SpendCapModal({ isOpen, onClose, currentSpendCapPaise, onSaveSpendCap }) {
  const [customValue, setCustomValue] = useState((currentSpendCapPaise / 100).toFixed(0));
  const presets = [500, 1000, 2500, 5000, 10000, 50000];

  useEffect(() => {
    setCustomValue((currentSpendCapPaise / 100).toFixed(0));
  }, [currentSpendCapPaise, isOpen]);

  if (!isOpen) return null;

  const handleSelectPreset = (val) => {
    setCustomValue(val.toString());
    onSaveSpendCap(val * 100);
    onClose();
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const parsed = parseInt(customValue, 10);
    if (!isNaN(parsed) && parsed > 0) {
      onSaveSpendCap(parsed * 100);
      onClose();
    }
  };

  return (
    <div className="spendcap-popover-overlay" onClick={onClose}>
      <div className="spendcap-popover-card" onClick={e => e.stopPropagation()}>
        <div className="spendcap-modal-header">
          <div className="spendcap-modal-title">
            <Shield size={16} color="var(--accent-teal)" />
            <span>Adjust Spend Cap</span>
          </div>
          <button className="btn-close-modal" onClick={onClose}>✕</button>
        </div>

        <p style={{ fontSize: '0.8rem', color: 'var(--ink-secondary)', lineHeight: 1.4 }}>
          Set your maximum budget ceiling. The Guardrail Engine will prevent orders or add-ons exceeding this limit.
        </p>

        <div>
          <div style={{ fontSize: '0.74rem', fontFamily: 'var(--font-mono)', color: 'var(--ink-muted)', marginBottom: 6 }}>
            QUICK PRESETS:
          </div>
          <div className="spendcap-presets-grid">
            {presets.map(p => (
              <button
                key={p}
                type="button"
                className={`preset-chip ${(currentSpendCapPaise / 100) === p ? 'active' : ''}`}
                onClick={() => handleSelectPreset(p)}
              >
                ₹{p.toLocaleString('en-IN')}
              </button>
            ))}
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ fontSize: '0.74rem', fontFamily: 'var(--font-mono)', color: 'var(--ink-muted)', marginBottom: 6 }}>
            CUSTOM CEILING (₹):
          </div>
          <div className="spendcap-custom-form">
            <input
              type="number"
              min="1"
              step="1"
              className="spendcap-custom-input"
              value={customValue}
              onChange={e => setCustomValue(e.target.value)}
              placeholder="e.g. 3500"
            />
            <button type="submit" className="btn-save-spendcap">
              Set Cap
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ─── Main Chat Component ────────────────────────────────────────────── */
export default function Chat() {
  const [messages, setMessages] = useState([
    {
      role: 'agent',
      content: 'Hello! I am your CartPilot personal shopping agent. Tell me what you need (e.g. "I want a new perfume and body cream", "buy me an iPhone charger and sunglasses"), and I will curate your cart with live receipts, spend cap verification, and smart recommendations.'
    }
  ]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [steps, setSteps] = useState(initialSteps());
  const [phase, setPhase] = useState('idle'); // idle | proposal | pending-payment | resolved

  // Active state objects
  const [activeCartData, setActiveCartData] = useState(null);
  const [upsellCandidates, setUpsellCandidates] = useState([]);
  const [substituteCandidates, setSubstituteCandidates] = useState([]);
  const [paymentData, setPaymentData] = useState(null);
  const [paymentStatus, setPaymentStatus] = useState(null);
  const [spendCapPaise, setSpendCapPaise] = useState(1000000);
  const [showSpendCapModal, setShowSpendCapModal] = useState(false);
  const [selectedProductForDetail, setSelectedProductForDetail] = useState(null);
  const [addingSku, setAddingSku] = useState(null);
  const [isUpdatingCart, setIsUpdatingCart] = useState(false);
  const [isCheckingStatus, setIsCheckingStatus] = useState(false);


  const streamEndRef = useRef(null);
  const pollRef = useRef(null);

  const scrollToBottom = () => {
    streamEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, activeCartData, upsellCandidates, substituteCandidates, paymentData]);

  // Fetch initial spend cap from backend
  useEffect(() => {
    fetch(`${BASE_URL}/api/policy`)
      .then(res => res.json())
      .then(data => {
        if (data.spend_cap_paise) {
          setSpendCapPaise(data.spend_cap_paise);
        }
      })
      .catch(() => {});
  }, []);

  const setStepStatus = (id, status, subtext) => {
    setSteps(prev => prev.map(s => s.id === id ? { ...s, status, ...(subtext ? { subtext } : {}) } : s));
  };

  const appendMessage = (role, content, extra = {}) => {
    setMessages(prev => [...prev, { role, content, ...extra }]);
  };

  const handleSaveSpendCap = async (newCapPaise) => {
    setSpendCapPaise(newCapPaise);
    try {
      await fetch(`${BASE_URL}/api/policy/spend-cap`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spend_cap_paise: newCapPaise })
      });
      appendMessage('agent', `🛡️ **Spend Cap Updated**: Maximum budget ceiling set to **₹${(newCapPaise / 100).toFixed(0)}**.`);

      if (activeCartData && activeCartData.total_paise) {
        if (activeCartData.total_paise > newCapPaise) {
          setActiveCartData(prev => ({
            ...prev,
            guardrail_reason: `Cart total (₹${(prev.total_paise/100).toFixed(0)}) exceeds updated spend cap (₹${(newCapPaise/100).toFixed(0)})`
          }));
        } else {
          setActiveCartData(prev => ({
            ...prev,
            guardrail_reason: `Within spend cap (₹${(prev.total_paise/100).toFixed(0)} <= ₹${(newCapPaise/100).toFixed(0)})`
          }));
        }
      }
    } catch (err) {
      console.error('Error updating spend cap policy:', err);
    }
  };

  /* ─── Submit Natural Language Query ────────────────────────────────── */
  const handleSend = async (e) => {
    e?.preventDefault();
    if (!query.trim() || loading) return;

    const userText = query.trim();
    setQuery('');
    appendMessage('user', userText);
    setLoading(true);
    setSteps(initialSteps());
    setPaymentData(null);
    setPaymentStatus(null);
    setSubstituteCandidates([]);
    setUpsellCandidates([]);

    try {
      setStepStatus('intent', 'active', 'Analyzing request & catalog…');

      const res = await fetch(`${BASE_URL}/checkout/agent-checkout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: userText, spend_cap_paise: spendCapPaise })
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Server error');

      setStepStatus('intent', 'success', data.intent ? data.intent.goal : 'Intent extracted');
      if (data.intent?.spend_cap_paise) {
        setSpendCapPaise(data.intent.spend_cap_paise);
      }

      // Handle Substitution offer
      if (data.status === 'substitute_offered') {
        setStepStatus('substitution', 'active', `OOS item detected: ${data.oos_item.name}`);
        const cands = data.substitute?.candidates || (data.substitute ? [data.substitute] : []);
        setSubstituteCandidates(cands);
        setActiveCartData(data);
        setPhase('proposal');
        appendMessage('agent', `I noticed **${data.oos_item.name}** is out of stock. I found the closest in-stock alternatives for you:`);
        setLoading(false);
        return;
      }

      // Handle Guardrail Blocked
      if (data.status === 'blocked') {
        setStepStatus('guardrail', 'error', data.reason);
        appendMessage('agent', `🚫 **Guardrail Blocked**: ${data.reason}`, { isAlert: true });
        setPhase('idle');
        setLoading(false);
        return;
      }

      // Cart Approved
      setStepStatus('guardrail', 'success', data.guardrail_reason || 'Spend cap & category policy verified ✓');
      setActiveCartData(data);

      // Handle Upsell Candidates
      if (data.upsell) {
        setStepStatus('upsell', 'success', `${data.upsell.name} (Lift: ${data.upsell.lift?.toFixed(1) || 1.2}x)`);
        const cands = data.upsell.candidates || [data.upsell];
        setUpsellCandidates(cands);
        appendMessage('agent', `I itemized your cart below! Customers who purchased these items also frequently added:`);
      } else {
        setStepStatus('upsell', 'pending', 'No matching market basket pairs');
        appendMessage('agent', `I itemized your cart below:`);
      }

      setPhase('proposal');
    } catch (err) {
      appendMessage('agent', `❌ Error: ${err.message}`, { isAlert: true });
    } finally {
      setLoading(false);
    }
  };

  /* ─── Add Single Item from Upsell / Substitution Carousel ──────────── */
  const handleAddCarouselItem = async (candidate) => {
    if (!activeCartData) return;
    setIsUpdatingCart(true);
    setAddingSku(candidate.sku);

    try {
      const currentItems = activeCartData.proposed_items || [];
      const exists = currentItems.find(i => i.sku === candidate.sku);
      let updatedItems;

      if (exists) {
        updatedItems = currentItems.map(i => i.sku === candidate.sku ? { ...i, qty: i.qty + 1 } : i);
      } else {
        updatedItems = [...currentItems, {
          sku: candidate.sku,
          qty: 1,
          name: candidate.name,
          price_paise: candidate.price_paise,
          category: candidate.category,
          image_url: candidate.image_url,
          description: candidate.description,
          metadata: candidate.metadata
        }];
      }

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
        appendMessage('agent', `🚫 Guardrail Blocked: ${data.reason}`, { isAlert: true });
        return;
      }

      setActiveCartData(data);
      if (data.upsell?.candidates) {
        setUpsellCandidates(data.upsell.candidates);
      }
      const sizeNote = candidate.selectedSize ? ` (${candidate.selectedSize})` : '';
      appendMessage('agent', `Added **${candidate.name}${sizeNote}** (₹${(candidate.price_paise / 100).toFixed(0)}) to your receipt!`);
    } catch (err) {
      appendMessage('agent', `❌ Error: ${err.message}`, { isAlert: true });
    } finally {
      setIsUpdatingCart(false);
      setAddingSku(null);
    }
  };


  /* ─── Modify Cart Quantities / Remove ──────────────────────────────── */
  const handleUpdateQty = async (sku, delta) => {
    if (!activeCartData) return;
    const currentItems = activeCartData.proposed_items || [];
    const updated = currentItems.map(i => i.sku === sku ? { ...i, qty: Math.max(1, (i.qty || 1) + delta) } : i);
    await syncCartUpdate(updated);
  };

  const handleRemoveItem = async (sku) => {
    if (!activeCartData) return;
    const currentItems = activeCartData.proposed_items || [];
    const updated = currentItems.filter(i => i.sku !== sku);
    if (updated.length === 0) {
      appendMessage('agent', 'Cart cannot be empty. Please keep at least one item.', { isAlert: true });
      return;
    }
    await syncCartUpdate(updated);
  };

  const syncCartUpdate = async (updatedItems) => {
    setIsUpdatingCart(true);
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
      if (!res.ok) throw new Error(data.detail || 'Update failed');
      setActiveCartData(data);
      if (data.upsell?.candidates) {
        setUpsellCandidates(data.upsell.candidates);
      }
    } catch (err) {
      appendMessage('agent', `❌ ${err.message}`, { isAlert: true });
    } finally {
      setIsUpdatingCart(false);
    }
  };

const extractErrorMessage = (data, defaultMsg = 'An error occurred') => {
  if (!data) return defaultMsg;
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map(d => d.msg || JSON.stringify(d)).join(', ');
  if (typeof data.detail === 'object' && data.detail !== null) return JSON.stringify(data.detail);
  if (data.message) return data.message;
  if (data.reason) return data.reason;
  return defaultMsg;
};

  /* ─── Finalize Cart & Generate Razorpay Mandate Link ───────────────── */
  const handleProceedPayment = async () => {
    if (!activeCartData) return;
    setLoading(true);
    setStepStatus('payment', 'active', 'Creating Razorpay payment link…');

    try {
      const res = await fetch(`${BASE_URL}/checkout/finalize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cart_id: activeCartData.cart_id,
          accept_upsell: false
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(extractErrorMessage(data, 'Finalization error'));

      setPaymentData({
        cartId: data.cart_id,
        orderId: data.razorpay_order_id,
        paymentLink: data.payment_link || data.payment_url,
        amountPaise: data.amount_paise
      });

      setPhase('pending-payment');
      setStepStatus('payment', 'active', 'Awaiting payment on Razorpay…');
      appendMessage('agent', `Your order is locked and ready for payment. Click below to complete test checkout on Razorpay:`);

      startPolling(data.cart_id);
    } catch (err) {
      appendMessage('agent', `❌ Payment creation failed: ${err.message}`, { isAlert: true });
      setStepStatus('payment', 'error', err.message);
    } finally {
      setLoading(false);
    }
  };


  /* ─── Polling for Payment Capture ──────────────────────────────────── */
  const checkPaymentStatus = useCallback(async (cartId) => {
    if (!cartId) return;
    setIsCheckingStatus(true);
    try {
      const res = await fetch(`${BASE_URL}/api/cart-status/${cartId}`);
      const data = await res.json();
      if (data.found) {
        setPaymentStatus(data.status);
        if (data.status === 'succeeded') {
          clearInterval(pollRef.current);
          setStepStatus('payment', 'success', 'Payment captured in Razorpay ✓');
          appendMessage('agent', `🎉 **Payment Succeeded!** Your order is confirmed. A live receipt has been logged to the immutable audit trail.`, { isSuccess: true });
          setPhase('resolved');
        }
      }
    } catch (_) {
      // silent retry
    } finally {
      setIsCheckingStatus(false);
    }
  }, []);

  const startPolling = useCallback((cartId) => {
    if (pollRef.current) clearInterval(pollRef.current);
    let attempts = 0;
    pollRef.current = setInterval(() => {
      attempts++;
      if (attempts > 60) {
        clearInterval(pollRef.current);
        return;
      }
      checkPaymentStatus(cartId);
    }, 2500);
  }, [checkPaymentStatus]);

  useEffect(() => () => clearInterval(pollRef.current), []);

  /* ─── Request AI Resolution / Refund ───────────────────────────────── */
  const handleRequestRefund = async () => {
    if (!paymentData?.cartId) return;
    setLoading(true);
    try {
      appendMessage('user', 'I would like to cancel my order and request a refund.');
      const res = await fetch(`${BASE_URL}/resolution/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cart_id: paymentData.cartId,
          query: 'Customer requested refund via chat'
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Refund failed');

      if (data.status === 'refunded') {
        appendMessage('agent', `✅ **Refund Processed**: ${data.reason}\nRazorpay Refund ID: \`${data.refund_id}\``, { isSuccess: true });
        setStepStatus('payment', 'success', `Refunded (${data.refund_id})`);
      } else {
        appendMessage('agent', `⚠️ Resolution Decision: ${data.reason}`, { isAlert: true });
      }
    } catch (err) {
      appendMessage('agent', `❌ ${err.message}`, { isAlert: true });
    } finally {
      setLoading(false);
    }
  };

  /* ─── Reset / New Order ────────────────────────────────────────────── */
  const handleReset = () => {
    clearInterval(pollRef.current);
    setPhase('idle');
    setActiveCartData(null);
    setPaymentData(null);
    setPaymentStatus(null);
    setUpsellCandidates([]);
    setSubstituteCandidates([]);
    setSteps(initialSteps());
    appendMessage('agent', 'Ready for a new shopping request! What can I help you find today?');
  };

  return (
    <div className="chat-layout">
      {/* ── Main Chat Stream Column ── */}
      <div className="chat-window">
        <div className="chat-header">
          <div className="chat-header-left">
            <div className="live-indicator-dot" />
            <div className="chat-header-title">CartPilot Personal Shopper</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button
              type="button"
              className="btn-spendcap-edit"
              onClick={() => setShowSpendCapModal(true)}
              title="Click to change your maximum spend cap ceiling anytime"
            >
              <Shield size={12} color="var(--accent-teal)" />
              <span>Spend Cap: ₹{(spendCapPaise / 100).toFixed(0)}</span>
              <span style={{ fontSize: '0.72rem', color: 'var(--ink-muted)' }}>✎</span>
            </button>
            {(phase === 'resolved' || phase === 'pending-payment') && (
              <button
                onClick={handleReset}
                style={{
                  background: 'none', border: '1px solid var(--hairline-dark)',
                  borderRadius: 'var(--radius-sm)', padding: '0.3rem 0.6rem',
                  fontSize: '0.78rem', cursor: 'pointer', display: 'flex',
                  alignItems: 'center', gap: 4, color: 'var(--ink)'
                }}
              >
                <RefreshCcw size={12} /> New Order
              </button>
            )}
          </div>

        </div>

        <div className="chat-stream">
          {messages.map((msg, i) => (
            <div key={i} className={`msg-row ${msg.role}`}>
              {msg.role === 'user' ? (
                <div className="user-bubble">{msg.content}</div>
              ) : (
                <div className={`agent-bubble ${msg.isAlert ? 'alert-bubble' : msg.isSuccess ? 'success-bubble' : ''}`}>
                  <p style={{ whiteSpace: 'pre-line' }}>{msg.content}</p>

                  {/* Render inline receipt card if this was the proposal moment */}
                  {i === messages.length - 1 && activeCartData && (
                    <>
                      <ReceiptCard
                        cartData={activeCartData}
                        spendCapPaise={spendCapPaise}
                        onSelectDetail={setSelectedProductForDetail}
                      />

                      {/* Render Substitution Multi-Card Carousel if OOS */}
                      {substituteCandidates.length > 0 && (
                        <ScrollSnapCarousel
                          title="In-Stock Semantic Alternatives"
                          candidates={substituteCandidates}
                          onAddItem={handleAddCarouselItem}
                          onSelectDetail={setSelectedProductForDetail}
                          currentCartTotalPaise={activeCartData.total_paise || 0}
                          spendCapPaise={spendCapPaise}
                          addingSku={addingSku}
                        />
                      )}

                      {/* Render Cross-Sell Multi-Card Carousel */}
                      {upsellCandidates.length > 0 && (
                        <ScrollSnapCarousel
                          title="Growth Agent Complementary Picks"
                          candidates={upsellCandidates}
                          onAddItem={handleAddCarouselItem}
                          onSelectDetail={setSelectedProductForDetail}
                          currentCartTotalPaise={activeCartData.total_paise || 0}
                          spendCapPaise={spendCapPaise}
                          addingSku={addingSku}
                        />
                      )}

                      {/* Render Interactive Cart Review & Edit component */}
                      {phase === 'proposal' && (
                        <CartEditReviewCard
                          cartData={activeCartData}
                          onUpdateQty={handleUpdateQty}
                          onRemoveItem={handleRemoveItem}
                          onProceedPayment={handleProceedPayment}
                          onSelectDetail={setSelectedProductForDetail}
                          isUpdating={isUpdatingCart}
                        />
                      )}


                      {/* Render Razorpay Payment Card */}
                      {paymentData && (
                        <RazorpayPaymentCard
                          paymentData={paymentData}
                          paymentStatus={paymentStatus}
                          onCheckStatus={() => checkPaymentStatus(paymentData.cartId)}
                          isChecking={isCheckingStatus}
                        />
                      )}

                      {/* Render Refund action after successful payment */}
                      {phase === 'resolved' && (
                        <div style={{ marginTop: '0.85rem', display: 'flex', gap: 8 }}>
                          <button
                            onClick={handleRequestRefund}
                            style={{
                              background: 'var(--alert-brick-bg)', color: 'var(--alert-brick)',
                              border: '1px solid var(--alert-brick-border)', borderRadius: 'var(--radius-sm)',
                              padding: '0.45rem 0.85rem', fontSize: '0.8rem', fontWeight: 600,
                              cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5
                            }}
                          >
                            <RotateCcw size={13} /> Request AI Resolution / Refund
                          </button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="msg-row agent">
              <div className="thinking-bubble">
                <div className="dot-flashing" />
                <div className="dot-flashing" />
                <div className="dot-flashing" />
                <span style={{ fontSize: '0.78rem', color: 'var(--ink-muted)', marginLeft: 6 }}>
                  Curating receipt & recommendations…
                </span>
              </div>
            </div>
          )}

          <div ref={streamEndRef} />
        </div>

        <form className="chat-input-bar" onSubmit={handleSend}>
          <input
            type="text"
            className="chat-input-field"
            placeholder={
              phase === 'pending-payment'
                ? 'Payment pending on Razorpay… (or type a message)'
                : 'Message your shopping agent (e.g. "I want red lipstick and perfume")…'
            }
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={loading}
          />
          <button
            type="submit"
            className="btn-chat-send"
            disabled={loading || !query.trim()}
            title="Send query"
          >
            <Send size={15} />
            <span>Send</span>
          </button>
        </form>
      </div>

      {/* ── Side Pipeline / Explainability Tracker ── */}
      <div className="side-tracker">
        <div className="tracker-title">Agent Pipeline Status</div>
        <div className="step-list">
          {steps.map((st) => (
            <div key={st.id} className="step-row">
              <div className={`step-icon-wrap ${st.status}`}>
                {st.status === 'success' ? (
                  <CheckCircle size={14} />
                ) : st.status === 'error' ? (
                  <AlertTriangle size={14} />
                ) : st.status === 'active' ? (
                  <Sparkles size={13} />
                ) : (
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor' }} />
                )}
              </div>
              <div className="step-content">
                <div className="step-label">{st.label}</div>
                <div className="step-subtext">{st.subtext}</div>
              </div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid var(--hairline)' }}>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: '0.92rem', fontWeight: 600, marginBottom: '0.4rem' }}>
            Explainability Engine
          </div>
          <p style={{ fontSize: '0.76rem', color: 'var(--ink-muted)', lineHeight: 1.4 }}>
            Every product recommendation is scored via 384-dimensional dense semantic vectors or mined market basket lift rules.
          </p>
        </div>
      </div>

      {/* ── Spend Cap Policy Modal ── */}
      <SpendCapModal
        isOpen={showSpendCapModal}
        onClose={() => setShowSpendCapModal(false)}
        currentSpendCapPaise={spendCapPaise}
        onSaveSpendCap={handleSaveSpendCap}
      />

      {/* ── Product Details & Sizing Modal ── */}
      <ProductDetailModal
        product={selectedProductForDetail}
        isOpen={Boolean(selectedProductForDetail)}
        onClose={() => setSelectedProductForDetail(null)}
        onAddToCart={handleAddCarouselItem}
        currentCartTotalPaise={activeCartData?.total_paise || 0}
        spendCapPaise={spendCapPaise}
        isAdding={addingSku === selectedProductForDetail?.sku}
      />
    </div>
  );
}


