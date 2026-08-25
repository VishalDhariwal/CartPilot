import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  Send, Sparkles, Shield, AlertTriangle, CheckCircle, RefreshCcw,
  ExternalLink, Trash2, Plus, Minus, ArrowRight, CornerDownLeft,
  RotateCcw, PackageCheck, ShoppingBag, DollarSign,
  History, MessageSquare, PanelLeftClose, PanelLeft, BookOpen, ChevronRight, Search
} from 'lucide-react';


const BASE_URL = 'http://127.0.0.1:8000';
const STORAGE_KEY = 'cartpilot_chat_sessions_v2';
const ACTIVE_ID_KEY = 'cartpilot_active_session_id';

const createDefaultSession = (title = 'New Shopping Chat') => ({
  id: 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
  title,
  createdAt: Date.now(),
  updatedAt: Date.now(),
  messages: [
    {
      role: 'agent',
      isWelcome: true,
      content: 'Hello! I am your CartPilot personal shopping agent. Tell me what you need (e.g. "I want a new perfume and body cream", "buy me an iPhone charger and sunglasses"), and I will curate your cart with live receipts, spend cap verification, and smart recommendations.'
    }
  ],
  phase: 'idle',
  activeCartData: null,
  upsellCandidates: [],
  substituteCandidates: [],
  paymentData: null,
  paymentStatus: null,
  spendCapPaise: 1000000
});

const loadSavedSessions = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch (_) { }
  const def = createDefaultSession();
  return [def];
};

const formatGuardrailNotice = (reason) => {
  if (!reason) {
    return `🔍 **No Matching Items Found**\nI couldn't find items matching your request in our catalog. Try searching for products like **MacBook Pro**, **iPhone**, **Dior Perfume**, or **Running Shoes**.`;
  }
  const low = reason.toLowerCase();
  if (low.includes('exceeds spend cap') || low.includes('spend cap')) {
    return `🛡️ **Budget Limit Notice**\n${reason}\n\n💡 *Tip: You can increase your spending limit by clicking **⚙️ Spend Cap** at the top right.*`;
  }
  if (low.includes('category') || low.includes('not allowed')) {
    return `🛡️ **Merchant Policy Notice**\n${reason}`;
  }
  if (low.includes('empty') || low.includes('no valid items')) {
    return `🔍 **No Matching Items Found**\nI couldn't find items in our catalog matching your request. Try browsing categories like **Laptops**, **Smartphones**, **Fragrances**, **Skincare**, or **Fashion**.`;
  }
  return `🛡️ **Shopping Policy Notice**\n${reason}`;
};

const NODE_LABELS = {
  UNDERSTAND_INTENT: { label: 'Intent Analysis', icon: '🎯' },
  SEARCH_CATALOG: { label: 'Catalog Search', icon: '🔍' },
  BUILD_CART: { label: 'Cart Synthesis', icon: '🛒' },
  VALIDATE_CART: { label: 'Guardrail & Budget Policy', icon: '🛡️' },
  REVISE_CART: { label: 'Cart Optimization', icon: '⚡' },
  GET_RECOMMENDATIONS: { label: 'RecSys Engine', icon: '✨' },
  PRESENT_FOR_APPROVAL: { label: 'Authorization Gate', icon: '👤' },
  EXECUTE_CHECKOUT: { label: 'Payment Initiation', icon: '💳' },
  VERIFY_PAYMENT: { label: 'Mandate Verification', icon: '✅' },
  HANDLE_RECOVERY: { label: 'Payment Recovery', icon: '🔄' },
  NOTIFY_BUYER_BLOCKED: { label: 'Policy Resolution', icon: '🚫' },
  FINALIZE_OUTCOME: { label: 'Audit Logging', icon: '📝' }
};

