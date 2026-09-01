import React, { useState, useEffect, useRef } from 'react';
import { useLocation } from 'wouter';
import { useAuth } from '../../contexts/AuthContext';
import {
  Send, Sparkles, ShieldCheck, AlertTriangle, CheckCircle, RefreshCcw,
  ExternalLink, Trash2, Plus, Minus, ArrowRight, CornerDownLeft,
  RotateCcw, ShoppingBag, DollarSign, MessageSquare, PanelLeftClose, PanelLeft,
  ChevronDown, ChevronRight, LogOut, Store, CreditCard, Lock, ShoppingCart,
  Search, Info, Star, Package, Layers, Tag, X, Check
} from 'lucide-react';
import { toast } from 'sonner';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const SUGGESTIONS = [
  'need a Hand Blender and a Honey Jar for my morning smoothies',
  'iPhone with silicone case and fast charger',
  'Casual blue shirt and leather loafers',
  'Hydrating face serum and fragrance',
  'Chef knife and wooden cutting board'
];

const NODE_CONFIG: Record<string, { label: string; icon: string }> = {
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

interface ChatMessage {
  role: 'buyer' | 'agent';
  content: string;
  isWelcome?: boolean;
  timestamp?: number;
  recommendations?: Recommendation[];
  cart?: any;
  decisionTrace?: TraceStep[];
  paymentLink?: string;
}

interface CartItem {
  sku: string;
  name: string;
  qty: number;
  price_paise: number;
  category?: string;
  image_url?: string;
  selectedSize?: string;
  selected_size?: string;
  metadata?: any;
}

interface Recommendation {
  sku: string;
  name: string;
  price_paise: number;
  price_rupees?: number;
  category: string;
  reason?: string;
  tier?: string;
  lift?: number;
  image_url?: string;
  description?: string;
  selectedSize?: string;
  selected_size?: string;
  stock?: number;
  metadata?: {
    brand?: string;
    rating?: number;
    weight?: number;
    dimensions?: { width: number; height: number; depth: number };
    warranty?: string;
    shipping?: string;
    returnPolicy?: string;
    availabilityStatus?: string;
    variantLabel?: string;
    sizes?: string[];
    options?: string[];
    images?: string[];
  };
}

interface TraceStep {
  node: string;
  tool?: string;
  input_summary?: string;
  result_summary?: string;
  state_transition?: string;
  outcome?: string;
  timestamp?: string;
}

interface ChatSessionItem {
  id: string;
  title: string;
  messages: ChatMessage[];
  activeCart: {
    items: CartItem[];
    total_paise: number;
    spend_cap_paise: number;
    guardrail_status: string;
    guardrail_reason?: string;
    mandate_id?: string;
  } | null;
  recommendations: Recommendation[];
  decisionTrace: TraceStep[];
  paymentData?: any;
  createdAt: number;
  updatedAt: number;
}

/* ─── 1. CHAT HISTORY SIDEBAR COMPONENT (ChatGPT / Gemini Style) ─── */
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
}: {
  sessions: ChatSessionItem[];
  currentSessionId: string;
  isOpen: boolean;
  onClose: () => void;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onDeleteSession: (e: React.MouseEvent, id: string) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
}) {
  const filteredSessions = sessions
    .filter(s => {
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (s.title && s.title.toLowerCase().includes(q)) ||
        (s.messages && s.messages.some(m => m.content && m.content.toLowerCase().includes(q)));
    })
    .sort((a, b) => (b.updatedAt || b.createdAt || 0) - (a.updatedAt || a.createdAt || 0));

  if (!isOpen) return null;

  return (
    <aside className="w-72 bg-white border-r border-[#ebeaf0] flex flex-col h-[calc(100vh-64px)] sticky top-16 z-20 shrink-0 shadow-sm transition-all">
      {/* Header */}
      <div className="p-3.5 border-b border-[#ebeaf0] flex items-center justify-between bg-[#faf9fd]">
        <div className="flex items-center gap-2 text-xs font-bold text-ink">
          <MessageSquare size={16} className="text-violet" />
          <span>Chat History</span>
          <span className="px-1.5 py-0.5 rounded-full bg-[#eeeaff] text-violet text-[10px] font-extrabold">
            {sessions.length}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 text-muted hover:text-ink hover:bg-[#f0eff4] rounded-lg transition-all"
          title="Collapse Chat History"
        >
          <PanelLeftClose size={16} />
        </button>
      </div>

      {/* New Chat Button & Search */}
      <div className="p-3 border-b border-[#ebeaf0] space-y-2">
        <button
          onClick={onNewChat}
          className="w-full h-10 rounded-xl bg-white border-2 border-dashed border-[#d9d5ec] hover:border-violet text-ink hover:text-violet font-bold text-xs flex items-center justify-center gap-2 shadow-xs transition-all hover:bg-[#fbfaff]"
        >
          <Plus size={15} className="text-violet" />
          <span>New Shopping Chat</span>
        </button>

        {sessions.length > 2 && (
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder="Search chats..."
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              className="w-full h-8 pl-7 pr-3 bg-[#f8f8fb] border border-[#ebeaf0] rounded-lg text-xs text-ink outline-none focus:border-violet"
            />
          </div>
        )}
      </div>

      {/* Session List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {filteredSessions.length === 0 ? (
          <div className="p-4 text-center text-xs text-muted">
            {searchQuery ? 'No matching chats found.' : 'No saved sessions yet. Start shopping!'}
          </div>
        ) : (
          filteredSessions.map((s) => {
            const isActive = s.id === currentSessionId;
            const itemCount = s.activeCart?.items?.length || 0;
            const totalRupees = s.activeCart?.total_paise ? (s.activeCart.total_paise / 100).toFixed(0) : null;
            const timeStr = new Date(s.updatedAt || s.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

            return (
              <div
                key={s.id}
                onClick={() => onSelectSession(s.id)}
                className={`group relative p-2.5 rounded-xl cursor-pointer transition-all flex items-start justify-between gap-2 border ${
                  isActive
                    ? 'bg-[#f4f0ff] border-[#d8cdfa] text-ink shadow-xs'
                    : 'bg-transparent border-transparent hover:bg-[#fbfafc] hover:border-[#ebeaf0] text-muted hover:text-ink'
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-bold truncate text-ink">
                    {s.title || 'Shopping Request'}
                  </div>
                  <div className="flex items-center gap-1.5 text-[10px] text-muted mt-1">
                    <span>{timeStr}</span>
                    {totalRupees ? (
                      <span className="px-1.5 py-0.2 rounded bg-[#e6f4ea] text-[#1b6b47] font-semibold">
                        ₹{totalRupees} ({itemCount})
                      </span>
                    ) : null}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={(e) => onDeleteSession(e, s.id)}
                  title="Delete chat"
                  className="opacity-0 group-hover:opacity-100 p-1 text-muted hover:text-red-600 rounded-md hover:bg-white transition-all shrink-0"
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

/* ─── 2. PRODUCT DETAILS & VARIANT SELECTOR MODAL COMPONENT ─── */
function ProductDetailModal({
  product,
  isOpen,
  onClose,
  onAddToCart,
  currentCartTotalPaise,
  spendCapPaise,
  isAlreadyInCart
}: {
  product: Recommendation | CartItem | null;
  isOpen: boolean;
  onClose: () => void;
  onAddToCart: (item: any, size: string) => void;
  currentCartTotalPaise: number;
  spendCapPaise: number;
  isAlreadyInCart: boolean;
}) {
  if (!isOpen || !product) return null;

  const metadata = (product as any).metadata || {};
  const options = metadata.sizes || metadata.options || ['Standard Edition', 'Pro Bundle'];
  const [selectedOption, setSelectedOption] = useState(
    (product as any).selectedSize || (product as any).selected_size || options[0] || 'Standard'
  );
  const variantLabel = metadata.variantLabel || 'Variant / Size';

  const pricePaise = product.price_paise || ((product as any).price_rupees ? (product as any).price_rupees * 100 : 0);
  const priceRupees = (pricePaise / 100).toFixed(2);
  const remainingBudgetPaise = Math.max(0, spendCapPaise - currentCartTotalPaise);
  const wouldExceed = !isAlreadyInCart && pricePaise > remainingBudgetPaise;

  const handleAdd = () => {
    onAddToCart({ ...product, price_paise: pricePaise }, selectedOption);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-xs z-50 flex items-center justify-center p-4">
      <div
        className="bg-white rounded-2xl max-w-xl w-full max-h-[90vh] flex flex-col shadow-2xl border border-[#ebeaf0] overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-[#ebeaf0] flex items-center justify-between bg-[#faf9fd]">
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider bg-[#eeeaff] text-violet">
              {product.category || 'Merchandise'}
            </span>
            {metadata.brand && (
              <span className="text-xs font-semibold text-muted">by {metadata.brand}</span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-muted hover:text-ink hover:bg-[#ebeaf0] rounded-lg transition-all"
          >
            <X size={18} />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="p-6 overflow-y-auto space-y-5">
          {/* Main Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-5 items-start">
            {/* Image */}
            <div className="sm:col-span-5 aspect-square rounded-xl bg-[#f8f8fb] border border-[#ebeaf0] overflow-hidden flex items-center justify-center p-2">
              <img
                src={product.image_url || 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400'}
                alt={product.name}
                className="w-full h-full object-contain"
                onError={(e: any) => {
                  e.target.src = 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400';
                }}
              />
            </div>

            {/* Info */}
            <div className="sm:col-span-7 space-y-2.5">
              <h3 className="font-display text-lg font-bold text-ink leading-snug">
                {product.name}
              </h3>

              <div className="flex items-center gap-2 flex-wrap text-xs">
                <span className="flex items-center gap-1 font-bold px-2 py-0.5 rounded bg-[#fff7e6] text-[#b25e00] border border-[#ffe3b3]">
                  <Star size={12} className="fill-[#b25e00]" />
                  {metadata.rating || '4.6'} / 5.0
                </span>
                <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald">
                  <CheckCircle size={13} />
                  {metadata.availabilityStatus || 'In Stock'} ({metadata.stock || (product as any).stock || 45} units)
                </span>
              </div>

              <div className="font-display text-2xl font-extrabold text-violet pt-1">
                ₹{priceRupees}
              </div>

              {(product as any).description && (
                <p className="text-xs text-muted leading-relaxed">
                  {(product as any).description}
                </p>
              )}
            </div>
          </div>

          {/* Variant Selection */}
          {options.length > 0 && (
            <div className="p-4 rounded-xl bg-[#fbfafc] border border-[#ebeaf0] space-y-2">
              <div className="flex items-center justify-between text-xs font-bold">
                <span className="text-ink">Select {variantLabel}:</span>
                <span className="text-violet">{selectedOption}</span>
              </div>
              <div className="flex flex-wrap gap-2 pt-1">
                {options.map((opt: string) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setSelectedOption(opt)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition-all ${
                      selectedOption === opt
                        ? 'bg-violet text-white border-violet shadow-xs'
                        : 'bg-white border-[#ebeaf0] text-ink hover:border-violet/40'
                    }`}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Specifications Table */}
          <div>
            <h4 className="text-[11px] font-extrabold uppercase tracking-wider text-muted mb-2">
              Product Specifications & Details
            </h4>
            <div className="border border-[#ebeaf0] rounded-xl overflow-hidden text-xs">
              <div className="divide-y divide-[#ebeaf0]">
                <div className="flex justify-between px-3 py-2 bg-[#faf9fd]">
                  <span className="text-muted font-medium">SKU Code</span>
                  <span className="font-mono font-bold text-ink">{product.sku}</span>
                </div>
                {metadata.brand && (
                  <div className="flex justify-between px-3 py-2 bg-white">
                    <span className="text-muted font-medium">Brand</span>
                    <span className="font-bold text-ink">{metadata.brand}</span>
                  </div>
                )}
                {metadata.warranty && (
                  <div className="flex justify-between px-3 py-2 bg-[#faf9fd]">
                    <span className="text-muted font-medium">Warranty</span>
                    <span className="font-bold text-ink">{metadata.warranty}</span>
                  </div>
                )}
                {metadata.shipping && (
                  <div className="flex justify-between px-3 py-2 bg-white">
                    <span className="text-muted font-medium">Shipping Time</span>
                    <span className="font-bold text-ink">{metadata.shipping}</span>
                  </div>
                )}
                {metadata.returnPolicy && (
                  <div className="flex justify-between px-3 py-2 bg-[#faf9fd]">
                    <span className="text-muted font-medium">Return Policy</span>
                    <span className="font-bold text-ink">{metadata.returnPolicy}</span>
                  </div>
                )}
                {metadata.dimensions && (
                  <div className="flex justify-between px-3 py-2 bg-white">
                    <span className="text-muted font-medium">Dimensions (W×H×D)</span>
                    <span className="font-bold text-ink">
                      {metadata.dimensions.width} × {metadata.dimensions.height} × {metadata.dimensions.depth} cm
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-[#ebeaf0] bg-[#faf9fd] flex items-center justify-between gap-4">
          <div>
            <span className="text-[11px] text-muted">Selected Price</span>
            <div className="font-display text-lg font-bold text-ink">₹{priceRupees}</div>
          </div>

          <button
            onClick={handleAdd}
            disabled={wouldExceed}
            className={`h-11 px-6 rounded-xl font-bold text-xs flex items-center gap-2 shadow-md transition-all ${
              wouldExceed
                ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
                : 'bg-violet hover:bg-[#6849d8] text-white'
            }`}
          >
            {wouldExceed ? (
              <span>Exceeds Spend Cap (₹{(spendCapPaise / 100).toFixed(0)})</span>
            ) : (
              <>
                <Plus size={15} />
                <span>Add ({selectedOption}) to Order</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── 3. IN-CHAT RECOMMENDATIONS CAROUSEL COMPONENT ─── */
function InChatRecommendations({
  recommendations,
  onSelectDetail,
  onAddWithVariant,
  selectedVariants,
  onSelectVariant,
  spendCapPaise,
  currentCartTotalPaise,
  cartSkus
}: {
  recommendations: Recommendation[];
  onSelectDetail: (rec: Recommendation) => void;
  onAddWithVariant: (rec: Recommendation, variant?: string) => void;
  selectedVariants: Record<string, string>;
  onSelectVariant: (sku: string, variant: string) => void;
  spendCapPaise: number;
  currentCartTotalPaise: number;
  cartSkus: Set<string>;
}) {
  if (!recommendations || recommendations.length === 0) return null;

  return (
    <div className="mt-3.5 pt-3 border-t border-[#ebeaf0] w-full">
      <div className="flex items-center justify-between mb-2.5 px-0.5">
        <div className="flex items-center gap-1.5 text-xs font-bold text-ink">
          <Sparkles size={14} className="text-violet" />
          <span>Recommended for You</span>
          <span className="px-1.5 py-0.2 rounded-full bg-[#eeeaff] text-violet text-[10px] font-extrabold">
            {recommendations.length}
          </span>
        </div>
        <span className="text-[10px] text-muted hidden sm:inline">Click card for details & sizing · Swipe to explore</span>
      </div>

      <div className="flex gap-3 overflow-x-auto pb-2 scroll-smooth no-scrollbar">
        {recommendations.map((rec) => {
          const pricePaise = rec.price_paise || ((rec.price_rupees || 0) * 100);
          const priceRupees = (pricePaise / 100).toFixed(2);
          const wouldExceed = (currentCartTotalPaise + pricePaise) > spendCapPaise;
          const isInCart = cartSkus.has(rec.sku);

          const options = rec.metadata?.sizes || rec.metadata?.options || ['Standard Edition', 'Pro Bundle'];
          const currentVariant = selectedVariants[rec.sku] || options[0];

          return (
            <div
              key={rec.sku}
              className={`w-[220px] shrink-0 bg-white rounded-xl border p-3 flex flex-col justify-between shadow-xs hover:shadow-md transition-all ${
                wouldExceed ? 'border-amber-200 bg-[#fffdfa]' : 'border-[#ebeaf0] hover:border-violet/50'
              }`}
            >
              <div
                className="cursor-pointer group space-y-2"
                onClick={() => onSelectDetail(rec)}
                title="Click for product details, sizing & specifications"
              >
                {/* Product Thumbnail */}
                <div className="w-full h-28 rounded-lg bg-[#f8f8fb] border border-[#f0eff4] overflow-hidden flex items-center justify-center p-1.5">
                  <img
                    src={rec.image_url || 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=300'}
                    alt={rec.name}
                    className="w-full h-full object-contain group-hover:scale-105 transition-transform duration-200"
                    onError={(e: any) => {
                      e.target.src = 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=300';
                    }}
                  />
                </div>

                {/* Details */}
                <div>
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-[9px] font-extrabold uppercase tracking-wider px-1.5 py-0.2 rounded bg-[#eeeaff] text-violet truncate">
                      {rec.category || 'Picks'}
                    </span>
                    <span className="text-[10px] text-muted flex items-center gap-0.5 group-hover:text-violet">
                      <Info size={11} /> Info
                    </span>
                  </div>

                  <h4 className="text-xs font-bold text-ink truncate group-hover:text-violet transition-colors mt-1">
                    {rec.name}
                  </h4>

                  <div className="font-display text-sm font-extrabold text-violet mt-0.5">
                    ₹{priceRupees}
                  </div>
                </div>

                {/* Rationale Quote */}
                {rec.reason && (
                  <p className="text-[10px] text-muted bg-[#f8f8fb] p-1.5 rounded-lg border border-[#f0eff4] line-clamp-2 leading-tight">
                    💡 {rec.reason}
                  </p>
                )}
              </div>

              {/* Variant Selector Pills */}
              <div className="mt-2 pt-2 border-t border-[#f4f3f8] space-y-2">
                {options.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {options.map((opt) => (
                      <button
                        key={opt}
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectVariant(rec.sku, opt);
                        }}
                        className={`px-1.5 py-0.5 rounded text-[9px] font-bold border transition-all ${
                          currentVariant === opt
                            ? 'bg-violet text-white border-violet'
                            : 'bg-[#faf9fd] border-[#ebeaf0] text-muted hover:text-ink'
                        }`}
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                )}

                {/* Add to Order Button */}
                <button
                  type="button"
                  onClick={() => onAddWithVariant(rec, currentVariant)}
                  disabled={wouldExceed}
                  className={`w-full h-8 rounded-lg text-xs font-bold flex items-center justify-center gap-1 transition-all shadow-xs ${
                    wouldExceed
                      ? 'bg-gray-100 text-gray-400 border border-gray-200 cursor-not-allowed'
                      : isInCart
                      ? 'bg-[#e6f4ea] text-[#1b6b47] hover:bg-[#d8edd9]'
                      : 'bg-violet text-white hover:bg-[#6849d8]'
                  }`}
                >
                  <Plus size={13} />
                  <span>{isInCart ? 'Add Another' : 'Add to Order'}</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── 4. SPEND CAP ADJUSTMENT MODAL COMPONENT ─── */
function SpendCapModal({
  isOpen,
  onClose,
  currentSpendCapPaise,
  onSaveSpendCap
}: {
  isOpen: boolean;
  onClose: () => void;
  currentSpendCapPaise: number;
  onSaveSpendCap: (newPaise: number) => void;
}) {
  const [capRupees, setCapRupees] = useState(String(Math.round(currentSpendCapPaise / 100)));
  const presets = [1000, 2500, 5000, 10000, 25000, 50000];

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl border border-[#ebeaf0] animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-display text-base font-bold text-ink">Set Buyer Spend Cap</h3>
          <button onClick={onClose} className="p-1 text-muted hover:text-ink rounded-lg">
            <X size={16} />
          </button>
        </div>
        <p className="text-xs text-muted mb-4">
          Autonomous purchases under this limit execute with zero friction.
        </p>

        {/* Input */}
        <div className="relative mb-3">
          <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-sm font-bold text-muted">₹</span>
          <input
            type="number"
            value={capRupees}
            onChange={(e) => setCapRupees(e.target.value)}
            className="w-full h-11 pl-8 pr-4 bg-[#fbfafc] border border-[#ebeaf0] rounded-xl text-sm font-bold text-ink outline-none focus:border-violet"
            autoFocus
          />
        </div>

        {/* Quick Presets */}
        <div className="flex flex-wrap gap-1.5 mb-5">
          {presets.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setCapRupees(String(p))}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all ${
                capRupees === String(p)
                  ? 'bg-violet text-white border-violet'
                  : 'bg-[#f8f8fb] text-muted hover:text-ink border-[#ebeaf0]'
              }`}
            >
              ₹{p.toLocaleString()}
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 rounded-xl border border-[#ebeaf0] text-xs font-semibold text-muted hover:text-ink"
          >
            Cancel
          </button>
          <button
            onClick={() => {
              const val = parseInt(capRupees, 10);
              if (!isNaN(val) && val > 0) {
                onSaveSpendCap(val * 100);
                onClose();
              }
            }}
            className="flex-1 py-2.5 rounded-xl bg-violet text-white text-xs font-bold shadow-md hover:bg-[#6849d8]"
          >
            Save Limit
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── 4. MAIN BUYER APP ORCHESTRATOR ─── */
export default function BuyerApp() {
  const { user, logout } = useAuth();
  const [, setLocation] = useLocation();

  // Sessions & History
  const [sessions, setSessions] = useState<ChatSessionItem[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string>(() => `sess_${Date.now()}`);
  const [isHistoryOpen, setIsHistoryOpen] = useState<boolean>(() => localStorage.getItem('cartpilot_buyer_history_open') !== 'false');
  const [historySearch, setHistorySearch] = useState('');

  // Conversation & Cart
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'agent',
      isWelcome: true,
      content: 'Hello! I am your CartPilot personal shopping agent. Tell me what you need (e.g. "I want a Hand Blender and Honey Jar", "iPhone with case and charger"), and I will curate your cart with live receipts, spend cap verification, and smart recommendations.',
      timestamp: Date.now()
    }
  ]);

  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeCart, setActiveCart] = useState<{
    items: CartItem[];
    total_paise: number;
    spend_cap_paise: number;
    guardrail_status: string;
    guardrail_reason?: string;
    mandate_id?: string;
  } | null>(null);

  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [decisionTrace, setDecisionTrace] = useState<TraceStep[]>([]);
  const [showTrace, setShowTrace] = useState(false);
  const [paymentData, setPaymentData] = useState<{
    payment_link?: string;
    mandate_id?: string;
    amount_rupees?: number;
    status?: string;
  } | null>(null);

  // Modals & Variant State
  const [inspectingProduct, setInspectingProduct] = useState<Recommendation | CartItem | null>(null);
  const [selectedVariants, setSelectedVariants] = useState<Record<string, string>>({});
  const [spendCapPaise, setSpendCapPaise] = useState(user?.spendCapPaise || 1000000);
  const [showSpendCapModal, setShowSpendCapModal] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load chat sessions & starter curated recommendations from backend & localStorage on mount
  useEffect(() => {
    const fetchSessionsAndStarters = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/chat-sessions`);
        if (res.ok) {
          const data = await res.json();
          if (data.sessions && Array.isArray(data.sessions)) {
            setSessions(data.sessions);
          }
        }
      } catch (err) {
        console.warn('Failed to load remote chat sessions, fallback to local', err);
      }

      // Local fallback for sessions
      try {
        const local = localStorage.getItem('cartpilot_buyer_sessions');
        if (local) setSessions(JSON.parse(local));
      } catch (e) {}

      // Fetch starter catalog recommendations
      try {
        const catRes = await fetch(`${API_BASE}/api/console/catalog`);
        if (catRes.ok) {
          const catData = await catRes.json();
          const items = (catData.items || []).filter((i: any) => i.image_url).slice(0, 4);
          if (items.length > 0) {
            const starterRecs: Recommendation[] = items.map((it: any) => ({
              sku: it.sku,
              name: it.name,
              price_paise: it.price_paise,
              category: it.category,
              image_url: it.image_url,
              description: it.description,
              metadata: it.metadata,
              tier: 'trending_curated',
              reason: 'Popular store essential curated by CartPilot agent.'
            }));
            setRecommendations(starterRecs);
            setMessages(prev =>
              prev.map((m, idx) =>
                idx === 0 && m.isWelcome && (!m.recommendations || m.recommendations.length === 0)
                  ? { ...m, recommendations: starterRecs }
                  : m
              )
            );
          }
        }
      } catch (e) {}
    };

    fetchSessionsAndStarters();
  }, []);

  // Save session when messages / cart change
  useEffect(() => {
    if (messages.length <= 1 && !activeCart) return;

    const firstUserMsg = messages.find(m => m.role === 'buyer')?.content || 'Shopping Session';
    const title = firstUserMsg.length > 35 ? firstUserMsg.slice(0, 32) + '…' : firstUserMsg;

    const currentSession: ChatSessionItem = {
      id: currentSessionId,
      title,
      messages,
      activeCart,
      recommendations,
      decisionTrace,
      paymentData,
      createdAt: Date.now(),
      updatedAt: Date.now()
    };

    setSessions(prev => {
      const idx = prev.findIndex(s => s.id === currentSessionId);
      const updated = idx >= 0
        ? prev.map(s => s.id === currentSessionId ? { ...s, ...currentSession, updatedAt: Date.now() } : s)
        : [currentSession, ...prev];

      try {
        localStorage.setItem('cartpilot_buyer_sessions', JSON.stringify(updated));
      } catch (e) {}

      return updated;
    });

    // Async persist to backend SQLite
    fetch(`${API_BASE}/api/chat-sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: currentSessionId,
        title,
        session_data: currentSession
      })
    }).catch(() => {});
  }, [messages, activeCart, recommendations, decisionTrace, paymentData, currentSessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Toggle History Sidebar
  const handleToggleHistory = () => {
    const next = !isHistoryOpen;
    setIsHistoryOpen(next);
    localStorage.setItem('cartpilot_buyer_history_open', String(next));
  };

  // Start New Chat
  const handleNewChat = () => {
    const newId = `sess_${Date.now()}`;
    setCurrentSessionId(newId);
    setMessages([
      {
        role: 'agent',
        isWelcome: true,
        content: 'Hello! I am your CartPilot personal shopping agent. Tell me what you need (e.g. "I want a Hand Blender and Honey Jar", "iPhone with case and charger"), and I will curate your cart with live receipts, spend cap verification, and smart recommendations.',
        timestamp: Date.now()
      }
    ]);
    setActiveCart(null);
    setRecommendations([]);
    setDecisionTrace([]);
    setPaymentData(null);
    toast.success('Started a fresh shopping session');
  };

  // Select an existing chat session
  const handleSelectSession = (id: string) => {
    const sess = sessions.find(s => s.id === id);
    if (!sess) return;

    setCurrentSessionId(sess.id);
    setMessages(sess.messages || []);
    setActiveCart(sess.activeCart || null);
    setRecommendations(sess.recommendations || []);
    setDecisionTrace(sess.decisionTrace || []);
    setPaymentData(sess.paymentData || null);
    toast.info(`Loaded "${sess.title}"`);
  };

  // Delete chat session
  const handleDeleteSession = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setSessions(prev => prev.filter(s => s.id !== id));

    try {
      await fetch(`${API_BASE}/api/chat-sessions/${id}`, { method: 'DELETE' });
    } catch (err) {}

    if (id === currentSessionId) {
      handleNewChat();
    }
    toast.success('Chat deleted');
  };

  // Send Message / Add Product Query
  const handleSendMessage = async (textToSend?: string) => {
    const query = (textToSend || input).trim();
    if (!query || loading) return;

    const userMsg: ChatMessage = { role: 'buyer', content: query, timestamp: Date.now() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: query,
          spend_cap_paise: spendCapPaise,
          current_cart: activeCart?.items || [],
        }),
      });

      if (!res.ok) {
        throw new Error(`API returned ${res.status}`);
      }

      const data = await res.json();

      const agentReply: ChatMessage = {
        role: 'agent',
        content: data.reply || data.assistant_message || 'I have updated your shopping cart.',
        recommendations: data.recommendations || [],
        cart: data.cart,
        decisionTrace: data.decision_trace,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, agentReply]);

      if (data.cart) {
        setActiveCart({
          items: data.cart.items || [],
          total_paise: data.cart.total_paise || 0,
          spend_cap_paise: data.cart.spend_cap_paise || spendCapPaise,
          guardrail_status: data.cart.guardrail_status || 'approved',
          guardrail_reason: data.cart.guardrail_reason,
          mandate_id: data.cart.mandate_id,
        });
      }

      if (data.recommendations && Array.isArray(data.recommendations)) {
        setRecommendations(data.recommendations);
      }

      if (data.decision_trace && Array.isArray(data.decision_trace)) {
        setDecisionTrace(data.decision_trace);
      }

      if (data.payment_link || data.payment_mandate) {
        setPaymentData({
          payment_link: data.payment_link || 'https://rzp.io/l/demo_cartpilot',
          mandate_id: data.mandate_id || data.cart?.mandate_id || 'MANDATE_AUTH_01',
          amount_rupees: Math.round((data.cart?.total_paise || 0) / 100),
          status: 'READY',
        });
      }
    } catch (err: any) {
      toast.error('Could not reach backend API: ' + (err.message || 'Check server'));
      setMessages((prev) => [
        ...prev,
        {
          role: 'agent',
          content: '⚠️ I encountered an error connecting to the CartPilot agent. Please ensure the backend is running.',
          timestamp: Date.now(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  // Add item directly to cart (no LLM call) with fresh recommendations after
  const handleAddCrossSellWithVariant = async (item: Recommendation, variant?: string) => {
    const chosenVariant = variant || selectedVariants[item.sku] || item.metadata?.sizes?.[0] || 'Standard';
    const priceRupees = ((item.price_paise || 0) / 100).toFixed(2);
    const label = chosenVariant && chosenVariant !== 'Standard Edition' && chosenVariant !== 'Standard'
      ? `${item.name} – ${chosenVariant}`
      : item.name;

    // 1. Directly add to cart state
    setActiveCart((prev) => {
      const existing = prev?.items || [];
      const idx = existing.findIndex((ci) => ci.sku === item.sku && (ci as any).selectedSize === chosenVariant);
      let updatedItems;
      if (idx >= 0) {
        updatedItems = existing.map((ci, i) => i === idx ? { ...ci, qty: ci.qty + 1 } : ci);
      } else {
        updatedItems = [
          ...existing,
          {
            sku: item.sku,
            name: item.name,
            qty: 1,
            price_paise: item.price_paise || 0,
            image_url: item.image_url || '',
            category: item.category || '',
            selectedSize: chosenVariant,
          }
        ];
      }
      const newTotal = updatedItems.reduce((acc, ci) => acc + ci.price_paise * ci.qty, 0);
      return {
        items: updatedItems,
        total_paise: newTotal,
        spend_cap_paise: prev?.spend_cap_paise || spendCapPaise,
        guardrail_status: 'approved',
        mandate_id: prev?.mandate_id,
      };
    });

    // 2. Confirmation message – plain readable text, no markdown
    const confirmMsg = `${label} (\u20b9${priceRupees}) added to your cart.`;

    // 3. Fetch fresh complementary recommendations, filtering out items already in cart
    let freshRecs: Recommendation[] = [];
    try {
      const cartNow = activeCart?.items || [];
      const allCartSkus = new Set([...cartNow.map(ci => ci.sku), item.sku]);
      const newItem = { sku: item.sku, name: item.name, price_paise: item.price_paise, qty: 1, selectedSize: chosenVariant };
      const payload = {
        message: `I just added ${label} to cart. What complementary products should I consider?`,
        spend_cap_paise: spendCapPaise,
        current_cart: [...cartNow, newItem],
      };
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const data = await res.json();
        // Filter out anything already in cart
        freshRecs = (data.recommendations || []).filter((r: Recommendation) => !allCartSkus.has(r.sku));
      }
    } catch (e) { /* silent */ }

    // Fallback: use existing recs filtered
    if (freshRecs.length === 0) {
      const allCartSkus = new Set([...(activeCart?.items || []).map(ci => ci.sku), item.sku]);
      freshRecs = recommendations.filter(r => !allCartSkus.has(r.sku));
    }

    // 4. Push confirmation + filtered recommendations
    setMessages((prev) => [
      ...prev,
      {
        role: 'agent' as const,
        content: confirmMsg,
        recommendations: freshRecs,
        timestamp: Date.now(),
      }
    ]);

    toast.success(`${label} added to cart!`);
  };

  // Remove individual item from Cart
  const handleRemoveCartItem = (index: number) => {
    if (!activeCart) return;
    const itemToRemove = activeCart.items[index];
    const updatedItems = activeCart.items.filter((_, i) => i !== index);
    const newTotal = updatedItems.reduce((acc, ci) => acc + ci.price_paise * ci.qty, 0);

    if (updatedItems.length === 0) {
      setActiveCart(null);
      setPaymentData(null);
    } else {
      setActiveCart({
        ...activeCart,
        items: updatedItems,
        total_paise: newTotal,
      });
    }

    const label = itemToRemove.selectedSize && itemToRemove.selectedSize !== 'Standard' && itemToRemove.selectedSize !== 'Standard Edition'
      ? `${itemToRemove.name} (${itemToRemove.selectedSize})`
      : itemToRemove.name;

    setMessages((prev) => [
      ...prev,
      {
        role: 'agent' as const,
        content: `Removed ${label} from your cart.`,
        timestamp: Date.now(),
      }
    ]);
    toast.success(`Removed ${label} from cart`);
  };

  // Clear Cart
  const handleClearCart = () => {
    setActiveCart(null);
    setRecommendations([]);
    setPaymentData(null);
    setDecisionTrace([]);
    setMessages((prev) => [
      ...prev,
      { role: 'agent', content: 'Cart has been cleared. What would you like to explore next?', timestamp: Date.now() }
    ]);
    toast.success('Cart cleared');
  };

  const cartTotalRupees = activeCart ? activeCart.total_paise / 100 : 0;
  const spendCapRupees = spendCapPaise / 100;
  const remainingBudget = Math.max(0, spendCapRupees - cartTotalRupees);
  const capPercentUsed = Math.min(100, Math.round((cartTotalRupees / spendCapRupees) * 100));

  return (
    <div className="min-h-screen bg-[#f8f8fb] flex flex-col">
      {/* Top Navbar */}
      <header className="h-16 bg-white border-b border-[#ebeaf0] sticky top-0 z-30 px-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="logo-mark" style={{ background: "#115e59", color: "#ffffff", borderRadius: "9px" }}>
            <ShoppingCart size={17} strokeWidth={2.4} color="#ffffff" />
          </div>
          <span className="font-display text-lg font-bold tracking-tight text-ink">
            CartPilot
          </span>
          <span className="hidden sm:inline-block ml-2 px-2.5 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider bg-[#e6f4ea] text-[#115e59]">
            Buyer Storefront
          </span>
        </div>

        <div className="flex items-center gap-3">
          {/* Spend Cap Chip */}
          <button
            onClick={() => setShowSpendCapModal(true)}
            className="flex items-center gap-2 bg-[#f4f3f8] hover:bg-[#eae8f2] border border-[#ebeaf0] px-3 py-1.5 rounded-lg text-xs font-semibold text-ink transition-all"
          >
            <ShieldCheck size={14} className="text-violet" />
            <span>Cap: ₹{spendCapRupees.toLocaleString()}</span>
          </button>

          {/* User Profile & Switcher */}
          <div className="flex items-center gap-2 pl-2 border-l border-[#ebeaf0]">
            <div className="w-8 h-8 rounded-full bg-[#d9cdfa] text-[#5c42bc] flex items-center justify-center text-xs font-bold">
              {user?.name?.slice(0, 2).toUpperCase() || 'SH'}
            </div>
            <span className="hidden md:inline text-xs font-bold text-ink">{user?.name || 'Shopper'}</span>

            <button
              onClick={() => {
                logout();
                setLocation('/auth');
              }}
              title="Sign Out / Switch Role"
              className="p-1.5 text-muted hover:text-ink hover:bg-[#f4f3f8] rounded-lg transition-all"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </header>

      {/* Spend Cap Modal */}
      <SpendCapModal
        isOpen={showSpendCapModal}
        onClose={() => setShowSpendCapModal(false)}
        currentSpendCapPaise={spendCapPaise}
        onSaveSpendCap={(newPaise) => {
          setSpendCapPaise(newPaise);
          toast.success(`Spend cap updated to ₹${(newPaise / 100).toLocaleString()}`);
        }}
      />

      {/* Product Detail & Sizing Modal */}
      <ProductDetailModal
        product={inspectingProduct}
        isOpen={Boolean(inspectingProduct)}
        onClose={() => setInspectingProduct(null)}
        onAddToCart={(item, size) => handleAddCrossSellWithVariant(item, size)}
        currentCartTotalPaise={activeCart?.total_paise || 0}
        spendCapPaise={spendCapPaise}
        isAlreadyInCart={Boolean(activeCart?.items?.some(i => i.sku === inspectingProduct?.sku))}
      />

      {/* Main Layout: Left History Sidebar + Center Chat Area + Right Live Receipt & Picks */}
      <div className="flex-1 flex max-w-[1600px] w-full mx-auto min-h-0">
        {/* Left Side: ChatGPT / Gemini Style Chat History Sidebar */}
        <ChatHistorySidebar
          sessions={sessions}
          currentSessionId={currentSessionId}
          isOpen={isHistoryOpen}
          onClose={handleToggleHistory}
          onSelectSession={handleSelectSession}
          onNewChat={handleNewChat}
          onDeleteSession={handleDeleteSession}
          searchQuery={historySearch}
          onSearchChange={setHistorySearch}
        />

        {/* Center & Right Column – Flex row: chat grows, cart fixed */}
        <main className="flex-1 p-4 md:p-6 flex gap-6 min-h-0 overflow-hidden">
          {/* Chat Conversation – fills remaining space */}
          <div className="flex-1 flex flex-col bg-white border border-[#ebeaf0] rounded-2xl shadow-sm overflow-hidden min-h-[620px] max-h-[calc(100vh-110px)]">
            {/* Chat Top Header */}
            <div className="p-4 border-b border-[#ebeaf0] bg-[#faf9fd] flex items-center justify-between">
              <div className="flex items-center gap-3">
                {/* Collapse Chat History toggle */}
                <button
                  onClick={handleToggleHistory}
                  className={`p-2 rounded-lg border transition-all ${
                    isHistoryOpen
                      ? 'bg-[#f0edff] text-violet border-[#d9d5ec]'
                      : 'bg-[#faf9fd] text-muted hover:text-ink border-[#ebeaf0]'
                  }`}
                  title={isHistoryOpen ? 'Collapse Chat History' : 'Expand Chat History'}
                >
                  <PanelLeft size={16} />
                </button>

                <div>
                  <h2 className="text-sm font-bold text-ink">CartPilot Shopping Agent</h2>
                  <div className="text-[11px] text-emerald flex items-center gap-1.5 font-medium">
                    <span className="w-2 h-2 rounded-full bg-[#2a9a71] animate-pulse"></span>
                    LangGraph Autonomous State Machine Ready
                  </div>
                </div>
              </div>

              {decisionTrace.length > 0 && (
                <button
                  onClick={() => setShowTrace(!showTrace)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#ebeaf0] bg-white text-xs font-bold text-violet hover:bg-[#fbfaff]"
                >
                  <span>{showTrace ? 'Hide Trace' : `Inspect Trace (${decisionTrace.length})`}</span>
                  <ChevronDown size={14} className={`transition-transform ${showTrace ? 'rotate-180' : ''}`} />
                </button>
              )}
            </div>

            {/* LangGraph Trace Accordion */}
            {showTrace && decisionTrace.length > 0 && (
              <div className="bg-[#1d1b25] text-white p-4 border-b border-[#353340] max-h-60 overflow-y-auto">
                <div className="eyebrow text-[#a388f5] mb-2">LangGraph Autonomous Execution Trace</div>
                <div className="space-y-2">
                  {decisionTrace.map((t, idx) => {
                    const cfg = NODE_CONFIG[t.node] || { label: t.node, icon: '⚙️' };
                    return (
                      <div key={idx} className="text-xs bg-[#2a2835] p-2.5 rounded-lg border border-[#3b384a]">
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-bold text-[#e5defe] flex items-center gap-1.5">
                            <span>{cfg.icon}</span>
                            <span>{cfg.label}</span>
                          </span>
                          <span className="text-[10px] text-muted font-mono">{t.node}</span>
                        </div>
                        {t.input_summary && <p className="text-[11px] text-[#aaa8b4] mb-0.5">Input: {t.input_summary}</p>}
                        {t.result_summary && <p className="text-[11px] text-[#2a9a71]">Output: {t.result_summary}</p>}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Chat Messages */}
            <div className="flex-1 p-6 overflow-y-auto space-y-4">
              {messages.map((m, idx) => (
                <div
                  key={idx}
                  className={`flex flex-col ${m.role === 'buyer' ? 'items-end' : 'items-start'}`}
                >
                  <div
                    className={`max-w-[95%] sm:max-w-[88%] rounded-2xl p-4 text-sm leading-relaxed ${
                      m.role === 'buyer'
                        ? 'bg-violet text-white rounded-br-none shadow-md'
                        : 'bg-[#f4f3f8] text-ink rounded-bl-none border border-[#ebeaf0]'
                    }`}
                  >
                    <div>{m.content}</div>

                    {/* In-Chat Payment Link Action Button */}
                    {m.paymentLink && (
                      <div className="mt-3 pt-2.5 border-t border-[#ebeaf0] flex items-center gap-2">
                        <a
                          href={m.paymentLink}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#2a9a71] text-white text-xs font-bold shadow-md hover:bg-[#23805e] transition-all"
                        >
                          <CreditCard size={14} />
                          <span>Complete Payment on Razorpay</span>
                          <ExternalLink size={13} />
                        </a>
                      </div>
                    )}

                    {/* In-Chat Interactive Recommendation Cards / Carousel */}
                    {m.recommendations && m.recommendations.length > 0 && (
                      <InChatRecommendations
                        recommendations={m.recommendations}
                        onSelectDetail={(rec) => setInspectingProduct(rec)}
                        onAddWithVariant={(rec, variant) => handleAddCrossSellWithVariant(rec, variant)}
                        selectedVariants={selectedVariants}
                        onSelectVariant={(sku, v) => setSelectedVariants((prev) => ({ ...prev, [sku]: v }))}
                        spendCapPaise={spendCapPaise}
                        currentCartTotalPaise={activeCart?.total_paise || 0}
                        cartSkus={new Set(activeCart?.items?.map((i) => i.sku) || [])}
                      />
                    )}
                  </div>
                  <span className="text-[10px] text-muted mt-1 px-1">
                    {m.role === 'buyer' ? 'You' : 'CartPilot Agent'}
                  </span>
                </div>
              ))}

              {loading && (
                <div className="flex items-center gap-2 p-3 bg-[#f4f3f8] rounded-2xl rounded-bl-none max-w-[200px] border border-[#ebeaf0]">
                  <div className="w-2 h-2 rounded-full bg-violet animate-bounce"></div>
                  <div className="w-2 h-2 rounded-full bg-violet animate-bounce [animation-delay:0.2s]"></div>
                  <div className="w-2 h-2 rounded-full bg-violet animate-bounce [animation-delay:0.4s]"></div>
                  <span className="text-xs text-muted font-medium ml-1">Evaluating policies...</span>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>


            {/* Input Form */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendMessage();
              }}
              className="p-4 bg-white border-t border-[#ebeaf0] flex items-center gap-2"
            >
              <input
                type="text"
                placeholder="Ask for products, outfit pairings, recipes, or accessories..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={loading}
                className="flex-1 h-12 px-4 bg-[#fbfafc] border border-[#ebeaf0] rounded-xl text-sm text-ink outline-none focus:border-violet focus:ring-1 focus:ring-violet transition-all"
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="h-12 w-12 rounded-xl bg-violet text-white flex items-center justify-center shadow-md hover:bg-[#6849d8] disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                <Send size={18} />
              </button>
            </form>
          </div>

          {/* Right Column: Live Cart Receipt – fixed 340px wide */}
          <div className="w-[340px] shrink-0 flex flex-col gap-4 overflow-y-auto max-h-[calc(100vh-110px)]">
            {/* Live Cart Receipt - fixed height, scrollable list */}
            <div className="bg-white border border-[#ebeaf0] rounded-2xl p-5 shadow-sm flex flex-col" style={{ maxHeight: 'calc(100vh - 120px)' }}>
              <div className="flex items-center justify-between mb-4 pb-3 border-b border-[#ebeaf0]">
                <div>
                  <h3 className="font-display text-sm font-bold text-ink">Live Cart Receipt</h3>
                  <p className="text-[11px] text-muted">Itemized snapshot & guardrail check</p>
                </div>
                {activeCart && activeCart.items.length > 0 && (
                  <button
                    onClick={handleClearCart}
                    title="Clear Cart"
                    className="p-1.5 text-muted hover:text-red-600 rounded-lg transition-all"
                  >
                    <Trash2 size={16} />
                  </button>
                )}
              </div>

              {activeCart && activeCart.items.length > 0 ? (
                <div className="flex flex-col min-h-0 flex-1">
                  {/* Cart Items List – scrollable, never grows the panel */}
                  <div className="space-y-2.5 mb-4 overflow-y-auto pr-1 flex-1" style={{ maxHeight: '45vh' }}>
                    {activeCart.items.map((item, i) => (
                      <div
                        key={i}
                        onClick={() => setInspectingProduct(item as any)}
                        className="flex items-center justify-between text-xs py-1.5 border-b border-[#f4f3f8] cursor-pointer hover:bg-[#faf9fd] p-1.5 rounded-lg transition-all group"
                        title="Click to view details & specifications"
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          {item.image_url && (
                            <img
                              src={item.image_url}
                              alt={item.name}
                              className="w-9 h-9 rounded-lg object-contain bg-[#f8f8fb] border border-[#ebeaf0] shrink-0"
                              onError={(e: any) => { e.target.style.display = 'none'; }}
                            />
                          )}
                          <div className="min-w-0">
                            <div className="font-bold text-ink truncate">{item.name}</div>
                            <div className="text-[10px] text-muted">
                              Qty: {item.qty} · ₹{(item.price_paise / 100).toFixed(2)}
                              {item.selectedSize ? ` · ${item.selectedSize}` : ''}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0 ml-2">
                          <div className="font-bold text-ink">
                            ₹{((item.price_paise * item.qty) / 100).toFixed(2)}
                          </div>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRemoveCartItem(i);
                            }}
                            title="Remove item from cart"
                            className="p-1 text-muted hover:text-red-500 hover:bg-red-50 rounded-md transition-colors"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Subtotal & Total */}
                  <div className="pt-2 border-t border-[#ebeaf0] space-y-1.5 text-xs">
                    <div className="flex justify-between text-muted">
                      <span>Subtotal</span>
                      <span>₹{cartTotalRupees.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between text-muted">
                      <span>Estimated Tax & Delivery</span>
                      <span>₹0.00</span>
                    </div>
                    <div className="flex justify-between font-display text-base font-bold text-ink pt-2 border-t border-[#ebeaf0]">
                      <span>Total Amount</span>
                      <span className="text-violet">₹{cartTotalRupees.toFixed(2)}</span>
                    </div>
                  </div>

                  {/* Spend Cap Meter */}
                  <div className="mt-4 p-3.5 rounded-xl bg-[#faf9fd] border border-[#ebeaf0]">
                    <div className="flex justify-between text-xs mb-1.5">
                      <span className="font-bold text-ink flex items-center gap-1.5">
                        <ShieldCheck size={14} className="text-emerald" />
                        Spend Cap Guardrail
                      </span>
                      <span className="font-bold text-violet">{capPercentUsed}%</span>
                    </div>
                    <div className="w-full h-2 bg-[#ebeaf0] rounded-full overflow-hidden mb-2">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          capPercentUsed > 100 ? 'bg-red-500' : 'bg-violet'
                        }`}
                        style={{ width: `${Math.min(100, capPercentUsed)}%` }}
                      />
                    </div>
                    <div className="text-[11px] text-muted flex justify-between">
                      <span>₹{cartTotalRupees.toFixed(2)} used</span>
                      <span>₹{remainingBudget.toFixed(2)} remaining</span>
                    </div>
                  </div>

                  {/* Proceed to Payment Button */}
                  <button
                    onClick={() => {
                      const amount = cartTotalRupees.toFixed(2);
                      const link = paymentData?.payment_link || 'https://rzp.io/l/demo_cartpilot';

                      // 1. Redirect to payment page in new window
                      try {
                        window.open(link, '_blank');
                      } catch (e) {}

                      // 2. Post payment awaiting message with clickable link in chat
                      setMessages((prev) => [
                        ...prev,
                        {
                          role: 'agent' as const,
                          content: `Payment awaited for ₹${amount}. Your order has been placed and is pending payment confirmation.`,
                          paymentLink: link,
                          timestamp: Date.now(),
                        }
                      ]);
                      toast.success(`Order placed! Redirecting to payment for ₹${amount}...`);
                    }}
                    className="w-full h-11 bg-[#2a9a71] text-white font-bold text-xs rounded-xl shadow-md hover:bg-[#23805e] transition-all flex items-center justify-center gap-2 mt-4"
                  >
                    <CreditCard size={16} />
                    <span>Proceed to Payment (₹{cartTotalRupees.toFixed(2)})</span>
                    <ArrowRight size={14} />
                  </button>
                </div>
              ) : (
                <div className="text-center py-8 text-muted">
                  <ShoppingBag size={32} className="mx-auto mb-2 opacity-40 text-violet" />
                  <p className="text-xs font-semibold text-ink">Your cart is empty</p>
                  <p className="text-[11px] mt-1">Tell the AI agent what you want to add.</p>
                </div>
              )}
            </div>

            {/* Growth Agent Recommendations removed – now shown inline in chat */}
            {false && recommendations.length > 0 && (
              <div className="bg-white border border-[#ebeaf0] rounded-2xl p-5 shadow-sm">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <Sparkles size={16} className="text-violet" />
                    <h3 className="font-display text-sm font-bold text-ink">Growth Agent Recommendations</h3>
                  </div>
                  <span className="text-[10px] text-muted">Click for info & sizing</span>
                </div>
                <p className="text-[11px] text-muted mb-4">
                  Learned co-purchase patterns & category compatibility
                </p>

                <div className="space-y-3.5">
                  {recommendations.map((rec, i) => {
                    const priceRupees = (
                      (rec.price_paise || (rec.price_rupees ? rec.price_rupees * 100 : 0)) / 100
                    ).toFixed(2);

                    const options = rec.metadata?.sizes || rec.metadata?.options || ['Standard Edition', 'Pro Bundle'];
                    const currentSelected = selectedVariants[rec.sku] || options[0];

                    return (
                      <div
                        key={i}
                        className="p-3.5 rounded-xl border border-[#ebeaf0] bg-[#fbfafc] hover:border-violet/40 hover:shadow-xs transition-all space-y-2.5"
                      >
                        {/* Product Header Row with Thumbnail */}
                        <div
                          className="flex items-start gap-3 cursor-pointer group"
                          onClick={() => setInspectingProduct(rec)}
                          title="Click to inspect full details, specifications & ratings"
                        >
                          <div className="w-14 h-14 rounded-xl bg-white border border-[#ebeaf0] overflow-hidden flex items-center justify-center p-1 shrink-0 group-hover:border-violet transition-all">
                            <img
                              src={rec.image_url || 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=200'}
                              alt={rec.name}
                              className="w-full h-full object-contain"
                              onError={(e: any) => {
                                e.target.src = 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=200';
                              }}
                            />
                          </div>

                          <div className="min-w-0 flex-1">
                            <div className="flex items-center justify-between gap-1">
                              <span className="inline-block text-[9px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded bg-[#eeeaff] text-violet truncate">
                                {rec.tier ? rec.tier.replace(/_/g, ' ') : 'Tier Recommendation'}
                              </span>
                              <span className="text-[10px] text-muted flex items-center gap-0.5">
                                <Info size={11} className="text-violet" />
                                Details
                              </span>
                            </div>

                            <h4 className="text-xs font-bold text-ink group-hover:text-violet transition-all truncate mt-0.5">
                              {rec.name}
                            </h4>

                            <div className="text-xs text-violet font-extrabold mt-0.5">
                              ₹{priceRupees}
                            </div>
                          </div>
                        </div>

                        {/* Rationale Quote */}
                        {rec.reason && (
                          <p className="text-[10px] text-muted bg-white p-2 rounded-lg border border-[#f0eff4] leading-relaxed">
                            💡 {rec.reason}
                          </p>
                        )}

                        {/* Inline Variant Selection Pills */}
                        {options.length > 0 && (
                          <div className="space-y-1">
                            <span className="text-[10px] font-bold text-muted">Variant:</span>
                            <div className="flex flex-wrap gap-1.5">
                              {options.map((opt: string) => (
                                <button
                                  key={opt}
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedVariants(prev => ({ ...prev, [rec.sku]: opt }));
                                  }}
                                  className={`px-2 py-0.5 rounded text-[10px] font-bold border transition-all ${
                                    currentSelected === opt
                                      ? 'bg-violet text-white border-violet'
                                      : 'bg-white border-[#ebeaf0] text-muted hover:text-ink'
                                  }`}
                                >
                                  {opt}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Action Row */}
                        <div className="flex items-center justify-between pt-1 gap-2 border-t border-[#f0eff4]">
                          <button
                            type="button"
                            onClick={() => setInspectingProduct(rec)}
                            className="text-[11px] font-bold text-muted hover:text-violet flex items-center gap-1"
                          >
                            <Info size={12} />
                            <span>More Info</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => handleAddCrossSellWithVariant(rec, currentSelected)}
                            className="px-3 py-1.5 rounded-lg bg-violet text-white text-[11px] font-bold hover:bg-[#6849d8] shadow-xs flex items-center gap-1 shrink-0"
                          >
                            <Plus size={13} />
                            <span>Add ({currentSelected})</span>
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

