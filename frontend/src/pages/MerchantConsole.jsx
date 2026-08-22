import React, { useState, useEffect, useMemo } from 'react';
import { 
  Shield, 
  Sliders, 
  Sparkles, 
  Search, 
  Check, 
  X, 
  AlertCircle, 
  CheckCircle2, 
  TrendingUp, 
  Zap, 
  Package, 
  ShoppingBag, 
  ArrowRight, 
  RefreshCw, 
  Lock, 
  ExternalLink,
  Volume2,
  VolumeX,
  Layers,
  BarChart3,
  DollarSign,
  Plus
} from 'lucide-react';

const BASE_URL = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000';

export default function MerchantConsole() {
  const [activeTab, setActiveTab] = useState('policy'); // 'policy' | 'catalog' | 'growth-rules'
  const [loading, setLoading] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);

  // ─── TAB 1: Policy State ──────────────────────────────────────────────────
  const [policyData, setPolicyData] = useState({
    spend_cap_paise: 1000000,
    autonomy_threshold_paise: 500000,
    allowed_categories: [],
    available_categories: []
  });
  const [spendCapInput, setSpendCapInput] = useState('10000');
  const [autonomyInput, setAutonomyInput] = useState('5000');
  const [categorySearch, setCategorySearch] = useState('');
  const [isSavingPolicy, setIsSavingPolicy] = useState(false);

  // ─── TAB 2: Catalog State ─────────────────────────────────────────────────
  const [catalogItems, setCatalogItems] = useState([]);
  const [catalogSummary, setCatalogSummary] = useState({
    total_items: 0,
    boosted_items: 0,
    out_of_stock_items: 0,
    categories_count: 0
  });
  const [catalogSearch, setCatalogSearch] = useState('');
  const [selectedCategoryFilter, setSelectedCategoryFilter] = useState('all');
  const [showBoostedOnly, setShowBoostedOnly] = useState(false);
  const [togglingSku, setTogglingSku] = useState(null);
  const [boostPreviewToast, setBoostPreviewToast] = useState(null);

  // ─── TAB 3: Growth Rules State ────────────────────────────────────────────
  const [growthRules, setGrowthRules] = useState([]);
  const [rulesSummary, setRulesSummary] = useState({
    total_rules: 0,
    verified_rules: 0,
    ai_suggested_rules: 0,
    active_rules: 0,
    muted_rules: 0,
    total_offered: 0,
    total_accepted: 0,
    overall_conversion_pct: 0,
    total_revenue_lift_rupees: 0
  });
  const [ruleSearch, setRuleSearch] = useState('');
  const [ruleStatusFilter, setRuleStatusFilter] = useState('all'); // 'all' | 'data_verified' | 'ai_suggested' | 'active' | 'muted'
  const [mutingRuleId, setMutingRuleId] = useState(null);
  const [isReseedingPriors, setIsReseedingPriors] = useState(false);

  // ─── Scalable Architecture: Category Compat & Embeddings State ───────────
  const [compatPairs, setCompatPairs] = useState([]);
  const [isGeneratingCompat, setIsGeneratingCompat] = useState(false);
  const [isAddingCompat, setIsAddingCompat] = useState(false);
  const [newCompatA, setNewCompatA] = useState('');
  const [newCompatB, setNewCompatB] = useState('');
  const [newCompatReason, setNewCompatReason] = useState('');
  const [showAddCompatModal, setShowAddCompatModal] = useState(false);
  const [embeddingStatus, setEmbeddingStatus] = useState({
    real_order_count: 0,
    min_orders_required: 50,
    skus_with_embeddings: 0,
    trained: false,
    ready: false
  });
  const [isTrainingEmbeddings, setIsTrainingEmbeddings] = useState(false);

  // Spend cap and autonomy presets
  const spendCapPresets = [500, 1000, 2500, 5000, 10000, 50000];
  const autonomyPresets = [1000, 2500, 5000, 10000, 25000, 50000];

  // Helper to show transient toasts
  const showToast = (msg, type = 'success') => {
    setToastMessage({ text: msg, type });
    setTimeout(() => setToastMessage(null), 4000);
  };

  // ─── Initial Fetch on Mount ───────────────────────────────────────────────
  useEffect(() => {
    fetchPolicy();
    fetchCatalog();
    fetchGrowthRules();
    fetchCategoryCompat();
    fetchEmbeddingStatus();
  }, []);

  /* ─── Fetch Policy Configuration ────────────────────────────────────────── */
  const fetchPolicy = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/console/policy`);
      const data = await res.json();
      if (res.ok) {
        setPolicyData(data);
        setSpendCapInput((data.spend_cap_paise / 100).toFixed(0));
        setAutonomyInput((data.autonomy_threshold_paise / 100).toFixed(0));
      }
    } catch (err) {
      console.error('Error fetching policy:', err);
    }
  };

  /* ─── Fetch Catalog & Boost Statuses ────────────────────────────────────── */
  const fetchCatalog = async () => {
    try {
      const params = new URLSearchParams();
      if (catalogSearch.trim()) params.append('q', catalogSearch.trim());
      if (selectedCategoryFilter !== 'all') params.append('category', selectedCategoryFilter);
      if (showBoostedOnly) params.append('boosted_only', 'true');
      params.append('limit', '100');

      const res = await fetch(`${BASE_URL}/api/console/catalog?${params.toString()}`);
      const data = await res.json();
      if (res.ok) {
        setCatalogItems(data.items || []);
        if (data.summary) setCatalogSummary(data.summary);
      }
    } catch (err) {
      console.error('Error fetching catalog:', err);
    }
  };

  useEffect(() => {
    fetchCatalog();
  }, [catalogSearch, selectedCategoryFilter, showBoostedOnly]);

  /* ─── Fetch Growth Rules & Empirical Stats ──────────────────────────────── */
  const fetchGrowthRules = async () => {
    try {
      const params = new URLSearchParams();
      if (ruleSearch.trim()) params.append('q', ruleSearch.trim());
      if (ruleStatusFilter !== 'all') params.append('status', ruleStatusFilter);

      const res = await fetch(`${BASE_URL}/api/console/growth-rules?${params.toString()}`);
      const data = await res.json();
      if (res.ok) {
        setGrowthRules(data.rules || []);
        if (data.summary) setRulesSummary(data.summary);
      }
    } catch (err) {
      console.error('Error fetching growth rules:', err);
    }
  };

  useEffect(() => {
    fetchGrowthRules();
  }, [ruleSearch, ruleStatusFilter]);

  /* ─── Save Policy Action ────────────────────────────────────────────────── */
  const handleSavePolicy = async (e) => {
    e?.preventDefault();
    const capPaise = parseInt(spendCapInput, 10) * 100;
    const autonomyPaise = parseInt(autonomyInput, 10) * 100;

    if (isNaN(capPaise) || capPaise <= 0) {
      showToast('Please enter a valid spend cap amount.', 'error');
      return;
    }
    if (isNaN(autonomyPaise) || autonomyPaise <= 0) {
      showToast('Please enter a valid autonomy threshold.', 'error');
      return;
    }
    if (!policyData.allowed_categories || policyData.allowed_categories.length === 0) {
      showToast('At least one category must be allowed.', 'error');
      return;
    }

    setIsSavingPolicy(true);
    try {
      const res = await fetch(`${BASE_URL}/api/console/policy`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          spend_cap_paise: capPaise,
          autonomy_threshold_paise: autonomyPaise,
          allowed_categories: policyData.allowed_categories
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to update policy');

      setPolicyData(prev => ({
        ...prev,
        spend_cap_paise: capPaise,
        autonomy_threshold_paise: autonomyPaise
      }));
      showToast('🛡️ Policy updated and logged to audit trail successfully!');
    } catch (err) {
      showToast(`❌ Error: ${err.message}`, 'error');
    } finally {
      setIsSavingPolicy(false);
    }
  };

  /* ─── Toggle Category Allowed State ─────────────────────────────────────── */
  const handleToggleCategory = (cat) => {
    setPolicyData(prev => {
      const current = prev.allowed_categories || [];
      const exists = current.includes(cat);
      const updated = exists ? current.filter(c => c !== cat) : [...current, cat];
      return { ...prev, allowed_categories: updated };
    });
  };

  const handleSelectAllCategories = () => {
    setPolicyData(prev => ({
      ...prev,
      allowed_categories: [...prev.available_categories]
    }));
  };

  const handleDeselectAllCategories = () => {
    setPolicyData(prev => ({
      ...prev,
      allowed_categories: []
    }));
  };

  /* ─── Toggle Promotion Boost ────────────────────────────────────────────── */
  const handleToggleBoost = async (sku, currentBoosted) => {
    setTogglingSku(sku);
    const newBoosted = !currentBoosted;

    // Optimistic UI update
    setCatalogItems(prev => prev.map(item => item.sku === sku ? { ...item, boosted: newBoosted } : item));

    try {
      const res = await fetch(`${BASE_URL}/api/console/catalog/boost`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sku, boosted: newBoosted })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to toggle boost');

      setBoostPreviewToast({
        name: data.name,
        preview: data.rank_preview,
        boosted: data.boosted
      });
      setTimeout(() => setBoostPreviewToast(null), 5000);

      // Refresh summary
      fetchCatalog();
    } catch (err) {
      // Revert optimistic update
      setCatalogItems(prev => prev.map(item => item.sku === sku ? { ...item, boosted: currentBoosted } : item));
      showToast(`❌ Boost Error: ${err.message}`, 'error');
    } finally {
      setTogglingSku(null);
    }
  };

  /* ─── Toggle Mute Growth Rule ───────────────────────────────────────────── */
  const handleToggleMuteRule = async (rule) => {
    const ruleId = rule.rule_id;
    setMutingRuleId(ruleId);
    const newMuted = !rule.muted;

    // Optimistic UI update
    setGrowthRules(prev => prev.map(r => r.rule_id === ruleId ? { ...r, muted: newMuted } : r));

    try {
      const res = await fetch(`${BASE_URL}/api/console/growth-rules/mute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sku_a: rule.sku_a,
          sku_b: rule.sku_b,
          muted: newMuted
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to update rule');

      showToast(newMuted ? `🔇 Muted rule: "${rule.trigger_name} → ${rule.target_name}". Excluded from recommendations.` : `🔊 Restored rule: "${rule.trigger_name} → ${rule.target_name}". Active in recommendation engine.`);

      // Refresh rules summary
      fetchGrowthRules();
    } catch (err) {
      // Revert
      setGrowthRules(prev => prev.map(r => r.rule_id === ruleId ? { ...r, muted: rule.muted } : r));
      showToast(`❌ Error: ${err.message}`, 'error');
    } finally {
      setMutingRuleId(null);
    }
  };

  /* ─── Reseed AI Cold-Start Priors ───────────────────────────────────────── */
  const handleReseedPriors = async () => {
    setIsReseedingPriors(true);
    try {
      const res = await fetch(`${BASE_URL}/api/console/growth-rules/reseed-priors`, {
        method: 'POST'
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to reseed priors');
      showToast(`🤖 ${data.message}`);
      fetchGrowthRules();
    } catch (err) {
      showToast(`❌ Error: ${err.message}`, 'error');
    } finally {
      setIsReseedingPriors(false);
    }
  };

  /* ─── Fetch Category Compatibility Graph ────────────────────────────────── */
  const fetchCategoryCompat = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/console/category-compat`);
      const data = await res.json();
      if (res.ok) {
        setCompatPairs(data.pairs || []);
      }
    } catch (err) {
      console.error('Error fetching category compat:', err);
    }
  };

  /* ─── Generate Category Compatibility Graph (LLM) ───────────────────────── */
  const handleGenerateCompat = async () => {
    setIsGeneratingCompat(true);
    try {
      const res = await fetch(`${BASE_URL}/api/console/category-compat/generate`, {
        method: 'POST'
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to generate category compatibility graph');
      showToast(`🌐 ${data.message}`);
      fetchCategoryCompat();
    } catch (err) {
      showToast(`❌ Error: ${err.message}`, 'error');
    } finally {
      setIsGeneratingCompat(false);
    }
  };

  /* ─── Delete / Lock Category Compatibility Pair ─────────────────────────── */
  const handleDeleteCompat = async (catA, catB) => {
    try {
      const res = await fetch(`${BASE_URL}/api/console/category-compat/${encodeURIComponent(catA)}/${encodeURIComponent(catB)}`, {
        method: 'DELETE'
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to delete pair');
      showToast(`🔒 ${data.message}`);
      fetchCategoryCompat();
    } catch (err) {
      showToast(`❌ Error: ${err.message}`, 'error');
    }
  };

  /* ─── Add Custom Category Compatibility Pair ────────────────────────────── */
  const handleAddCompat = async (e) => {
    e.preventDefault();
    if (!newCompatA || !newCompatB || !newCompatReason.trim()) {
      showToast('❌ Please select both categories and provide reasoning.', 'error');
      return;
    }
    if (newCompatA === newCompatB) {
      showToast('❌ Cannot pair a category with itself.', 'error');
      return;
    }
    setIsAddingCompat(true);
    try {
      const res = await fetch(`${BASE_URL}/api/console/category-compat/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category_a: newCompatA,
          category_b: newCompatB,
          reasoning: newCompatReason.trim()
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to add compatibility pair');
      showToast(`✅ ${data.message}`);
      setNewCompatA('');
      setNewCompatB('');
      setNewCompatReason('');
      setShowAddCompatModal(false);
      fetchCategoryCompat();
    } catch (err) {
      showToast(`❌ Error: ${err.message}`, 'error');
    } finally {
      setIsAddingCompat(false);
    }
  };

  /* ─── Fetch Co-Purchase Embeddings Status ────────────────────────────────── */
  const fetchEmbeddingStatus = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/console/embeddings/status`);
      const data = await res.json();
      if (res.ok) {
        setEmbeddingStatus(data);
      }
    } catch (err) {
      console.error('Error fetching embedding status:', err);
    }
  };

  /* ─── Train Co-Purchase Embeddings (item2vec) ────────────────────────────── */
  const handleTrainEmbeddings = async () => {
    setIsTrainingEmbeddings(true);
    try {
      const res = await fetch(`${BASE_URL}/api/console/embeddings/train`, {
        method: 'POST'
      });
      const data = await res.json();
      if (data.status === 'insufficient_data') {
        showToast(`⚠️ ${data.message}`, 'error');
      } else if (!res.ok) {
        throw new Error(data.detail || 'Failed to train embeddings');
      } else {
        showToast(`🧠 ${data.message}`);
      }
      fetchEmbeddingStatus();
    } catch (err) {
      showToast(`❌ Error: ${err.message}`, 'error');
    } finally {
      setIsTrainingEmbeddings(false);
    }
  };

  const filteredCategories = useMemo(() => {
    if (!categorySearch.trim()) return policyData.available_categories;
    return policyData.available_categories.filter(c => c.toLowerCase().includes(categorySearch.toLowerCase()));
  }, [policyData.available_categories, categorySearch]);

  return (
    <div className="console-container">
      {/* ── Top Header ── */}
      <div className="console-header">
        <div className="console-header-left">
          <div className="console-badge">
            <Sliders size={13} />
            <span>Merchant Control Plane</span>
          </div>
          <h1 className="console-title">Merchant Governance Console</h1>
          <p className="console-subtitle">
            Configure autonomous guardrail policies, curate promotion levers, and inspect empirical growth engine performance.
          </p>
        </div>

        <div className="console-meta-pills">
          <div className="console-meta-pill">
            <Shield size={13} color="var(--accent-teal)" />
            <span>Spend Cap: ₹{(policyData.spend_cap_paise / 100).toFixed(0)}</span>
          </div>
          <div className="console-meta-pill">
            <Lock size={13} color="var(--accent-mustard)" />
            <span>Autonomy Limit: ₹{(policyData.autonomy_threshold_paise / 100).toFixed(0)}</span>
          </div>
          <div className="console-meta-pill">
            <Zap size={13} color="#2563EB" />
            <span>Active Rules: {rulesSummary.active_rules}</span>
          </div>
        </div>
      </div>

      {/* ── Toast Notifications ── */}
      {toastMessage && (
        <div className={`console-toast ${toastMessage.type === 'error' ? 'error' : 'success'}`}>
          {toastMessage.type === 'error' ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
          <span>{toastMessage.text}</span>
        </div>
      )}

      {/* ── Boost Preview Toast ── */}
      {boostPreviewToast && (
        <div className="console-boost-toast">
          <div className="boost-toast-header">
            <Sparkles size={14} color="var(--accent-mustard)" />
            <strong>Promotion Boost Uplift Simulation</strong>
          </div>
          <p className="boost-toast-body">{boostPreviewToast.preview}</p>
        </div>
      )}

      {/* ── Tab Switcher Navigation ── */}
      <div className="console-tabs-nav">
        <button
          className={`console-tab-btn ${activeTab === 'policy' ? 'active' : ''}`}
          onClick={() => setActiveTab('policy')}
        >
          <Shield size={16} />
          <span>Policy Control</span>
        </button>

        <button
          className={`console-tab-btn ${activeTab === 'catalog' ? 'active' : ''}`}
          onClick={() => setActiveTab('catalog')}
        >
          <Package size={16} />
          <span>Catalog & Promotions</span>
          {catalogSummary.boosted_items > 0 && (
            <span className="tab-pill-badge">{catalogSummary.boosted_items} Boosted</span>
          )}
        </button>

        <button
          className={`console-tab-btn ${activeTab === 'growth-rules' ? 'active' : ''}`}
          onClick={() => setActiveTab('growth-rules')}
        >
          <TrendingUp size={16} />
          <span>Growth Rules Inspector</span>
          <span className="tab-pill-badge">{rulesSummary.total_rules} Rules</span>
        </button>
      </div>

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* ── TAB 1: Policy Control ── */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {activeTab === 'policy' && (
        <div className="console-tab-content">
          <form onSubmit={handleSavePolicy}>
            <div className="console-grid-2col">
              {/* Card 1: Maximum Hard Spend Cap */}
              <div className="console-card">
                <div className="console-card-header">
                  <div>
                    <h3 className="console-card-title">Global Hard Spend Cap</h3>
                    <p className="console-card-desc">
                      Hard ceiling. Orders exceeding this amount are automatically blocked by the guardrail engine.
                    </p>
                  </div>
                  <Shield size={20} color="var(--accent-teal)" />
                </div>

                <div className="console-input-group">
                  <label className="console-input-label">Spend Cap Ceiling (INR ₹)</label>
                  <div className="console-currency-input-wrap">
                    <span className="currency-symbol">₹</span>
                    <input
                      type="number"
                      className="console-input"
                      value={spendCapInput}
                      onChange={(e) => setSpendCapInput(e.target.value)}
                      min="1"
                      required
                    />
                  </div>
                </div>

                <div className="console-presets-row">
                  <span className="presets-label">Presets:</span>
                  <div className="presets-chips">
                    {spendCapPresets.map((val) => (
                      <button
                        key={val}
                        type="button"
                        className={`preset-chip ${spendCapInput === val.toString() ? 'active' : ''}`}
                        onClick={() => setSpendCapInput(val.toString())}
                      >
                        ₹{val.toLocaleString()}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Card 2: Autonomy Threshold (Reserve Pay Spending-Limit Architecture) */}
              <div className="console-card">
                <div className="console-card-header">
                  <div>
                    <h3 className="console-card-title">Autonomy Threshold</h3>
                    <p className="console-card-desc">
                      Orders below this threshold auto-approve without friction. Orders at or above pause for explicit merchant/buyer confirmation before creating a payment mandate.
                    </p>
                  </div>
                  <Lock size={20} color="var(--accent-mustard)" />
                </div>

                <div className="reserve-pay-callout">
                  <Zap size={14} color="var(--accent-mustard)" />
                  <div>
                    <strong>Reserve Pay Design Pattern:</strong>
                    <span> Mirrors production high-value authorization limits (autonomous transacting up to threshold, deliberate confirmation above).</span>
                  </div>
                </div>

                <div className="console-input-group" style={{ marginTop: '0.85rem' }}>
                  <label className="console-input-label">Autonomy Confirmation Threshold (INR ₹)</label>
                  <div className="console-currency-input-wrap">
                    <span className="currency-symbol">₹</span>
                    <input
                      type="number"
                      className="console-input"
                      value={autonomyInput}
                      onChange={(e) => setAutonomyInput(e.target.value)}
                      min="1"
                      required
                    />
                  </div>
                </div>

                <div className="console-presets-row">
                  <span className="presets-label">Presets:</span>
                  <div className="presets-chips">
                    {autonomyPresets.map((val) => (
                      <button
                        key={val}
                        type="button"
                        className={`preset-chip ${autonomyInput === val.toString() ? 'active' : ''}`}
                        onClick={() => setAutonomyInput(val.toString())}
                      >
                        ₹{val.toLocaleString()}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Card 3: Allowed Categories Multi-Select Grid */}
            <div className="console-card" style={{ marginTop: '1.25rem' }}>
              <div className="console-card-header">
                <div>
                  <h3 className="console-card-title">Catalog Category Whitelist</h3>
                  <p className="console-card-desc">
                    Only SKUs in checked categories can be itemized by the buyer agent. Unchecked categories are blocked by guardrails.
                  </p>
                </div>
                <div className="category-actions-row">
                  <button
                    type="button"
                    className="btn-console-outline"
                    onClick={handleSelectAllCategories}
                  >
                    Select All
                  </button>
                  <button
                    type="button"
                    className="btn-console-outline"
                    onClick={handleDeselectAllCategories}
                  >
                    Deselect All
                  </button>
                </div>
              </div>

              <div className="category-search-bar">
                <Search size={14} color="var(--ink-muted)" />
                <input
                  type="text"
                  placeholder="Filter category whitelist…"
                  value={categorySearch}
                  onChange={(e) => setCategorySearch(e.target.value)}
                />
                <span className="category-count-badge">
                  {policyData.allowed_categories?.length || 0} of {policyData.available_categories?.length || 0} Enabled
                </span>
              </div>

              <div className="categories-grid">
                {filteredCategories.map((cat) => {
                  const isChecked = policyData.allowed_categories?.includes(cat);
                  return (
                    <div
                      key={cat}
                      className={`category-chip-box ${isChecked ? 'active' : ''}`}
                      onClick={() => handleToggleCategory(cat)}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => {}} // Handled by div click
                      />
                      <span className="category-chip-name">{cat}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Form Save Button Bar */}
            <div className="console-footer-bar">
              <div className="console-audit-note">
                <Shield size={14} color="var(--accent-teal)" />
                <span>Every policy update is automatically recorded into the immutable audit ledger.</span>
              </div>

              <button
                type="submit"
                className="btn-console-primary"
                disabled={isSavingPolicy}
              >
                {isSavingPolicy ? (
                  <>
                    <RefreshCw size={14} className="animate-spin" />
                    <span>Saving Policy…</span>
                  </>
                ) : (
                  <>
                    <Check size={15} />
                    <span>Save & Deploy Policy</span>
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* ── TAB 2: Catalog & Promotions ── */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {activeTab === 'catalog' && (
        <div className="console-tab-content">
          {/* Summary KPIs */}
          <div className="console-kpi-grid">
            <div className="console-kpi-card">
              <div className="kpi-label">Total Catalog SKUs</div>
              <div className="kpi-value">{catalogSummary.total_items}</div>
              <div className="kpi-sub">Synced from merchant inventory</div>
            </div>
            <div className="console-kpi-card">
              <div className="kpi-label">Active Promoted Items</div>
              <div className="kpi-value" style={{ color: 'var(--accent-mustard)' }}>
                {catalogSummary.boosted_items}
              </div>
              <div className="kpi-sub">1.35x rank uplift applied</div>
            </div>
            <div className="console-kpi-card">
              <div className="kpi-label">Out of Stock SKUs</div>
              <div className="kpi-value" style={{ color: 'var(--alert-brick)' }}>
                {catalogSummary.out_of_stock_items}
              </div>
              <div className="kpi-sub">Triggers Substitution Agent</div>
            </div>
            <div className="console-kpi-card">
              <div className="kpi-label">Distinct Categories</div>
              <div className="kpi-value" style={{ color: 'var(--accent-teal)' }}>
                {catalogSummary.categories_count}
              </div>
              <div className="kpi-sub">Governed by policy whitelist</div>
            </div>
          </div>

          {/* Search & Filter Bar */}
          <div className="console-toolbar">
            <div className="toolbar-search-wrap">
              <Search size={15} color="var(--ink-muted)" />
              <input
                type="text"
                placeholder="Search products by name, SKU, or keyword…"
                value={catalogSearch}
                onChange={(e) => setCatalogSearch(e.target.value)}
              />
            </div>

            <div className="toolbar-controls-right">
              <select
                className="console-select"
                value={selectedCategoryFilter}
                onChange={(e) => setSelectedCategoryFilter(e.target.value)}
              >
                <option value="all">All Categories ({policyData.available_categories.length})</option>
                {policyData.available_categories.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>

              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={showBoostedOnly}
                  onChange={(e) => setShowBoostedOnly(e.target.checked)}
                />
                <span>Boosted Only</span>
              </label>
            </div>
          </div>

          {/* Catalog Products Table */}
          <div className="console-table-card">
            <div className="console-table-scroll">
              <table className="console-table">
              <thead>
                <tr>
                  <th style={{ width: '45%' }}>Product & SKU</th>
                  <th>Category</th>
                  <th>Price</th>
                  <th>Inventory Status</th>
                  <th style={{ textAlign: 'right' }}>Promotion Boost Lever</th>
                </tr>
              </thead>
              <tbody>
                {catalogItems.length === 0 ? (
                  <tr>
                    <td colSpan="5" className="table-empty-cell">
                      No products matched your search filter.
                    </td>
                  </tr>
                ) : (
                  catalogItems.map((item) => (
                    <tr key={item.sku} className={item.boosted ? 'boosted-row' : ''}>
                      <td>
                        <div className="table-product-cell">
                          {item.image_url ? (
                            <img
                              src={item.image_url}
                              alt={item.name}
                              className="table-product-thumb"
                              onError={(e) => { e.target.style.display = 'none'; }}
                            />
                          ) : (
                            <div className="table-product-thumb-placeholder">
                              <ShoppingBag size={14} />
                            </div>
                          )}
                          <div>
                            <div className="table-product-name">{item.name}</div>
                            <div className="table-product-sku">{item.sku}</div>
                          </div>
                        </div>
                      </td>

                      <td>
                        <span className="category-tag-cell">{item.category}</span>
                      </td>

                      <td>
                        <span className="table-price-cell">₹{(item.price_paise / 100).toFixed(2)}</span>
                      </td>

                      <td>
                        {item.stock > 0 ? (
                          <span className="stock-badge in-stock">
                            <CheckCircle2 size={11} /> {item.stock} in stock
                          </span>
                        ) : (
                          <span className="stock-badge out-of-stock">
                            <AlertCircle size={11} /> Out of Stock
                          </span>
                        )}
                      </td>

                      <td style={{ textAlign: 'right' }}>
                        <div className="boost-toggle-wrap">
                          {item.boosted && (
                            <span className="boost-indicator-pill">
                              <Sparkles size={11} /> 1.35x Boost
                            </span>
                          )}
                          <button
                            type="button"
                            className={`btn-toggle-switch ${item.boosted ? 'on' : 'off'}`}
                            onClick={() => handleToggleBoost(item.sku, item.boosted)}
                            disabled={togglingSku === item.sku}
                            title={item.boosted ? 'Deactivate promotion boost' : 'Activate 1.35x promotion boost'}
                          >
                            <span className="switch-slider" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            </div>
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* ── TAB 3: Growth Rules Inspector (Hybrid AI & Data Governance) ── */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {activeTab === 'growth-rules' && (
        <div className="console-tab-content">
          {/* Top Performance KPI Metrics */}
          <div className="console-kpi-grid">
            <div className="console-kpi-card">
              <div className="kpi-label">Active Growth Rules</div>
              <div className="kpi-value" style={{ color: 'var(--accent-teal)' }}>
                {rulesSummary.active_rules}
              </div>
              <div className="kpi-sub">{rulesSummary.verified_rules || 0} Data-Verified · {rulesSummary.ai_suggested_rules || 0} AI-Priors</div>
            </div>

            <div className="console-kpi-card">
              <div className="kpi-label">Total Upsell Offers Triggered</div>
              <div className="kpi-value">{rulesSummary.total_offered}</div>
              <div className="kpi-sub">Across customer shopping chats</div>
            </div>

            <div className="console-kpi-card">
              <div className="kpi-label">Conversion Rate</div>
              <div className="kpi-value" style={{ color: 'var(--accent-mustard)' }}>
                {rulesSummary.overall_conversion_pct}%
              </div>
              <div className="kpi-sub">{rulesSummary.total_accepted} accepted upsells</div>
            </div>

            <div className="console-kpi-card">
              <div className="kpi-label">Attributable Revenue Lift</div>
              <div className="kpi-value" style={{ color: '#16A34A' }}>
                ₹{rulesSummary.total_revenue_lift_rupees.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
              </div>
              <div className="kpi-sub">Incremental revenue generated</div>
            </div>
          </div>

          {/* Search & Filter Bar */}
          <div className="console-toolbar">
            <div className="toolbar-search-wrap">
              <Search size={15} color="var(--ink-muted)" />
              <input
                type="text"
                placeholder="Search rules by trigger, recommended SKU, or reasoning…"
                value={ruleSearch}
                onChange={(e) => setRuleSearch(e.target.value)}
              />
            </div>

            <div className="toolbar-controls-right">
              <div className="rule-filter-chips">
                <button
                  className={`filter-chip ${ruleStatusFilter === 'all' ? 'active' : ''}`}
                  onClick={() => setRuleStatusFilter('all')}
                >
                  All ({rulesSummary.total_rules || 0})
                </button>
                <button
                  className={`filter-chip ${ruleStatusFilter === 'data_verified' ? 'active' : ''}`}
                  onClick={() => setRuleStatusFilter('data_verified')}
                >
                  <CheckCircle2 size={12} style={{ display: 'inline', marginRight: 4 }} />
                  Data-Verified ({rulesSummary.verified_rules || 0})
                </button>
                <button
                  className={`filter-chip ${ruleStatusFilter === 'ai_suggested' ? 'active' : ''}`}
                  onClick={() => setRuleStatusFilter('ai_suggested')}
                >
                  <Sparkles size={12} style={{ display: 'inline', marginRight: 4 }} />
                  AI-Priors ({rulesSummary.ai_suggested_rules || 0})
                </button>
                <button
                  className={`filter-chip ${ruleStatusFilter === 'muted' ? 'active' : ''}`}
                  onClick={() => setRuleStatusFilter('muted')}
                >
                  <VolumeX size={12} style={{ display: 'inline', marginRight: 4 }} />
                  Muted ({rulesSummary.muted_rules || 0})
                </button>
              </div>

              <button
                type="button"
                className="btn-console-outline"
                onClick={handleReseedPriors}
                disabled={isReseedingPriors}
                title="Regenerate LLM-seeded cold-start priors grounded in active store catalog"
              >
                {isReseedingPriors ? (
                  <>
                    <RefreshCw size={13} className="animate-spin" />
                    <span>Seeding Priors…</span>
                  </>
                ) : (
                  <>
                    <Sparkles size={13} color="var(--accent-mustard)" />
                    <span>Regenerate AI Priors</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Growth Rules Table */}
          <div className="console-table-card">
            <div className="console-table-scroll">
              <table className="console-table">
              <thead>
                <tr>
                  <th style={{ width: '30%' }}>Association Rule (Trigger → Recommendation)</th>
                  <th style={{ width: '22%' }}>Evidence Source & Verification</th>
                  <th style={{ width: '26%' }}>Framing & Contextual Reasoning</th>
                  <th>Empirical Conversion</th>
                  <th style={{ textAlign: 'right' }}>Governance</th>
                </tr>
              </thead>
              <tbody>
                {growthRules.length === 0 ? (
                  <tr>
                    <td colSpan="5" className="table-empty-cell">
                      No association rules found matching your filter.
                    </td>
                  </tr>
                ) : (
                  growthRules.map((rule) => {
                    const isMuted = rule.muted;
                    const isVerified = rule.source === 'data_verified' && rule.lift !== null;

                    return (
                      <tr key={rule.rule_id} className={isMuted ? 'muted-rule-row' : ''}>
                        {/* Association Pair */}
                        <td>
                          <div className="rule-pair-visual">
                            <div className="rule-item-box">
                              <div className="rule-item-name" title={rule.trigger_name}>
                                {rule.trigger_name}
                              </div>
                              <div className="rule-item-meta">
                                <span className="category-micro-tag">{rule.trigger_category}</span>
                                <span>₹{rule.trigger_price_rupees}</span>
                              </div>
                            </div>

                            <ArrowRight size={14} className="rule-arrow-icon" />

                            <div className="rule-item-box target">
                              <div className="rule-item-name" title={rule.target_name}>
                                {rule.target_name}
                                {rule.target_boosted && (
                                  <Sparkles size={11} color="var(--accent-mustard)" style={{ display: 'inline', marginLeft: 4 }} />
                                )}
                              </div>
                              <div className="rule-item-meta">
                                <span className="category-micro-tag">{rule.target_category}</span>
                                <span>₹{rule.target_price_rupees}</span>
                              </div>
                            </div>
                          </div>
                        </td>

                        {/* Evidence Source & Verification Tracker */}
                        <td>
                          {isVerified ? (
                            <div>
                              <div className="source-tag-verified">
                                <CheckCircle2 size={12} />
                                <span>Data-Verified Rule</span>
                              </div>
                              <div className="rule-stat-badges" style={{ marginTop: '0.35rem' }}>
                                <span className="stat-badge lift" title="Empirical Market Basket Lift Multiplier">
                                  {rule.lift.toFixed(2)}x Lift
                                </span>
                                <span className="stat-badge support" title="Real co-occurrence count across completed orders">
                                  {rule.co_occurrence_count} orders ({(rule.support * 100).toFixed(1)}% Sup)
                                </span>
                              </div>
                            </div>
                          ) : (
                            <div>
                              <div className="source-tag-ai">
                                <Sparkles size={12} />
                                <span>AI-Suggested Prior</span>
                              </div>
                              <div className="verification-tracker" style={{ marginTop: '0.35rem' }}>
                                <div className="verification-bar">
                                  <div
                                    className="verification-bar-fill"
                                    style={{ width: `${Math.min(100, ((rule.co_occurrence_count || 0) / 8) * 100)}%` }}
                                  />
                                </div>
                                <span className="verification-text">
                                  {rule.co_occurrence_count || 0} of 8 orders needed to verify
                                </span>
                              </div>
                            </div>
                          )}
                        </td>

                        {/* Framing & LLM Reasoning */}
                        <td>
                          <div className="rule-plain-framing">
                            {isVerified ? (
                              <span>"{rule.plain_language}"</span>
                            ) : (
                              <div>
                                <span className="llm-reasoning-quote">"{rule.reasoning || rule.plain_language}"</span>
                                <div className="llm-badge-sub">Grounded LLM Merchandising Prior</div>
                              </div>
                            )}
                          </div>
                        </td>

                        {/* Empirical Conversion */}
                        <td>
                          <div className="rule-empirical-stats">
                            <div className="empirical-row">
                              <span className="empirical-label">Offered:</span>
                              <strong>{rule.times_offered}x</strong>
                              <span className="empirical-label" style={{ marginLeft: 6 }}>Accepted:</span>
                              <strong>{rule.times_accepted}x</strong>
                            </div>
                            <div className="empirical-row">
                              <span className="empirical-label">Conv:</span>
                              <strong style={{ color: rule.conversion_rate_pct > 0 ? 'var(--accent-teal)' : 'inherit' }}>
                                {rule.conversion_rate_pct}%
                              </strong>
                              {rule.revenue_lift_rupees > 0 && (
                                <span className="rule-rev-tag">+₹{rule.revenue_lift_rupees.toFixed(0)}</span>
                              )}
                            </div>
                          </div>
                        </td>

                        {/* Governance Mute/Unmute Lever */}
                        <td style={{ textAlign: 'right' }}>
                          <div className="rule-action-cell">
                            {isMuted ? (
                              <button
                                type="button"
                                className="btn-rule-unmute"
                                onClick={() => handleToggleMuteRule(rule)}
                                disabled={mutingRuleId === rule.rule_id}
                                title="Unmute rule and restore to active recommendations"
                              >
                                <Volume2 size={13} />
                                <span>Unmute</span>
                              </button>
                            ) : (
                              <button
                                type="button"
                                className="btn-rule-mute"
                                onClick={() => handleToggleMuteRule(rule)}
                                disabled={mutingRuleId === rule.rule_id}
                                title="Mute rule to immediately exclude from buyer agent recommendations"
                              >
                                <VolumeX size={13} />
                                <span>Mute Rule</span>
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
            </div>
          </div>

          {/* ─────────────────────────────────────────────────────────────────── */}
          {/* ── Scalable Architecture: Category Compatibility & Embeddings ── */}
          {/* ─────────────────────────────────────────────────────────────────── */}
          <div className="scalable-layers-grid" style={{ marginTop: '2rem' }}>
            {/* Card 1: Category Compatibility Graph */}
            <div className="console-card">
              <div className="console-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div className="card-title-wrap">
                    <Layers size={16} color="var(--accent-teal)" />
                    <h3 className="console-card-title">Scalable Layer 1: Category Compatibility Graph</h3>
                  </div>
                  <p className="console-card-desc">
                    High-level cross-category affinities generated by LLM cold-start. Scales by category count (not product count).
                  </p>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    type="button"
                    className="btn-console-outline"
                    onClick={() => setShowAddCompatModal(!showAddCompatModal)}
                  >
                    <Plus size={13} />
                    <span>Add Pair</span>
                  </button>
                  <button
                    type="button"
                    className="btn-console-outline"
                    onClick={handleGenerateCompat}
                    disabled={isGeneratingCompat}
                    title="Regenerate category compatibility graph with LLM. Preserves merchant-locked pairs."
                  >
                    {isGeneratingCompat ? (
                      <>
                        <RefreshCw size={13} className="animate-spin" />
                        <span>Generating…</span>
                      </>
                    ) : (
                      <>
                        <Sparkles size={13} color="var(--accent-mustard)" />
                        <span>Regenerate Graph</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Add Custom Pair Inline Modal / Form */}
              {showAddCompatModal && (
                <form onSubmit={handleAddCompat} className="compat-add-form" style={{ padding: '1rem', background: 'var(--bg-paper-tint)', borderBottom: '1px solid var(--hairline)', marginBottom: '0.5rem' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 2fr auto', gap: '8px', alignItems: 'end' }}>
                    <div>
                      <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--ink-secondary)', display: 'block', marginBottom: 4 }}>
                        Category A
                      </label>
                      <select
                        value={newCompatA}
                        onChange={(e) => setNewCompatA(e.target.value)}
                        className="console-select"
                        style={{ width: '100%', padding: '6px 8px', fontSize: '0.8rem' }}
                      >
                        <option value="">Select Category A</option>
                        {policyData.available_categories.map(c => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--ink-secondary)', display: 'block', marginBottom: 4 }}>
                        Category B
                      </label>
                      <select
                        value={newCompatB}
                        onChange={(e) => setNewCompatB(e.target.value)}
                        className="console-select"
                        style={{ width: '100%', padding: '6px 8px', fontSize: '0.8rem' }}
                      >
                        <option value="">Select Category B</option>
                        {policyData.available_categories.map(c => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--ink-secondary)', display: 'block', marginBottom: 4 }}>
                        Reasoning / Merchandising Rule
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. Riders need protective gear and accessories"
                        value={newCompatReason}
                        onChange={(e) => setNewCompatReason(e.target.value)}
                        className="console-input"
                        style={{ width: '100%', padding: '6px 8px', fontSize: '0.8rem' }}
                      />
                    </div>

                    <div style={{ display: 'flex', gap: '4px' }}>
                      <button
                        type="submit"
                        className="btn-console-primary"
                        disabled={isAddingCompat}
                        style={{ padding: '6px 12px', fontSize: '0.8rem' }}
                      >
                        {isAddingCompat ? 'Saving…' : 'Save & Lock'}
                      </button>
                      <button
                        type="button"
                        className="btn-console-outline"
                        onClick={() => setShowAddCompatModal(false)}
                        style={{ padding: '6px 8px' }}
                      >
                        <X size={14} />
                      </button>
                    </div>
                  </div>
                </form>
              )}

              {/* Category Compat List */}
              <div className="console-table-scroll" style={{ maxHeight: '320px' }}>
                <table className="console-table">
                  <thead>
                    <tr>
                      <th style={{ width: '35%' }}>Compatible Categories</th>
                      <th>Merchandising Reasoning</th>
                      <th style={{ width: '15%' }}>Governance Status</th>
                      <th style={{ textAlign: 'right', width: '10%' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {compatPairs.length === 0 ? (
                      <tr>
                        <td colSpan="4" className="table-empty-cell">
                          No category compatibility pairs recorded. Click 'Regenerate Graph' to seed from catalog.
                        </td>
                      </tr>
                    ) : (
                      compatPairs.slice(0, 30).map((pair, idx) => (
                        <tr key={`${pair.category_a}__${pair.category_b}__${idx}`}>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem' }}>
                              <span className="category-micro-tag" style={{ fontWeight: 600 }}>{pair.category_a}</span>
                              <ArrowRight size={12} color="var(--ink-muted)" />
                              <span className="category-micro-tag" style={{ fontWeight: 600 }}>{pair.category_b}</span>
                            </div>
                          </td>
                          <td style={{ fontSize: '0.78rem', color: 'var(--ink-secondary)' }}>
                            {pair.reasoning}
                          </td>
                          <td>
                            {pair.editable ? (
                              <span className="source-tag-ai" style={{ fontSize: '0.68rem' }}>
                                AI-Generated
                              </span>
                            ) : (
                              <span className="source-tag-verified" style={{ fontSize: '0.68rem' }}>
                                <Lock size={10} style={{ display: 'inline', marginRight: 2 }} />
                                Merchant-Locked
                              </span>
                            )}
                          </td>
                          <td style={{ textAlign: 'right' }}>
                            <button
                              type="button"
                              className="btn-rule-mute"
                              onClick={() => handleDeleteCompat(pair.category_a, pair.category_b)}
                              title="Delete compatibility pair and lock against future regeneration"
                              style={{ padding: '2px 6px', fontSize: '0.7rem' }}
                            >
                              <X size={11} />
                              <span>Remove</span>
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Card 2: Co-Purchase Embeddings (Layer 2) */}
            <div className="console-card" style={{ marginTop: '1.25rem' }}>
              <div className="console-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div className="card-title-wrap">
                    <BarChart3 size={16} color="var(--accent-mustard)" />
                    <h3 className="console-card-title">Scalable Layer 2: Co-Purchase Embeddings (item2vec)</h3>
                  </div>
                  <p className="console-card-desc">
                    Trained over real order sequences only (<span style={{ fontFamily: 'var(--font-mono)' }}>is_synthetic = 0</span>). Requires $\ge 50$ real completed orders.
                  </p>
                </div>

                <div>
                  <button
                    type="button"
                    className="btn-console-primary"
                    onClick={handleTrainEmbeddings}
                    disabled={isTrainingEmbeddings || embeddingStatus.real_order_count < embeddingStatus.min_orders_required}
                    title={
                      embeddingStatus.real_order_count < embeddingStatus.min_orders_required
                        ? `Requires at least ${embeddingStatus.min_orders_required} real orders (currently ${embeddingStatus.real_order_count})`
                        : "Train item2vec skip-gram embeddings over real orders"
                    }
                  >
                    {isTrainingEmbeddings ? (
                      <>
                        <RefreshCw size={13} className="animate-spin" />
                        <span>Training Vectors…</span>
                      </>
                    ) : (
                      <>
                        <Zap size={13} />
                        <span>Train Embeddings</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              <div style={{ padding: '1rem', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', background: 'var(--bg-paper-tint)', borderTop: '1px solid var(--hairline)' }}>
                <div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--ink-muted)', textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>Real Orders</div>
                  <div style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--ink)' }}>{embeddingStatus.real_order_count}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--ink-secondary)' }}>Minimum needed: {embeddingStatus.min_orders_required}</div>
                </div>

                <div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--ink-muted)', textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>Training Readiness</div>
                  <div style={{ fontSize: '1.2rem', fontWeight: 700, color: embeddingStatus.ready ? 'var(--accent-teal)' : 'var(--alert-brick)' }}>
                    {embeddingStatus.ready ? 'Ready to Train' : 'Gating Active'}
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--ink-secondary)' }}>
                    {embeddingStatus.ready ? 'Sufficient order volume' : `${Math.max(0, embeddingStatus.min_orders_required - embeddingStatus.real_order_count)} more orders needed`}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--ink-muted)', textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>SKUs with Vectors</div>
                  <div style={{ fontSize: '1.2rem', fontWeight: 700, color: embeddingStatus.skus_with_embeddings > 0 ? 'var(--accent-teal)' : 'var(--ink-muted)' }}>
                    {embeddingStatus.skus_with_embeddings}
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--ink-secondary)' }}>In-stock catalog items</div>
                </div>

                <div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--ink-muted)', textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>Model Status</div>
                  <div style={{ fontSize: '1.2rem', fontWeight: 700, color: embeddingStatus.trained ? 'var(--accent-teal)' : 'var(--accent-mustard)' }}>
                    {embeddingStatus.trained ? 'Trained (Active)' : 'Cold-Start Fallback'}
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--ink-secondary)' }}>
                    {embeddingStatus.trained ? 'Layer 2 active in blend' : 'Layers 1, 3 & 4 active'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