function LangGraphTraceViewer({ trace, revisionCount }) {
  const [open, setOpen] = useState(false);
  if (!trace || trace.length === 0) return null;

  return (
    <div className="trace-timeline-container">
      <button
        type="button"
        className="trace-timeline-toggle"
        onClick={() => setOpen(!open)}
      >
        <span className="trace-badge-ai">LangGraph</span>
        <span className="trace-steps-count">
          Decision Execution Trace ({trace.length} steps{revisionCount ? ` · ${revisionCount} auto-revisions` : ''})
        </span>
        <span className="trace-arrow-icon">{open ? '▲ Hide' : '▼ Inspect'}</span>
      </button>

      {open && (
        <div className="trace-step-flow">
          {trace.map((step, idx) => {
            const meta = NODE_LABELS[step.node] || { label: step.node, icon: '⚙️' };
            const isBlocked = step.guardrail_status === 'blocked' || Boolean(step.error);
            const isApproved = step.guardrail_status === 'approved';

            return (
              <div key={idx} className={`trace-row ${isBlocked ? 'is-blocked' : isApproved ? 'is-approved' : 'is-neutral'}`}>
                <div className="trace-node-bullet">
                  <span className="trace-bullet-dot" />
                  {idx < trace.length - 1 && <span className="trace-connector-line" />}
                </div>
                <div className="trace-node-card">
                  <div className="trace-node-header">
                    <span className="trace-node-title">
                      {meta.icon} {meta.label}
                    </span>
                    {step.tool && <span className="trace-pill-tool">{step.tool}</span>}
                    {step.guardrail_status && (
                      <span className={`trace-pill-status ${step.guardrail_status}`}>
                        {step.guardrail_status}
                      </span>
                    )}
                  </div>
                  <div className="trace-node-summary">{step.result_summary || step.input_summary}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ─── Unified Dotted-Leader & Interactive Receipt Card Component ────── */
function ReceiptCard({
  cartData,
  spendCapPaise,
  onSelectDetail,
  isRefunded,
  isInteractive,
  onUpdateQty,
  onRemoveItem,
  onProceedPayment,
  isUpdating
}) {
  if (!cartData || !cartData.proposed_items || cartData.proposed_items.length === 0) return null;

  const totalPaise = cartData.proposed_items.reduce((sum, i) => sum + (i.price_paise * (i.qty || 1)), 0);
  const totalRupees = ((totalPaise || cartData.total_paise || 0) / 100).toFixed(2);
  const capRupees = spendCapPaise ? (spendCapPaise / 100).toFixed(0) : '10,000';

  return (
    <div className={`receipt-card ${isRefunded ? 'refunded' : ''}`}>
      <div className="receipt-header">
        <div className="receipt-merchant-title">
          CARTPILOT RECEIPT
          {isRefunded && <span className="receipt-refunded-badge">REFUNDED</span>}
        </div>
        <div className="receipt-submeta">
          ID: {cartData.cart_id ? cartData.cart_id.slice(-8).toUpperCase() : 'PENDING'} • {cartData.proposed_items.length} item(s)
        </div>
      </div>

      <div className="receipt-items-list">
        {cartData.proposed_items.map((item, idx) => {
          const totalItemRupees = ((item.price_paise * (item.qty || 1)) / 100).toFixed(2);

          return (
            <div key={item.sku + idx} className="receipt-line-row">
              <div
                className="receipt-item-info product-card-clickable"
                onClick={() => onSelectDetail?.(item)}
                title="Click to view product details & sizing"
                style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, flex: 1 }}
              >
                {item.image_url && (
                  <img
                    src={item.image_url}
                    alt={item.name}
                    className="receipt-item-thumb"
                    onError={(e) => { e.target.style.display = 'none'; }}
                  />
                )}
                <div style={{ minWidth: 0 }}>
                  <div className="receipt-item-label" title={item.name}>
                    {item.name || item.sku}
                    {item.selected_size && (
                      <span style={{ marginLeft: 6, fontSize: '0.72rem', padding: '2px 6px', borderRadius: 4, background: 'rgba(56, 178, 172, 0.15)', color: 'var(--accent-teal)', fontWeight: 600, display: 'inline-block' }}>
                        {item.selected_size}
                      </span>
                    )}
                  </div>
                  {isInteractive && (
                    <div style={{ fontSize: '0.72rem', color: 'var(--ink-muted)' }}>
                      ₹{(item.price_paise / 100).toFixed(0)} each
                    </div>
                  )}
                </div>
              </div>

              {isInteractive ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                  <div className="cart-edit-qty-ctrl">
                    <button
                      className="qty-btn"
                      onClick={() => onUpdateQty?.(item.sku, Math.max(0, (item.qty || 1) - 1))}
                      disabled={isUpdating}
                      title="Decrease quantity"
                    >
                      <Minus size={10} />
                    </button>
                    <span className="qty-val">{item.qty || 1}</span>
                    <button
                      className="qty-btn"
                      onClick={() => onUpdateQty?.(item.sku, (item.qty || 1) + 1)}
                      disabled={isUpdating}
                      title="Increase quantity"
                    >
                      <Plus size={10} />
                    </button>
                  </div>

                  <span className="receipt-item-price" style={{ minWidth: 50, textAlign: 'right' }}>
                    ₹{totalItemRupees}
                  </span>

                  <button
                    className="btn-remove-cart-item"
                    onClick={() => onRemoveItem?.(item.sku)}
                    disabled={isUpdating}
                    title="Remove item"
                    style={{ padding: '3px 4px', border: 'none', background: 'none', cursor: 'pointer', color: 'var(--ink-muted)' }}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ) : (
                <>
                  <span className="receipt-item-qty">×{item.qty || 1}</span>
                  <div className="receipt-dotted-leader" />
                  <span className="receipt-item-price">₹{totalItemRupees}</span>
                </>
              )}
            </div>
          );
        })}
      </div>

      <div className="receipt-divider" />

      <div className="receipt-total-row">
        <span className="receipt-total-label">{isRefunded ? 'Refunded Total' : 'Total Amount'}</span>
        <span className="receipt-total-value" style={isRefunded ? { color: 'var(--alert-brick)', textDecoration: 'line-through' } : {}}>
          ₹{totalRupees}
        </span>
      </div>

      {cartData.status === 'pending_confirmation' && (
        <div className="pending-confirmation-banner">
          <div className="pending-conf-title">
            <Lock size={14} color="var(--accent-mustard)" />
            <strong>Reserve Pay Autonomy Threshold Confirmation</strong>
          </div>
          <p className="pending-conf-desc">
            This order of ₹{totalRupees} meets or exceeds the merchant autonomy threshold. Explicit authorization is required before generating the Razorpay payment mandate.
          </p>
        </div>
      )}

      {cartData.guardrail_reason && (
        <div className="receipt-guardrail-tag">
          <Shield size={13} />
          <span>Guardrail: {cartData.guardrail_reason} (Spend Cap: ₹{capRupees})</span>
        </div>
      )}

      {cartData.decision_trace && cartData.decision_trace.length > 0 && (
        <LangGraphTraceViewer trace={cartData.decision_trace} revisionCount={cartData.revision_count} />
      )}

      {isInteractive && (
        <div style={{ marginTop: '0.85rem' }}>
          <button
            className="btn-checkout-primary"
            onClick={onProceedPayment}
            disabled={isUpdating}
            style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, padding: '0.65rem 1rem' }}
          >
            {cartData.status === 'pending_confirmation' ? (
              <>
                <Lock size={14} />
                <span>Authorize High-Value Order & Proceed</span>
              </>
            ) : (
              <>
                <span>Proceed to Payment</span>
                <ArrowRight size={14} />
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}




/* ─── Scroll-Snap Multi-Card Carousel Component ──────────────────────── */
function ScrollSnapCarousel({ title, candidates, onAddItem, onSelectDetail, currentCartTotalPaise, spendCapPaise, addingSku, cartSkus }) {
  const visibleCandidates = (candidates || []).filter(cand => !cartSkus?.has(cand.sku));
  if (!visibleCandidates || visibleCandidates.length === 0) return null;

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
        {visibleCandidates.map((cand) => {
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
                  title={wouldExceed ? `Exceeds spend cap by ₹${((cand.price_paise - remainingBudgetPaise) / 100).toFixed(0)}` : 'Add to your cart'}
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
function ProductDetailModal({ product, isOpen, onClose, onAddToCart, currentCartTotalPaise, spendCapPaise, isAdding, isAlreadyInCart }) {
  if (!isOpen || !product) return null;

  return (
    <ProductDetailModalContent
      product={product}
      onClose={onClose}
      onAddToCart={onAddToCart}
      currentCartTotalPaise={currentCartTotalPaise}
      spendCapPaise={spendCapPaise}
      isAdding={isAdding}
      isAlreadyInCart={isAlreadyInCart}
    />
  );
}

function ProductDetailModalContent({ product, onClose, onAddToCart, currentCartTotalPaise, spendCapPaise, isAdding, isAlreadyInCart }) {
  const metadata = product.metadata || {};
  const options = metadata.sizes || metadata.options || ['Standard'];
  const initialOption = product.selected_size || product.selected_option || product.selectedSize || (options.length > 0 ? options[0] : 'Standard');
  const [selectedOption, setSelectedOption] = useState(initialOption);
  const variantLabel = metadata.variantLabel || 'Option';

  const pricePaise = product.price_paise || 0;
  const priceRupees = (pricePaise / 100).toFixed(0);
  const remainingBudgetPaise = Math.max(0, spendCapPaise - currentCartTotalPaise);
  const wouldExceed = !isAlreadyInCart && pricePaise > remainingBudgetPaise;

  const handleAdd = () => {
    onAddToCart({ ...product, selectedSize: selectedOption, selected_size: selectedOption });
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

          {/* Variant / Option Selection */}
          {options.length > 0 && (
            <div className="product-size-section">
              <div className="size-section-label">
                <span>Select {variantLabel}:</span>
                <span style={{ color: 'var(--accent-teal)', fontWeight: 600 }}>{selectedOption}</span>
              </div>
              <div className="size-chips-grid">
                {options.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    className={`size-chip ${selectedOption === opt ? 'active' : ''}`}
                    onClick={() => setSelectedOption(opt)}
                  >
                    {opt}
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
              <span className="flex-center gap-1"><RefreshCcw size={13} className="animate-spin" /> {isAlreadyInCart ? 'Updating…' : 'Adding…'}</span>
            ) : wouldExceed ? (
              <span>Exceeds Spend Cap (₹{(spendCapPaise / 100).toFixed(0)})</span>
            ) : (
              <>
                {isAlreadyInCart ? <CheckCircle size={14} /> : <Plus size={14} />}
                <span>{isAlreadyInCart ? `Update to ${selectedOption}` : `Add to Order (${selectedOption})`}</span>
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

  const isRefunded = paymentStatus === 'refunded';

  return (
    <div className={`razorpay-pay-card ${isRefunded ? 'refunded' : ''}`}>
      <div className="pay-card-header">
        <div className="pay-card-title">
          {isRefunded ? 'Razorpay Order Refunded & Reversed' : 'Razorpay Test Mandate Ready'}
        </div>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--ink-muted)' }}>
          Order: {paymentData.orderId}
        </span>
      </div>

      <p style={{ fontSize: '0.88rem', color: 'var(--ink-secondary)', marginBottom: '0.5rem' }}>
        {isRefunded ? (
          <>The payment of <strong>₹{(paymentData.amountPaise / 100).toFixed(2)}</strong> has been cancelled & refunded via test-mode API.</>
        ) : (
          <>Complete test-mode payment for <strong>₹{(paymentData.amountPaise / 100).toFixed(2)}</strong>.</>
        )}
      </p>

      {!isRefunded && paymentData.paymentLink && paymentStatus !== 'succeeded' && (
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
        <div className="live-indicator-dot" style={isRefunded ? { background: 'var(--alert-brick)' } : {}} />
        <span>
          {isRefunded
            ? '✅ Refund completed and recorded in audit ledger'
            : paymentStatus === 'succeeded'
              ? '✅ Payment confirmed & captured in Razorpay!'
              : 'Listening for Razorpay webhook / auto-polling…'}
        </span>
        {!isRefunded && paymentStatus !== 'succeeded' && (
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

/* ─── Collapsible Chat History Sidebar Component ──────────────────────── */
function ChatHistorySidebar({
  sessions,
  currentSessionId,
  isOpen,
  onClose,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  searchQuery,
  onSearchChange
}) {
  const filteredSessions = sessions
    .filter(s => {
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (s.title && s.title.toLowerCase().includes(q)) ||
        (s.messages && s.messages.some(m => m.content && m.content.toLowerCase().includes(q)));
    })
    .sort((a, b) => (b.updatedAt || b.createdAt || 0) - (a.updatedAt || a.createdAt || 0));

  return (
    <aside className={`chat-history-sidebar ${!isOpen ? 'collapsed' : ''}`} aria-label="Chat History">
      <div className="history-header">
        <div className="history-title">
          <PanelLeft size={16} color="var(--accent-teal)" />
          <span>Chat History</span>
        </div>
        <button
          className="btn-close-history-sidebar"
          onClick={onClose}
          title="Collapse Chat History"
        >
          <PanelLeftClose size={16} />
        </button>
      </div>



      <div className="history-actions-bar">
        <button
          type="button"
          className="btn-new-chat-sidebar"
          onClick={onNewChat}
          title="Start a new shopping conversation"
        >
          <Plus size={15} color="var(--accent-teal)" />
          <span>New Chat</span>
        </button>

        {sessions.length > 3 && (
          <input
            type="text"
            className="history-search-input"
            placeholder="Search past chats…"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        )}
      </div>

      <div className="history-sessions-list">
        {filteredSessions.length === 0 ? (
          <div className="history-empty-state">
            {searchQuery ? 'No matching chats found.' : 'No previous chat sessions yet. Start shopping!'}
          </div>
        ) : (
          filteredSessions.map((s) => {
            const isActive = s.id === currentSessionId;
            const itemCount = s.activeCartData?.proposed_items?.length || 0;
            const totalRupees = s.activeCartData?.total_paise ? (s.activeCartData.total_paise / 100).toFixed(0) : null;
            const timeStr = new Date(s.updatedAt || s.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

            return (
              <div
                key={s.id}
                className={`history-session-item ${isActive ? 'active' : ''}`}
                onClick={() => onSelectSession(s.id)}
              >
                <div className="history-session-info">
                  <div className="history-session-title" title={s.title}>
                    {s.title || 'Shopping Request'}
                  </div>
                  <div className="history-session-sub">
                    <span>{timeStr}</span>
                    {s.phase === 'resolved' ? (
                      <span className="history-session-badge settled">Settled ✓</span>
                    ) : totalRupees ? (
                      <span className="history-session-badge pending">₹{totalRupees} ({itemCount})</span>
                    ) : null}
                  </div>
                </div>

                <button
                  type="button"
                  className="btn-delete-session"
                  onClick={(e) => onDeleteSession(e, s.id)}
                  title="Delete chat session"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}

/* ─── Authentic Welcome Hero Card Component ────────────────────────── */
function WelcomeHeroCard({ onSelectPrompt }) {
  const [prompts, setPrompts] = useState([
    {
      emoji: '💄',
      category: 'Beauty & Fragrances',
      prompt: 'I want Essence Mascara and Dior Sauvage perfume within ₹3,500',
      tag: 'Trending'
    },
    {
      emoji: '📱',
      category: 'Electronics & Style',
      prompt: 'Buy me an iPhone charger and luxury sunglasses under ₹2,000',
      tag: 'High Demand'
    },
    {
      emoji: '💻',
      category: 'Tech & Laptops',
      prompt: 'Show me a Lenovo Yoga 920 laptop or iPad Mini with fast delivery',
      tag: 'Work & Play'
    },
    {
      emoji: '👟',
      category: 'Footwear & Fashion',
      prompt: 'Find stylish running shoes and Calvin Klein perfume under ₹4,000',
      tag: 'Lifestyle'
    }
  ]);
  const [loadingPrompts, setLoadingPrompts] = useState(false);

  const fetchTrendingPrompts = async (isRefresh = false) => {
    setLoadingPrompts(true);
    try {
      const res = await fetch(`${BASE_URL}/checkout/trending-prompts${isRefresh ? '?refresh=true' : ''}`);
      if (res.ok) {
        const data = await res.json();
        if (data.prompts && data.prompts.length > 0) {
          setPrompts(data.prompts);
        }
      }
    } catch (err) {
      console.warn('Could not load dynamic trending prompts:', err);
    } finally {
      setLoadingPrompts(false);
    }
  };

  useEffect(() => {
    fetchTrendingPrompts(false);
  }, []);

  return (
    <div className="welcome-hero-card">
      <div className="welcome-hero-header">
        <div className="welcome-agent-identity">
          <div className="welcome-avatar-icon">
            <Sparkles size={18} />
          </div>
          <div>
            <div className="welcome-agent-title">CartPilot Shopping Concierge</div>
            <div className="welcome-agent-subtitle">Explainable Agentic Commerce • Live Catalog Sync</div>
          </div>
        </div>

        <div className="welcome-status-pill">
          <span className="pulse-dot" />
          <span>Active & Guardrail Protected</span>
        </div>
      </div>

      <div className="welcome-hero-body">
        Hello! I am your <strong>CartPilot</strong> personal shopping agent. Tell me what you need in plain natural language, and I will curate your cart with live receipts, spend cap verification, and smart recommendations.
      </div>

      <div className="welcome-prompts-section">
        <div className="welcome-prompts-header-row">
          <div className="welcome-prompts-title">
            <Sparkles size={13} color="var(--accent-mustard)" />
            <span>AI-Curated Trending Demands</span>
            <span className="live-ai-badge">Live LLM</span>
          </div>

          <button
            type="button"
            className={`btn-refresh-prompts ${loadingPrompts ? 'loading' : ''}`}
            onClick={() => fetchTrendingPrompts(true)}
            disabled={loadingPrompts}
            title="Generate fresh demand-driven suggestions using LLM"
          >
            <RefreshCcw size={11} className={loadingPrompts ? 'spin-icon' : ''} />
            <span>{loadingPrompts ? 'Analyzing...' : 'Refresh Demands'}</span>
          </button>
        </div>

        <div className="welcome-chips-grid">
          {prompts.map((item, idx) => (
            <button
              key={idx}
              type="button"
              className="welcome-chip-btn"
              onClick={() => onSelectPrompt(item.prompt)}
              title={`Click to try: "${item.prompt}"`}
            >
              <span className="welcome-chip-emoji">{item.emoji || '🛍️'}</span>
              <div className="welcome-chip-content">
                <div className="welcome-chip-label-row">
                  <span className="welcome-chip-label">{item.category}</span>
                  {item.tag && <span className="welcome-chip-tag">{item.tag}</span>}
                </div>
                <div className="welcome-chip-text">{item.prompt}</div>
              </div>
              <ArrowRight size={13} color="var(--ink-muted)" style={{ marginTop: 2, flexShrink: 0 }} />
            </button>
          ))}
        </div>
      </div>

      <div className="welcome-badges-row">
        <span className="welcome-badge-tag">
          <Shield size={12} color="var(--accent-teal)" />
          <span>Spend Cap Guarantee</span>
        </span>
        <span className="welcome-badge-tag">
          <CheckCircle size={12} color="var(--accent-teal)" />
          <span>Zero Hallucinated Prices</span>
        </span>
        <span className="welcome-badge-tag">
          <ShoppingBag size={12} color="var(--accent-teal)" />
          <span>Razorpay Test Checkout</span>
        </span>
      </div>
    </div>
  );
}

/* ─── Main Chat Component ────────────────────────────────────────────── */
export default function Chat() {
  const [sessions, setSessions] = useState(loadSavedSessions);
  const [currentSessionId, setCurrentSessionId] = useState(() => {
    const savedActive = localStorage.getItem(ACTIVE_ID_KEY);
    const initial = loadSavedSessions();
    if (savedActive && initial.some(s => s.id === savedActive)) {
      return savedActive;
    }
    return initial[0]?.id || 'default_session';
  });

  const activeSession = sessions.find(s => s.id === currentSessionId) || sessions[0] || createDefaultSession();

  const [messages, setMessages] = useState(activeSession.messages);
  const [phase, setPhase] = useState(activeSession.phase || 'idle');
  const [activeCartData, setActiveCartData] = useState(activeSession.activeCartData);
  const [upsellCandidates, setUpsellCandidates] = useState(activeSession.upsellCandidates || []);
  const [substituteCandidates, setSubstituteCandidates] = useState(activeSession.substituteCandidates || []);
  const [paymentData, setPaymentData] = useState(activeSession.paymentData);
  const [paymentStatus, setPaymentStatus] = useState(activeSession.paymentStatus);
  const [spendCapPaise, setSpendCapPaise] = useState(activeSession.spendCapPaise || 1000000);

  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [showSpendCapModal, setShowSpendCapModal] = useState(false);
  const [selectedProductForDetail, setSelectedProductForDetail] = useState(null);
  const [addingSku, setAddingSku] = useState(null);
  const [isUpdatingCart, setIsUpdatingCart] = useState(false);
  const [isCheckingStatus, setIsCheckingStatus] = useState(false);
  const [isHistoryOpen, setIsHistoryOpen] = useState(() => localStorage.getItem('cartpilot_history_open') !== 'false');
  const [historySearch, setHistorySearch] = useState('');

  const streamEndRef = useRef(null);
  const pollRef = useRef(null);

  const scrollToBottom = () => {
    streamEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, activeCartData, upsellCandidates, substituteCandidates, paymentData]);

  // Sync active chat state changes back to sessions, localStorage & SQLite backend
  useEffect(() => {
    setSessions(prevSessions => {
      const idx = prevSessions.findIndex(s => s.id === currentSessionId);
      if (idx === -1) return prevSessions;

      let updatedTitle = prevSessions[idx].title;
      if (updatedTitle === 'New Shopping Chat' || !updatedTitle) {
        const firstUserMsg = messages.find(m => m.role === 'user');
        if (firstUserMsg && firstUserMsg.content) {
          updatedTitle = firstUserMsg.content.slice(0, 32);
          if (firstUserMsg.content.length > 32) updatedTitle += '…';
        }
      }

      const updatedSession = {
        ...prevSessions[idx],
        title: updatedTitle,
        updatedAt: Date.now(),
        messages,
        phase,
        activeCartData,
        upsellCandidates,
        substituteCandidates,
        paymentData,
        paymentStatus,
        spendCapPaise
      };

      const nextSessions = [...prevSessions];
      nextSessions[idx] = updatedSession;
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(nextSessions));
      } catch (_) { }

      // Persist to backend SQLite for cross-browser synchronization
      fetch(`${BASE_URL}/api/chat-sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: updatedSession.id,
          title: updatedSession.title,
          session_data: updatedSession
        })
      }).catch(() => { });

      return nextSessions;
    });
  }, [messages, phase, activeCartData, upsellCandidates, substituteCandidates, paymentData, paymentStatus, spendCapPaise, currentSessionId]);

  // Fetch initial spend cap and live-sync persistent sessions from backend SQLite
  useEffect(() => {
    fetch(`${BASE_URL}/api/policy`)
      .then(res => res.json())
      .then(data => {
        if (data.spend_cap_paise) {
          setSpendCapPaise(data.spend_cap_paise);
        }
      })
      .catch(() => { });

    const syncSessions = () => {
      // Do not sync/overwrite state if user is actively awaiting an agent response
      if (loading) return;

      fetch(`${BASE_URL}/api/chat-sessions`)
        .then(res => res.json())
        .then(data => {
          if (data?.sessions && Array.isArray(data.sessions) && data.sessions.length > 0) {
            const serverSessions = data.sessions;
            setSessions(serverSessions);
            try {
              localStorage.setItem(STORAGE_KEY, JSON.stringify(serverSessions));
            } catch (_) { }

            // If the currently open session was updated in another browser window
            const serverActive = serverSessions.find(s => s.id === currentSessionId);
            if (serverActive && !loading) {
              if (
                serverActive.messages &&
                serverActive.messages.length > messages.length
              ) {
                setMessages(serverActive.messages);
                if (serverActive.activeCartData) setActiveCartData(serverActive.activeCartData);
                if (serverActive.phase) setPhase(serverActive.phase);
                if (serverActive.paymentData) setPaymentData(serverActive.paymentData);
                if (serverActive.paymentStatus) setPaymentStatus(serverActive.paymentStatus);
                if (serverActive.upsellCandidates) setUpsellCandidates(serverActive.upsellCandidates);
              }
            }
          }
        })
        .catch(() => { });
    };


    syncSessions();
    const interval = setInterval(syncSessions, 2500);

    const onStorage = (e) => {
      if (e.key === STORAGE_KEY && e.newValue) {
        try {
          const parsed = JSON.parse(e.newValue);
          if (Array.isArray(parsed) && parsed.length > 0) {
            setSessions(parsed);
            const active = parsed.find(s => s.id === currentSessionId);
            if (active) {
              setMessages(active.messages || []);
              setActiveCartData(active.activeCartData || null);
              setPhase(active.phase || 'idle');
              setPaymentData(active.paymentData || null);
              setPaymentStatus(active.paymentStatus || null);
            }
          }
        } catch (_) { }
      }
    };
    window.addEventListener('storage', onStorage);

    return () => {
      clearInterval(interval);
      window.removeEventListener('storage', onStorage);
    };
  }, [currentSessionId, messages.length, phase, paymentStatus]);


  const appendMessage = (role, content, extra = {}) => {
    setMessages(prev => [...prev, { role, content, ...extra }]);
  };

  const handleSelectSession = (sessionId) => {
    if (sessionId === currentSessionId) return;
    if (pollRef.current) clearInterval(pollRef.current);

    const target = sessions.find(s => s.id === sessionId);
    if (!target) return;

    setCurrentSessionId(target.id);
    localStorage.setItem(ACTIVE_ID_KEY, target.id);
    setMessages(target.messages || []);
    setPhase(target.phase || 'idle');
    setActiveCartData(target.activeCartData || null);
    setUpsellCandidates(target.upsellCandidates || []);
    setSubstituteCandidates(target.substituteCandidates || []);
    setPaymentData(target.paymentData || null);
    setPaymentStatus(target.paymentStatus || null);
    setSpendCapPaise(target.spendCapPaise || 1000000);

    if (target.paymentData?.cartId && target.phase === 'pending-payment') {
      startPolling(target.paymentData.cartId);
    }
  };

  const handleNewChat = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    const newSession = createDefaultSession();
    const updated = [newSession, ...sessions];
    setSessions(updated);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    } catch (_) { }
    setCurrentSessionId(newSession.id);
    localStorage.setItem(ACTIVE_ID_KEY, newSession.id);
    setMessages(newSession.messages);
    setPhase('idle');
    setActiveCartData(null);
    setUpsellCandidates([]);
    setSubstituteCandidates([]);
    setPaymentData(null);
    setPaymentStatus(null);
    setSpendCapPaise(1000000);

    fetch(`${BASE_URL}/api/chat-sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: newSession.id,
        title: newSession.title,
        session_data: newSession
      })
    }).catch(() => { });
  };

  const handleDeleteSession = (e, sessionId) => {
    e?.stopPropagation();
    fetch(`${BASE_URL}/api/chat-sessions/${sessionId}`, { method: 'DELETE' }).catch(() => { });
    const updated = sessions.filter(s => s.id !== sessionId);
    if (updated.length === 0) {
      const fresh = createDefaultSession();
      setSessions([fresh]);
      handleSelectSession(fresh.id);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify([fresh]));
      } catch (_) { }
      return;
    }
    setSessions(updated);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    } catch (_) { }
    if (currentSessionId === sessionId) {
      handleSelectSession(updated[0].id);
    }
  };


  const handleToggleHistory = () => {
    const next = !isHistoryOpen;
    setIsHistoryOpen(next);
    localStorage.setItem('cartpilot_history_open', String(next));
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
            guardrail_reason: `Cart total (₹${(prev.total_paise / 100).toFixed(0)}) exceeds updated spend cap (₹${(newCapPaise / 100).toFixed(0)})`
          }));
        } else {
          setActiveCartData(prev => ({
            ...prev,
            guardrail_reason: `Within spend cap (₹${(prev.total_paise / 100).toFixed(0)} <= ₹${(newCapPaise / 100).toFixed(0)})`
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
    setPaymentData(null);
    setPaymentStatus(null);
    setSubstituteCandidates([]);
    setUpsellCandidates([]);

    try {
      const res = await fetch(`${BASE_URL}/checkout/agent-checkout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: userText,
          spend_cap_paise: spendCapPaise,
          conversation_history: messages.slice(-8).map(m => ({ role: m.role, content: m.content })),
          current_cart: (phase === 'proposal' && activeCartData?.proposed_items) ? activeCartData.proposed_items : []
        })
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Server error');

      if (data.intent?.spend_cap_paise) {
        setSpendCapPaise(data.intent.spend_cap_paise);
      }

      // Handle Substitution offer
      if (data.status === 'substitute_offered') {
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
        const displayMsg = data.message || formatGuardrailNotice(data.reason);
        appendMessage('agent', displayMsg, {
          isAlert: true,
          decisionTrace: data.decision_trace || []
        });
        setPhase('idle');
        setLoading(false);
        return;
      }

      // Cart Approved
      setActiveCartData(data);

      // Handle Upsell Candidates
      const cands = data.upsell ? (data.upsell.candidates || [data.upsell]) : [];
      setUpsellCandidates(cands);

      const msgText = data.message || (data.upsell
        ? `I itemized your cart below! Customers who purchased these items also frequently added:`
        : `I itemized your cart below:`);

      appendMessage('agent', msgText, {
        cartData: data,
        upsellCandidates: cands,
        phase: 'proposal'
      });

      setPhase('proposal');
    } catch (err) {
      appendMessage('agent', `❌ Error: ${err.message}`, { isAlert: true });
    } finally {
      setLoading(false);
    }
  };

  /* ─── Submit Quick Starter Prompt from Welcome Card ─────────────────── */
  const handleQuickPrompt = async (promptText) => {
    if (loading || !promptText) return;
    const userText = promptText.trim();
    setQuery('');
    appendMessage('user', userText);
    setLoading(true);
    setPaymentData(null);
    setPaymentStatus(null);
    setSubstituteCandidates([]);
    setUpsellCandidates([]);

    try {
      const res = await fetch(`${BASE_URL}/checkout/agent-checkout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: userText,
          spend_cap_paise: spendCapPaise,
          conversation_history: messages.slice(-8).map(m => ({ role: m.role, content: m.content })),
          current_cart: (phase === 'proposal' && activeCartData?.proposed_items) ? activeCartData.proposed_items : []
        })
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Server error');

      if (data.intent?.spend_cap_paise) {
        setSpendCapPaise(data.intent.spend_cap_paise);
      }

      // Handle Substitution offer
      if (data.status === 'substitute_offered') {
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
        const displayMsg = data.message || formatGuardrailNotice(data.reason);
        appendMessage('agent', displayMsg, {
          isAlert: true,
          decisionTrace: data.decision_trace || []
        });
        setPhase('idle');
        setLoading(false);
        return;
      }

      // Cart Approved
      setActiveCartData(data);

      // Handle Upsell Candidates
      const cands = data.upsell ? (data.upsell.candidates || [data.upsell]) : [];
      setUpsellCandidates(cands);

      const msgText = data.message || (data.upsell
        ? `I itemized your cart below! Customers who purchased these items also frequently added:`
        : `I itemized your cart below:`);

      appendMessage('agent', msgText, {
        cartData: data,
        upsellCandidates: cands,
        phase: 'proposal'
      });

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
      // ── SCENARIO 1: POST-PURCHASE 1-CLICK ADD-ON (Initial order already paid) ──
      if (phase === 'resolved' || paymentStatus === 'succeeded') {
        const res = await fetch(`${BASE_URL}/checkout/post-purchase-add`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            parent_cart_id: activeCartData.cart_id,
            sku: candidate.sku,
            qty: 1,
            selected_size: candidate.selectedSize
          })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(extractErrorMessage(data, 'Failed to add post-purchase item'));

        if (data.status === 'blocked') {
          appendMessage('agent', `🚫 Guardrail Blocked: ${data.reason}`, { isAlert: true });
          return;
        }

        const addOnPayInfo = {
          cartId: data.cart_id,
          orderId: data.razorpay_order_id,
          paymentLink: data.payment_link || data.payment_url,
          amountPaise: data.amount_paise
        };

        // Set up new Razorpay checkout for the add-on
        setPaymentData(addOnPayInfo);
        setPaymentStatus('created');
        setPhase('pending-payment');
        setActiveCartData(data); // Display the add-on item receipt

        const sizeNote = candidate.selectedSize ? ` (${candidate.selectedSize})` : '';
        appendMessage(
          'agent',
          `📦 **Post-Purchase Add-on Added!** Added **${candidate.name}${sizeNote}** (₹${(data.total_paise / 100).toFixed(0)}) to your dispatch shipment.\nComplete 1-click test checkout below:`,
          {
            cartData: data,
            paymentData: addOnPayInfo,
            paymentStatus: 'created',
            phase: 'pending-payment'
          }
        );

        startPolling(data.cart_id);
        return;
      }

      // ── SCENARIO 2: PRE-PURCHASE CART EXPANSION / SIZING UPDATE (During proposal phase) ──
      const currentItems = activeCartData.proposed_items || [];
      const chosenSize = candidate.selectedSize || candidate.selected_size;
      const existsIndex = currentItems.findIndex(i => i.sku === candidate.sku);
      let updatedItems;

      if (existsIndex !== -1) {
        // Update size of the existing item in the cart without increasing quantity
        updatedItems = currentItems.map((item, idx) => {
          if (idx === existsIndex) {
            return {
              ...item,
              selected_size: chosenSize || item.selected_size
            };
          }
          return item;
        });
      } else {
        // Add fresh item with chosen size
        updatedItems = [...currentItems, {
          sku: candidate.sku,
          name: candidate.name,
          price_paise: candidate.price_paise,
          qty: 1,
          category: candidate.category,
          image_url: candidate.image_url || '',
          metadata: candidate.metadata || {},
          selected_size: chosenSize
        }];
      }

      await syncCartUpdate(updatedItems);
    } catch (err) {
      appendMessage('agent', `❌ Error: ${err.message}`, { isAlert: true });
    } finally {
      setIsUpdatingCart(false);
      setAddingSku(null);
    }
  };


  /* ─── Update Item Quantity directly from Receipt ─────────────────────── */
  const handleUpdateQty = (sku, newQty) => {
    if (!activeCartData?.proposed_items) return;
    const currentItems = activeCartData.proposed_items;
    let updatedItems;
    if (newQty <= 0) {
      updatedItems = currentItems.filter(i => i.sku !== sku);
    } else {
      updatedItems = currentItems.map(i => i.sku === sku ? { ...i, qty: newQty } : i);
    }

    if (updatedItems.length === 0) {
      appendMessage('agent', 'Cart cannot be empty. Please keep at least one item.', { isAlert: true });
      return;
    }
    syncCartUpdate(updatedItems);
  };

  /* ─── Remove Item from Cart ─────────────────────────────────────────── */
  const handleRemoveItem = (sku) => {
    if (!activeCartData?.proposed_items) return;
    const currentItems = activeCartData.proposed_items;
    const updatedItems = currentItems.filter(i => i.sku !== sku);
    if (updatedItems.length === 0) {
      appendMessage('agent', 'Cart cannot be empty. Please keep at least one item.', { isAlert: true });
      return;
    }
    syncCartUpdate(updatedItems);
  };

  /* ─── Synchronize Cart Updates with Backend Guardrail Engine ────────── */
  const syncCartUpdate = async (items) => {
    if (!activeCartData?.cart_id) return;
    setIsUpdatingCart(true);

    // Optimistic local update for instant UI responsiveness
    const optimisticTotal = items.reduce((sum, i) => sum + ((i.price_paise || 0) * (i.qty || 1)), 0);
    const optimisticCart = {
      ...activeCartData,
      proposed_items: items,
      total_paise: optimisticTotal
    };
    setActiveCartData(optimisticCart);
    setMessages(prev => {
      const lastIdx = prev.reduce((acc, m, idx) => (m.role === 'agent' && m.cartData) ? idx : acc, -1);
      if (lastIdx !== -1) {
        const next = [...prev];
        next[lastIdx] = { ...next[lastIdx], cartData: optimisticCart };
        return next;
      }
      return prev;
    });

    try {
      const res = await fetch(`${BASE_URL}/checkout/update-cart`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cart_id: activeCartData.cart_id,
          items: items.map(i => ({
            sku: i.sku,
            qty: i.qty,
            selected_size: i.selected_size || i.selectedSize || null
          }))
        })
      });

      const data = await res.json();
      if (!res.ok) throw new Error(extractErrorMessage(data, 'Cart update error'));

      if (data.status === 'blocked') {
        appendMessage('agent', `🚫 Guardrail Blocked: ${data.reason}`, { isAlert: true });
        return;
      }

      const cartItemSkus = new Set((data.proposed_items || items || []).map(i => i.sku));
      const newUpsells = (data.upsell ? (data.upsell.candidates || [data.upsell]) : []).filter(c => !cartItemSkus.has(c.sku));
      setUpsellCandidates(newUpsells);

      setActiveCartData(data);
      setMessages(prev => {
        const lastIdx = prev.reduce((acc, m, idx) => (m.role === 'agent' && m.cartData) ? idx : acc, -1);
        if (lastIdx !== -1) {
          const next = [...prev];
          next[lastIdx] = { 
            ...next[lastIdx], 
            cartData: data,
            upsellCandidates: newUpsells
          };
          return next;
        }
        return prev;
      });
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

  /* ─── Lock & Finalize Order (Proceed to Razorpay Checkout) ───────────── */
  const handleProceedPayment = async () => {
    if (!activeCartData) return;
    setLoading(true);

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

      const payData = {
        cartId: data.cart_id,
        orderId: data.razorpay_order_id,
        paymentLink: data.payment_link || data.payment_url,
        amountPaise: data.amount_paise
      };

      setPaymentData(payData);
      setPaymentStatus('created');
      setPhase('pending-payment');

      appendMessage('agent', `Your order is locked and ready for payment. Click below to complete test checkout on Razorpay:`, {
        cartData: activeCartData,
        paymentData: payData,
        paymentStatus: 'created',
        phase: 'pending-payment'
      });

      startPolling(data.cart_id);
    } catch (err) {
      appendMessage('agent', `❌ Payment creation failed: ${err.message}`, { isAlert: true });
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
          setPhase('resolved');
          appendMessage('agent', `🎉 **Payment Succeeded!** Your order is confirmed. A live receipt has been logged to the immutable audit trail.`, {
            isSuccess: true,
            cartData: activeCartData,
            paymentData: paymentData,
            paymentStatus: 'succeeded',
            upsellCandidates: upsellCandidates,
            phase: 'resolved'
          });
        }
      }
    } catch (_) {
      // silent retry
    } finally {
      setIsCheckingStatus(false);
    }
  }, [activeCartData, paymentData, upsellCandidates]);

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
        setPaymentStatus('refunded');
        setPhase('refunded');
        appendMessage('agent', `✅ **Refund Processed**: ${data.reason}\n\n• **Order Status**: \`${data.order_status}\`\n• **Gateway Refund ID**: \`${data.refund_id}\`\n• **Refund Amount**: ₹${((data.amount_refunded_paise || 0) / 100).toFixed(2)}`, {
          isSuccess: true,
          isRefunded: true,
          refundId: data.refund_id,
          cartData: activeCartData,
          paymentStatus: 'refunded',
          phase: 'refunded'
        });
      } else if (data.status === 'cancelled') {
        setPaymentStatus('cancelled');
        appendMessage('agent', `🚫 **Order Cancelled**: ${data.reason}\n\n• **Order Status**: \`${data.order_status}\``, { isAlert: true });
      } else if (data.status === 'review_required') {
        appendMessage('agent', `📋 **Resolution Review Required**: ${data.reason}\n\n• **Return Status**: \`${data.return_status || 'REVIEW_REQUIRED'}\`\n• **Order Status**: \`${data.order_status}\``, { isAlert: true });
      } else if (data.status === 'inform') {
        appendMessage('agent', `ℹ️ **Policy Information**:\n\n${data.reason}`);
      } else {
        appendMessage('agent', `⚠️ **Resolution Decision**: ${data.reason}`, { isAlert: true });
      }
    } catch (err) {
      appendMessage('agent', `❌ ${err.message}`, { isAlert: true });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat-layout">
      {/* ── Left Side: ChatGPT-Style Collapsible Chat History Sidebar ── */}
      <ChatHistorySidebar
        sessions={sessions}
        currentSessionId={currentSessionId}
        isOpen={isHistoryOpen}
        onClose={() => handleToggleHistory()}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
        searchQuery={historySearch}
        onSearchChange={setHistorySearch}
      />

      {/* ── Main Chat Stream Column ── */}
      <div className="chat-window">
        <div className="chat-header">
          <div className="chat-header-left">
            <button
              type="button"
              className={`btn-history-book-toggle ${isHistoryOpen ? 'active' : ''}`}
              onClick={handleToggleHistory}
              title={isHistoryOpen ? 'Collapse Chat History' : 'Open Chat History'}
            >
              <PanelLeftClose size={16} />
            </button>
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

            <button
              type="button"
              className="btn-history-toggle"
              onClick={handleNewChat}
              title="Start a new shopping conversation"
            >
              <Plus size={13} />
              <span>New Chat</span>
            </button>
          </div>
        </div>

        <div className="chat-stream">
          {(() => {
            const lastAgentIdx = messages.reduce((acc, m, idx) => m.role === 'agent' ? idx : acc, -1);
            return messages.map((msg, i) => {
              const isLatestAgent = i === lastAgentIdx;
              const messageCartData = msg.cartData || (isLatestAgent ? activeCartData : null);
              const messagePaymentData = msg.paymentData || (isLatestAgent ? paymentData : null);
              const messagePaymentStatus = msg.paymentStatus || (isLatestAgent ? paymentStatus : null);
              
              const currentCartSkus = new Set(messageCartData?.proposed_items?.map(item => item.sku) || []);
              const rawUpsells = isLatestAgent ? (upsellCandidates.length > 0 ? upsellCandidates : (msg.upsellCandidates || [])) : (msg.upsellCandidates || []);
              const rawSubstitutes = isLatestAgent ? (substituteCandidates.length > 0 ? substituteCandidates : (msg.substituteCandidates || [])) : (msg.substituteCandidates || []);
              const messageUpsells = rawUpsells.filter(c => !currentCartSkus.has(c.sku));
              const messageSubstitutes = rawSubstitutes.filter(c => !currentCartSkus.has(c.sku));

              const isRefundedMsg = msg.isRefunded || messagePaymentStatus === 'refunded' || (isLatestAgent && (phase === 'refunded' || paymentStatus === 'refunded'));

              const isInteractiveProposal = isLatestAgent && phase === 'proposal' && !messagePaymentData;
              const canRequestRefund = !isRefundedMsg && (messagePaymentStatus === 'succeeded' || (isLatestAgent && phase === 'resolved')) && phase !== 'refunded' && paymentStatus !== 'refunded';

              return (
                <div key={i} className={`msg-row ${msg.role}`}>
                  {msg.role === 'user' ? (
                    <div className="user-bubble">{msg.content}</div>
                  ) : (msg.isWelcome || (i === 0 && !messageCartData && messages.length === 1)) ? (
                    <WelcomeHeroCard onSelectPrompt={handleQuickPrompt} />
                  ) : (
                    <div className={`agent-bubble ${msg.isAlert ? 'alert-bubble' : msg.isSuccess ? 'success-bubble' : ''}`}>
                      <div className="agent-text-content">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>

                      {msg.decisionTrace && msg.decisionTrace.length > 0 && !messageCartData && (
                        <LangGraphTraceViewer trace={msg.decisionTrace} />
                      )}

                      {messageCartData && (
                        <>
                          <ReceiptCard
                            cartData={messageCartData}
                            spendCapPaise={spendCapPaise}
                            onSelectDetail={setSelectedProductForDetail}
                            isRefunded={isRefundedMsg}
                            isInteractive={isInteractiveProposal}
                            onUpdateQty={handleUpdateQty}
                            onRemoveItem={handleRemoveItem}
                            onProceedPayment={handleProceedPayment}
                            isUpdating={isUpdatingCart}
                          />

                          {/* Substitution Carousel on active proposal */}
                          {messageSubstitutes.length > 0 && isInteractiveProposal && (
                            <ScrollSnapCarousel
                              title="In-Stock Semantic Alternatives"
                              candidates={messageSubstitutes}
                              onAddItem={handleAddCarouselItem}
                              onSelectDetail={setSelectedProductForDetail}
                              currentCartTotalPaise={messageCartData.total_paise || 0}
                              spendCapPaise={spendCapPaise}
                              addingSku={addingSku}
                              cartSkus={currentCartSkus}
                            />
                          )}

                          {/* Cross-Sell Carousel (only if not refunded) */}
                          {messageUpsells.length > 0 && !isRefundedMsg && (isInteractiveProposal || (isLatestAgent && phase === 'resolved')) && (
                            <ScrollSnapCarousel
                              title={phase === 'resolved' ? '🎁 Post-Purchase 1-Click Add-on Recommendations' : 'Growth Agent Complementary Picks'}
                              candidates={messageUpsells}
                              onAddItem={handleAddCarouselItem}
                              onSelectDetail={setSelectedProductForDetail}
                              currentCartTotalPaise={messageCartData.total_paise || 0}
                              spendCapPaise={spendCapPaise}
                              addingSku={addingSku}
                              cartSkus={currentCartSkus}
                            />
                          )}

                          {/* Razorpay Payment Card */}
                          {messagePaymentData && (
                            <RazorpayPaymentCard
                              paymentData={messagePaymentData}
                              paymentStatus={isRefundedMsg ? 'refunded' : messagePaymentStatus}
                              onCheckStatus={() => checkPaymentStatus(messagePaymentData.cartId)}
                              isChecking={isCheckingStatus}
                            />
                          )}


                          {/* Refund button (hidden once refunded) */}
                          {canRequestRefund && (
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
              );
            });
          })()}



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
        isAlreadyInCart={activeCartData?.proposed_items?.some(i => i.sku === selectedProductForDetail?.sku)}
      />
    </div>
  );
}




