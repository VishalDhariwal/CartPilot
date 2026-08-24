import React, { useState, useEffect, useMemo, useRef } from 'react';
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
  Plus,
  Archive,
  Play,
  Eye,
  Bot,
  Activity,
  Compass,
  Clock,
  ArrowUpRight,
  CheckSquare,
  ChevronDown,
  ChevronUp,
  Info,
  HelpCircle,
  History,
  FileText,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';

const BASE_URL = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000';

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

export default function MerchantConsole() {
  const [activeTab, setActiveTab] = useState('growth-manager'); // 'growth-manager' | 'growth-rules' | 'catalog' | 'policy'
  const [loading, setLoading] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);

  // ─── TAB 0: AI Growth Manager State ─────────────────────────────────────────
  const [growthMetrics, setGrowthMetrics] = useState({
    realized_gross_revenue_rupees: 0,
    observed_ai_attributed_revenue_rupees: 0,
    cross_sell_revenue_rupees: 0,
    recovery_attributed_revenue_rupees: 0,
    gross_recovered_revenue_rupees: 0,
    recoverable_cart_value_rupees: 0,
    recoverable_cart_count: 0,
    inventory_exposure_value_rupees: 0,
    organic_baseline_revenue_rupees: 0,
    aov_rupees: 0,
    total_orders_count: 0,
    succeeded_payments_count: 0,
    accepted_upsells_count: 0,
    total_upsells_offered: 0,
    upsell_attachment_rate: 0,
    active_opportunities_count: 0,
    recovery_attribution_percent: 60,
    recovery_idle_threshold_minutes: 120
  });
  const [growthOpportunities, setGrowthOpportunities] = useState([]);
  const [growthLearning, setGrowthLearning] = useState(null);
  const [growthTimeline, setGrowthTimeline] = useState([]);
  const [expandedWhyAction, setExpandedWhyAction] = useState({});
  const [growthMode, setGrowthMode] = useState('suggested'); // 'manual' | 'suggested' | 'autonomous'
  const [promoSystemState, setPromoSystemState] = useState(null);
  const [workerStatus, setWorkerStatus] = useState(null);
  const [isGrowthLoading, setIsGrowthLoading] = useState(false);
  const [executingActionId, setExecutingActionId] = useState(null);
  const [lastGrowthUpdated, setLastGrowthUpdated] = useState(null);
  const isFetchingGrowthRef = useRef(false);
  const [recoveryIdleMinutes, setRecoveryIdleMinutes] = useState(120);
  const [isSavingRecoveryPolicy, setIsSavingRecoveryPolicy] = useState(false);

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
  const [catalogPage, setCatalogPage] = useState(1);
  const [catalogTotal, setCatalogTotal] = useState(0);
  const [catalogHasMore, setCatalogHasMore] = useState(false);
  const [isLoadingMoreCatalog, setIsLoadingMoreCatalog] = useState(false);

  // ─── TAB 3: Growth Rules & Live Preview State ─────────────────────────────
  const [growthSubTab, setGrowthSubTab] = useState('live_preview'); // 'live_preview' | 'verified' | 'retired'
  const [previewSku, setPreviewSku] = useState('SUN-FAS-PAR-157'); // default: Party Glasses
  const [previewSearch, setPreviewSearch] = useState('');
  const [previewData, setPreviewData] = useState(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [growthRules, setGrowthRules] = useState([]);
  const [rulesPage, setRulesPage] = useState(1);
  const [rulesTotal, setRulesTotal] = useState(0);
  const [rulesHasMore, setRulesHasMore] = useState(false);
  const [isLoadingMoreRules, setIsLoadingMoreRules] = useState(false);
  const [compatVisibleCount, setCompatVisibleCount] = useState(50);
  const [timelineVisibleCount, setTimelineVisibleCount] = useState(50);

  const [rulesSummary, setRulesSummary] = useState({
    total_rules: 0,
    active_rules: 0,
    verified_rules: 0,
    category_compat_rules: 0,
    retired_priors: 0,
    muted_rules: 0,
    total_offered: 0,
    total_accepted: 0,
    overall_conversion_pct: 0,
    total_revenue_lift_rupees: 0
  });
  const [ruleSearch, setRuleSearch] = useState('');
  const [ruleStatusFilter, setRuleStatusFilter] = useState('all'); // 'all' | 'data_verified' | 'retired' | 'active' | 'muted'
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

  // ─── Evidence-Based Promotion Experiments & Observational Legacy State ───
  const [promotionExperiments, setPromotionExperiments] = useState([]);
  const [legacyAssessments, setLegacyAssessments] = useState([]);
  const [isSubmittingDecision, setIsSubmittingDecision] = useState({});
  const [isReconcilingSku, setIsReconcilingSku] = useState({});

  // ─── Growth Manager Modular Sub-Views & Table Controls ────────────────────
  const [managerView, setManagerView] = useState('pipeline'); // 'pipeline' | 'experiments' | 'legacy' | 'ledger' | 'timeline'
  const [legacySearch, setLegacySearch] = useState('');
  const [legacyFilter, setLegacyFilter] = useState('ALL'); // 'ALL' | 'KEEP' | 'RETIRE' | 'CONVERT_TO_EXPERIMENT'
  const [legacyPage, setLegacyPage] = useState(1);
  const LEGACY_PAGE_SIZE = 12;

  const [timelineFilter, setTimelineFilter] = useState('ALL');
  const [timelineSearch, setTimelineSearch] = useState('');

  const [oppFilter, setOppFilter] = useState('ALL'); // 'ALL' | 'RECOVER_CART' | 'CROSS_SELL' | 'PROMOTE_PRODUCT' | 'NO_ACTION'
  const [oppSearch, setOppSearch] = useState('');

  // Spend cap and autonomy presets
  const spendCapPresets = [500, 1000, 2500, 5000, 10000, 50000];
  const autonomyPresets = [1000, 2500, 5000, 10000, 25000, 50000];

  // Helper to show transient toasts
  const showToast = (msg, type = 'success') => {
    setToastMessage({ text: msg, type });
    setTimeout(() => setToastMessage(null), 4000);
  };

  // ─── Initial Fetch on Mount & 5-minute Polling ────────────────────────────
  useEffect(() => {
    fetchGrowthData();
    fetchPolicy();
    fetchCatalog();
    fetchGrowthRules();
    fetchCategoryCompat();
    fetchEmbeddingStatus();

    // 5-minute background polling for Growth Manager
    const interval = setInterval(() => {
      fetchGrowthData(true);
    }, 5 * 60 * 1000);

    return () => clearInterval(interval);
  }, []);

  /* ─── Fetch Growth Manager Data ────────────────────────────────────────── */
  const fetchGrowthData = async (silent = false) => {
    if (isFetchingGrowthRef.current) return;
    isFetchingGrowthRef.current = true;
    if (!silent) setIsGrowthLoading(true);
    try {
      const [metRes, oppRes, learnRes, workRes, timeRes, promoRes, legRes] = await Promise.all([
        fetch(`${BASE_URL}/api/growth/metrics`),
        fetch(`${BASE_URL}/api/growth/opportunities`),
        fetch(`${BASE_URL}/api/growth/performance`),
        fetch(`${BASE_URL}/api/growth/worker-status`),
        fetch(`${BASE_URL}/api/growth/timeline?limit=200`),
        fetch(`${BASE_URL}/api/growth/promotion-experiments`),
        fetch(`${BASE_URL}/api/growth/legacy-boosts-assessment`)
      ]);

      if (metRes.ok) {
        const metData = await metRes.json();
        setGrowthMetrics(metData);
        if (metData.recovery_idle_threshold_minutes != null) {
          setRecoveryIdleMinutes(metData.recovery_idle_threshold_minutes);
        }
      }
      if (oppRes.ok) {
        const oppData = await oppRes.json();
        setGrowthOpportunities(oppData.opportunities || []);
        if (oppData.promotion_system_state) {
          setPromoSystemState(oppData.promotion_system_state);
        }
      }
      if (learnRes.ok) {
        const learnData = await learnRes.json();
        setGrowthLearning(learnData);
        if (learnData.growth_mode) {
          setGrowthMode(learnData.growth_mode);
        }
      }
      if (workRes.ok) {
        const workData = await workRes.json();
        setWorkerStatus(workData);
      }
      if (timeRes && timeRes.ok) {
        const timeData = await timeRes.json();
        setGrowthTimeline(timeData.events || []);
      }
      if (promoRes && promoRes.ok) {
        const pData = await promoRes.json();
        setPromotionExperiments(pData.experiments || []);
        if (pData.system_state) {
          setPromoSystemState(pData.system_state);
        }
      }
      if (legRes && legRes.ok) {
        const lData = await legRes.json();
        setLegacyAssessments(lData.assessments || []);
      }
      setLastGrowthUpdated(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    } catch (err) {
      console.error('Error fetching growth data:', err);
    } finally {
      if (!silent) setIsGrowthLoading(false);
      isFetchingGrowthRef.current = false;
    }
  };

  /* ─── Toggle "Why this action?" Accordion ────────────────────────────────── */
  const toggleWhyAction = (oppId) => {
    setExpandedWhyAction(prev => ({
      ...prev,
      [oppId]: !prev[oppId]
    }));
  };

  /* ─── Execute Next Best Action ─────────────────────────────────────────── */
  const handleExecuteGrowthAction = async (opp) => {
    setExecutingActionId(opp.opportunity_id);
    const actionType = opp.selected_action?.action_type || opp.action_type || opp.type;
    const targetId = opp.selected_action?.target_id || opp.action_target_id;

    if (actionType === 'NO_ACTION' || !opp.action_executable) {
      showToast('This item is for diagnostic merchant review only.', 'info');
      setExecutingActionId(null);
      return;
    }

    try {
      const res = await fetch(`${BASE_URL}/api/growth/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_type: actionType,
          target_id: targetId,
          mode: growthMode
        })
      });
      const data = await res.json();
      if (res.ok) {
        showToast(data.message || `Successfully executed ${actionType}!`);
        await fetchGrowthData(true);
        if (actionType === 'PROMOTE_PRODUCT') {
          fetchCatalog();
        }
      } else {
        showToast(data.detail || 'Failed to execute action', 'error');
      }
    } catch (err) {
      console.error('Error executing growth action:', err);
      showToast('Network error executing growth action', 'error');
    } finally {
      setExecutingActionId(null);
    }
  };

  /* ─── Dismiss Opportunity ──────────────────────────────────────────────── */
  const handleDismissGrowthAction = async (oppId) => {
    try {
      const res = await fetch(`${BASE_URL}/api/growth/actions/${oppId}/dismiss`, {
        method: 'POST'
      });
      if (res.ok) {
        setGrowthOpportunities(prev => prev.filter(o => o.opportunity_id !== oppId));
        showToast('Opportunity dismissed');
      }
    } catch (err) {
      console.error('Error dismissing opportunity:', err);
    }
  };

  /* ─── Submit Promotion Experiment Decision (Day-14 Decision Gate) ──────── */
  const handleExperimentDecision = async (expId, decision) => {
    setIsSubmittingDecision(prev => ({ ...prev, [expId]: true }));
    try {
      const res = await fetch(`${BASE_URL}/api/growth/promotion-experiments/${expId}/decision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision })
      });
      const data = await res.json();
      if (res.ok) {
        showToast(data.message || `Decision recorded: ${decision.replace(/_/g, ' ')}`);
        await fetchGrowthData(true);
        await fetchCatalog();
      } else {
        showToast(data.detail || 'Failed to submit decision', 'error');
      }
    } catch (err) {
      console.error('Error submitting experiment decision:', err);
      showToast('Error submitting decision', 'error');
    } finally {
      setIsSubmittingDecision(prev => ({ ...prev, [expId]: false }));
    }
  };

  /* ─── Reconcile Legacy Boost ───────────────────────────────────────────── */
  const handleReconcileLegacyBoost = async (sku, action) => {
    setIsReconcilingSku(prev => ({ ...prev, [sku]: true }));
    try {
      const res = await fetch(`${BASE_URL}/api/growth/reconcile-legacy-boost`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sku, action })
      });
      const data = await res.json();
      if (res.ok) {
        showToast(data.message || `Legacy boost updated: ${action}`);
        await fetchGrowthData(true);
        await fetchCatalog();
      } else {
        showToast(data.detail || 'Failed to update legacy boost', 'error');
      }
    } catch (err) {
      console.error('Error updating legacy boost:', err);
      showToast('Error updating legacy boost', 'error');
    } finally {
      setIsReconcilingSku(prev => ({ ...prev, [sku]: false }));
    }
  };

  /* ─── Set Growth Autonomy Mode ─────────────────────────────────────────── */
  const handleSetGrowthMode = async (newMode) => {
    try {
      const res = await fetch(`${BASE_URL}/api/growth/mode`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ growth_mode: newMode })
      });
      if (res.ok) {
        setGrowthMode(newMode);
        showToast(`Merchant Growth Autonomy Mode set to '${newMode}'`);
      }
    } catch (err) {
      console.error('Error updating growth mode:', err);
    }
  };

  /* ─── Update Recovery Policy (idle threshold + attribution %) ─────────── */
  const handleUpdateRecoveryPolicy = async (newIdleMinutes) => {
    setIsSavingRecoveryPolicy(true);
    try {
      const res = await fetch(`${BASE_URL}/api/growth/policy`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recovery_idle_threshold_minutes: newIdleMinutes })
      });
      const data = await res.json();
      if (res.ok) {
        setRecoveryIdleMinutes(data.recovery_idle_threshold_minutes);
        showToast(
          newIdleMinutes === 0
            ? 'Demo mode: idle gate removed (0 min threshold)'
            : `Recovery idle threshold set to ${data.recovery_idle_threshold_minutes} minutes`
        );
        await fetchGrowthData(true);
      } else {
        showToast(data.detail || 'Failed to update recovery policy', 'error');
      }
    } catch (err) {
      console.error('Error updating recovery policy:', err);
      showToast('Network error updating recovery policy', 'error');
    } finally {
      setIsSavingRecoveryPolicy(false);
    }
  };

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

  /* ─── Fetch Catalog & Boost Statuses (Server-Side Pagination) ───────────── */
  const fetchCatalog = async (reset = true) => {
    try {
      const pageToFetch = reset ? 1 : catalogPage + 1;
      const params = new URLSearchParams();
      if (catalogSearch.trim()) params.append('q', catalogSearch.trim());
      if (selectedCategoryFilter !== 'all') params.append('category', selectedCategoryFilter);
      if (showBoostedOnly) params.append('boosted_only', 'true');
      params.append('page', String(pageToFetch));
      params.append('limit', '50');

      if (!reset) setIsLoadingMoreCatalog(true);

      const res = await fetch(`${BASE_URL}/api/console/catalog?${params.toString()}`);
      const data = await res.json();
      if (res.ok) {
        if (reset) {
          setCatalogItems(data.items || []);
          setCatalogPage(1);
        } else {
          setCatalogItems(prev => [...prev, ...(data.items || [])]);
          setCatalogPage(pageToFetch);
        }
        setCatalogTotal(data.total || 0);
        setCatalogHasMore(Boolean(data.has_more));
        if (data.summary) setCatalogSummary(data.summary);
      }
    } catch (err) {
      console.error('Error fetching catalog:', err);
    } finally {
      setIsLoadingMoreCatalog(false);
    }
  };

  const handleLoadMoreCatalog = () => {
    if (!isLoadingMoreCatalog && catalogHasMore) {
      fetchCatalog(false);
    }
  };

  useEffect(() => {
    fetchCatalog(true);
  }, [catalogSearch, selectedCategoryFilter, showBoostedOnly]);

  /* ─── Fetch Growth Rules & Empirical Stats (Server-Side Pagination) ──────── */
  const fetchGrowthRules = async (reset = true) => {
    try {
      const pageToFetch = reset ? 1 : rulesPage + 1;
      const params = new URLSearchParams();
      if (ruleSearch.trim()) params.append('q', ruleSearch.trim());
      if (ruleStatusFilter !== 'all') params.append('status', ruleStatusFilter);
      params.append('page', String(pageToFetch));
      params.append('limit', '50');

      if (!reset) setIsLoadingMoreRules(true);

      const res = await fetch(`${BASE_URL}/api/console/growth-rules?${params.toString()}`);
      const data = await res.json();
      if (res.ok) {
        if (reset) {
          setGrowthRules(data.rules || []);
          setRulesPage(1);
        } else {
          setGrowthRules(prev => [...prev, ...(data.rules || [])]);
          setRulesPage(pageToFetch);
        }
        setRulesTotal(data.total || 0);
        setRulesHasMore(Boolean(data.has_more));
        if (data.summary) setRulesSummary(data.summary);
      }
    } catch (err) {
      console.error('Error fetching growth rules:', err);
    } finally {
      setIsLoadingMoreRules(false);
    }
  };

  const handleLoadMoreRules = () => {
    if (!isLoadingMoreRules && rulesHasMore) {
      fetchGrowthRules(false);
    }
  };

  useEffect(() => {
    fetchGrowthRules(true);
  }, [ruleSearch, ruleStatusFilter, growthSubTab]);

  /* ─── Live Recommendation Preview Sandbox Fetcher ───────────────────────── */
  const handleFetchLivePreview = async (skuToFetch) => {
    const targetSku = skuToFetch || previewSku;
    if (!targetSku) return;
    setIsPreviewLoading(true);
    try {
      const res = await fetch(`${BASE_URL}/api/console/growth-rules/live-preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sku: targetSku, top_k: 4 })
      });
      const data = await res.json();
      if (res.ok) {
        setPreviewData(data);
        setPreviewSku(targetSku);
      } else {
        showToast(data.detail || 'Could not compute live preview', 'error');
      }
    } catch (err) {
      console.error('Error fetching live preview:', err);
    } finally {
      setIsPreviewLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'growth-rules' && !previewData && !isPreviewLoading) {
      handleFetchLivePreview(previewSku || 'SUN-FAS-PAR-157');
    }
  }, [activeTab]);

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

  // ─── Filtered Opportunities ──────────────────────────────────────────────
  const filteredOpportunities = useMemo(() => {
    return growthOpportunities.filter(opp => {
      const actionType = opp.selected_action?.action_type || opp.action_type || opp.type;
      const isNoAction = opp.selected_action?.action_type === 'NO_ACTION' || !opp.action_executable;
      
      const matchesFilter = oppFilter === 'ALL' ||
        (oppFilter === 'NO_ACTION' && isNoAction) ||
        (oppFilter === 'RECOVER_CART' && actionType === 'RECOVER_CART') ||
        (oppFilter === 'CROSS_SELL' && actionType === 'CROSS_SELL') ||
        (oppFilter === 'PROMOTE_PRODUCT' && (actionType === 'PROMOTE_PRODUCT' || (opp.goal && opp.goal.includes('INVENTORY'))) && !isNoAction);

      const matchesSearch = !oppSearch.trim() ||
        (opp.business_problem && opp.business_problem.toLowerCase().includes(oppSearch.toLowerCase())) ||
        (opp.title && opp.title.toLowerCase().includes(oppSearch.toLowerCase())) ||
        (opp.opportunity_id && opp.opportunity_id.toLowerCase().includes(oppSearch.toLowerCase())) ||
        (opp.evidence?.sku && opp.evidence.sku.toLowerCase().includes(oppSearch.toLowerCase())) ||
        (opp.evidence?.product_name && opp.evidence.product_name.toLowerCase().includes(oppSearch.toLowerCase()));

      return matchesFilter && matchesSearch;
    });
  }, [growthOpportunities, oppFilter, oppSearch]);

  // ─── Filtered & Paginated Legacy Boosts ────────────────────────────────────
  const filteredLegacyAssessments = useMemo(() => {
    return legacyAssessments.filter(leg => {
      const matchesSearch = !legacySearch.trim() || 
        leg.name.toLowerCase().includes(legacySearch.toLowerCase()) || 
        leg.sku.toLowerCase().includes(legacySearch.toLowerCase()) ||
        leg.category.toLowerCase().includes(legacySearch.toLowerCase());
      const matchesFilter = legacyFilter === 'ALL' || leg.suggested_action === legacyFilter;
      return matchesSearch && matchesFilter;
    });
  }, [legacyAssessments, legacySearch, legacyFilter]);

  const paginatedLegacyAssessments = useMemo(() => {
    const start = (legacyPage - 1) * LEGACY_PAGE_SIZE;
    return filteredLegacyAssessments.slice(start, start + LEGACY_PAGE_SIZE);
  }, [filteredLegacyAssessments, legacyPage]);

  const totalLegacyPages = Math.ceil(filteredLegacyAssessments.length / LEGACY_PAGE_SIZE) || 1;

  // ─── Filtered Timeline ───────────────────────────────────────────────────
  const filteredTimeline = useMemo(() => {
    return growthTimeline
      .filter(evt => {
        const matchesSearch = !timelineSearch.trim() ||
          (evt.detail && evt.detail.toLowerCase().includes(timelineSearch.toLowerCase())) ||
          (evt.event && evt.event.toLowerCase().includes(timelineSearch.toLowerCase())) ||
          (evt.ref_id && evt.ref_id.toLowerCase().includes(timelineSearch.toLowerCase()));
        const matchesFilter = timelineFilter === 'ALL' || 
          (evt.event && evt.event.toUpperCase().includes(timelineFilter.toUpperCase())) ||
          (evt.detail && evt.detail.toUpperCase().includes(timelineFilter.toUpperCase()));
        return matchesSearch && matchesFilter;
      })
      .sort((a, b) => (new Date(b.created_at || 0) - new Date(a.created_at || 0)) || ((b.id || 0) - (a.id || 0)));
  }, [growthTimeline, timelineSearch, timelineFilter]);

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
          className={`console-tab-btn ${activeTab === 'growth-manager' ? 'active' : ''}`}
          onClick={() => setActiveTab('growth-manager')}
        >
          <Bot size={16} />
          <span>AI Growth Manager</span>
          {growthOpportunities.length > 0 && (
            <span className="growth-tab-pill">
              {growthOpportunities.length} Opps
            </span>
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
          className={`console-tab-btn ${activeTab === 'policy' ? 'active' : ''}`}
          onClick={() => setActiveTab('policy')}
        >
          <Shield size={16} />
          <span>Policy Control</span>
        </button>
      </div>

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* ── TAB 0: AI Growth Manager ────────────────────────────────────── */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {activeTab === 'growth-manager' && (
        <div className="console-tab-content">
          {/* Header Bar: Autonomy Control & Agent Lifecycle State */}
          <div className="growth-header-bar">
            <div>
              <div className="growth-header-title">
                <Bot size={22} color="#059669" />
                <span>AI Growth Manager</span>
                <span className="growth-action-badge" style={{ background: '#ECFDF5', color: '#065F46', border: '1px solid #A7F3D0' }}>
                  Track 01 · Agentic Commerce
                </span>
              </div>
              <div className="growth-header-sub">
                Autonomous agent continuously observing store friction, prioritizing Next Best Actions, and learning from captured outcomes.
              </div>

              {/* Live Worker Telemetry & Scan Telemetry */}
              <div style={{ marginTop: '0.6rem', display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                {growthMode === 'autonomous' ? (
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: '#ECFDF5', border: '1px solid #A7F3D0', padding: '3px 10px', borderRadius: '9999px', fontSize: '0.74rem', color: '#065F46', fontWeight: 600 }}>
                    <span className="live-pulse-dot" />
                    <span>Autonomous Worker: Active (5m Loop)</span>
                    <span style={{ color: '#059669', fontFamily: 'var(--font-mono)' }}>· {workerStatus?.actions_executed_total || 0} executed</span>
                  </div>
                ) : growthMode === 'suggested' ? (
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: '#EFF6FF', border: '1px solid #BFDBFE', padding: '3px 10px', borderRadius: '9999px', fontSize: '0.74rem', color: '#1E40AF', fontWeight: 600 }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#3B82F6', display: 'inline-block' }} />
                    <span>Suggested Mode: Agent prepares actions for 1-click merchant approval</span>
                  </div>
                ) : (
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'var(--bg-paper-tint)', border: '1px solid var(--hairline)', padding: '3px 10px', borderRadius: '9999px', fontSize: '0.74rem', color: 'var(--ink-muted)' }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#9CA3AF', display: 'inline-block' }} />
                    <span>Manual Mode: Agent detects opportunities · Merchant decides execution</span>
                  </div>
                )}
                {workerStatus?.last_action_at && (
                  <span style={{ fontSize: '0.72rem', color: 'var(--ink-muted)', fontFamily: 'var(--font-mono)' }}>
                    Last action: {new Date(workerStatus.last_action_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                )}
              </div>
            </div>

            <div className="growth-actions-toolbar">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '0.78rem', color: 'var(--ink-secondary)', fontWeight: 600 }}>
                  Autonomy Mode:
                </span>
                <div className="growth-autonomy-toggle">
                  <button
                    type="button"
                    className={`growth-mode-btn ${growthMode === 'manual' ? 'active' : ''}`}
                    onClick={() => handleSetGrowthMode('manual')}
                    title="Manual: Agent detects → Merchant decides"
                  >
                    Manual
                  </button>
                  <button
                    type="button"
                    className={`growth-mode-btn ${growthMode === 'suggested' ? 'active' : ''}`}
                    onClick={() => handleSetGrowthMode('suggested')}
                    title="Suggested: Agent detects → Agent prepares → Merchant approves"
                  >
                    Suggested
                  </button>
                  <button
                    type="button"
                    className={`growth-mode-btn ${growthMode === 'autonomous' ? 'active autonomous' : ''}`}
                    onClick={() => handleSetGrowthMode('autonomous')}
                    title="Autonomous: Agent detects → Agent decides → Policy approves → Agent executes"
                  >
                    Autonomous
                  </button>
                </div>
              </div>

              {/* Recovery Idle Gate — live-configurable, demo-friendly */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '0.73rem', color: 'var(--ink-secondary)', fontWeight: 600, whiteSpace: 'nowrap' }}>
                  Recovery Idle Gate:
                </span>
                <div style={{ display: 'flex', gap: '4px' }}>
                  {[0, 5, 30, 60, 120].map(mins => (
                    <button
                      key={mins}
                      type="button"
                      onClick={() => handleUpdateRecoveryPolicy(mins)}
                      disabled={isSavingRecoveryPolicy}
                      title={mins === 0 ? 'Demo mode: no idle gate applied' : `Cart must be idle ≥ ${mins}m for recovery attribution`}
                      style={{
                        padding: '2px 7px',
                        borderRadius: '5px',
                        fontSize: '0.7rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                        border: '1px solid',
                        background: recoveryIdleMinutes === mins ? (mins === 0 ? '#FEF3C7' : '#ECFDF5') : 'transparent',
                        borderColor: recoveryIdleMinutes === mins ? (mins === 0 ? '#F59E0B' : '#059669') : 'var(--hairline)',
                        color: recoveryIdleMinutes === mins ? (mins === 0 ? '#92400E' : '#065F46') : 'var(--ink-muted)',
                        transition: 'all 0.15s ease'
                      }}
                    >
                      {mins === 0 ? '0m ⚡Demo' : `${mins}m`}
                    </button>
                  ))}
                </div>
                <span style={{ fontSize: '0.65rem', color: 'var(--ink-muted)', fontStyle: 'italic' }}>
                  {recoveryIdleMinutes === 0 ? 'Demo mode — no idle gate' : `${recoveryIdleMinutes}m`}
                </span>
              </div>

              <div className="growth-refresh-indicator">
                {lastGrowthUpdated && <span>Updated {lastGrowthUpdated}</span>}
                <button
                  type="button"
                  className="btn-icon-refresh"
                  onClick={() => fetchGrowthData(false)}
                  disabled={isGrowthLoading}
                  title="Refresh opportunities & metrics"
                  style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: '4px', display: 'flex', alignItems: 'center' }}
                >
                  <RefreshCw size={14} className={isGrowthLoading ? 'spin-anim' : ''} color="var(--ink-secondary)" />
                </button>
              </div>
            </div>
          </div>

          {/* ── SECTION 1: BUSINESS IMPACT SCORECARD ── */}
          <div style={{ marginBottom: '1.25rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.6rem' }}>
              <div style={{ fontSize: '0.92rem', fontWeight: 700, color: 'var(--ink)', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <DollarSign size={16} color="#059669" />
                <span>Business Impact & Revenue Streams</span>
              </div>
              <span style={{ fontSize: '0.74rem', color: 'var(--ink-muted)', fontFamily: 'var(--font-mono)' }}>
                Audited Razorpay Rails · Strict Separation of Risk & Cash
              </span>
            </div>

            <div className="growth-kpi-grid">
              {/* Card 1: Realized Gross Revenue */}
              <div className="growth-kpi-card">
                <div className="growth-kpi-label">
                  <span>Realized Gross Revenue</span>
                  <span className="growth-kpi-chip">Captured Cash</span>
                </div>
                <div className="growth-kpi-value">
                  ₹{(growthMetrics.realized_gross_revenue_rupees || growthMetrics.total_revenue_rupees || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
                <div className="growth-kpi-sub">
                  Across {growthMetrics.succeeded_payments_count || 0} settled payments (₹{(growthMetrics.organic_baseline_revenue_rupees || 0).toLocaleString('en-IN')} organic baseline)
                </div>

                <KpiTooltip
                  title="Realized Gross Revenue (Captured Cash)"
                  category="Settled Cash"
                  description="Total rupee amount successfully captured and settled from customers through Razorpay payment rails."
                  formula="∑(payment_mandates.amount_paise WHERE status='succeeded')"
                  source="payment_mandates • Razorpay Settlement"
                  align="left"
                />
              </div>

              {/* Card 2: Observed AI Revenue */}
              <div className="growth-kpi-card">
                <div className="growth-kpi-label">
                  <span>Observed AI Revenue</span>
                  <span className="growth-kpi-chip">Attributed Lift</span>
                </div>
                <div className="growth-kpi-value">
                  ₹{(growthMetrics.observed_ai_attributed_revenue_rupees || growthMetrics.observed_ai_revenue_rupees || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
                <div className="growth-kpi-sub">
                  Cross-Sell: ₹{(growthMetrics.cross_sell_revenue_rupees || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })} · Recovery: ₹{(growthMetrics.recovery_attributed_revenue_rupees || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>

                <KpiTooltip
                  title="Observed AI Attributed Revenue"
                  category="AI Attribution"
                  description="Direct monetary lift produced by CartPilot's 3-tier recommendation engine and autonomous cart recoveries."
                  formula="Cross_Sell_Lift + (0.60 × Eligible_Settled_Recoveries)"
                  source="upsell_events • cart_recovery_actions"
                />
              </div>

              {/* Card 3: Recoverable Cart Value (At Risk) */}
              <div className="growth-kpi-card">
                <div className="growth-kpi-label">
                  <span>Recoverable Carts</span>
                  <span className="growth-kpi-chip">At Risk</span>
                </div>
                <div className="growth-kpi-value">
                  ₹{(growthMetrics.recoverable_cart_value_rupees || growthMetrics.estimated_opportunity_rupees || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
                <div className="growth-kpi-sub">
                  {growthMetrics.recoverable_cart_count || 0} active abandoned customer carts eligible for recovery
                </div>

                <KpiTooltip
                  title="Recoverable Carts (Pipeline Value)"
                  category="Revenue Opportunity"
                  description="Gross rupee value of active abandoned carts with approved guardrails and active payment links."
                  formula="∑(cart_mandates.total_paise WHERE idle ≥ 10min AND status='approved')"
                  source="cart_mandates • intent_mandates"
                />
              </div>

              {/* Card 4: Inventory Exposure */}
              <div className="growth-kpi-card">
                <div className="growth-kpi-label">
                  <span>Inventory Exposure</span>
                  <span className="growth-kpi-chip">Stagnant Stock</span>
                </div>
                <div className="growth-kpi-value">
                  ₹{(growthMetrics.inventory_exposure_value_rupees || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
                <div className="growth-kpi-sub">
                  Stock value of high-inventory SKUs with weak sales velocity
                </div>

                <KpiTooltip
                  title="Inventory Exposure Value"
                  category="Working Capital"
                  description="Total tied-up capital in catalog items holding high stock but trailing category median sales velocity."
                  formula="∑(price_paise × stock WHERE velocity < cat_median)"
                  source="catalog • inventory_velocity_metrics"
                  align="right"
                />
              </div>
            </div>
          </div>

          {/* ── SUB-NAVIGATION: MODULAR SEGMENTED CONTROLS ── */}
          <div className="growth-manager-subnav">
            <button
              type="button"
              className={`growth-manager-nav-btn ${managerView === 'pipeline' ? 'active' : ''}`}
              onClick={() => setManagerView('pipeline')}
            >
              <Zap size={14} />
              <span>Opportunity Pipeline</span>
              <span className="growth-manager-nav-badge">
                {growthOpportunities.length}
              </span>
            </button>

            <button
              type="button"
              className={`growth-manager-nav-btn ${managerView === 'experiments' ? 'active' : ''}`}
              onClick={() => setManagerView('experiments')}
            >
              <Activity size={14} />
              <span>Controlled Experiments (DiD)</span>
              <span className="growth-manager-nav-badge">
                {promotionExperiments.length}
              </span>
            </button>

            <button
              type="button"
              className={`growth-manager-nav-btn ${managerView === 'legacy' ? 'active' : ''}`}
              onClick={() => setManagerView('legacy')}
            >
              <Shield size={14} />
              <span>Legacy Boosts Queue</span>
              {legacyAssessments.length > 0 && (
                <span className="growth-manager-nav-badge">
                  {legacyAssessments.length}
                </span>
              )}
            </button>

            <button
              type="button"
              className={`growth-manager-nav-btn ${managerView === 'ledger' ? 'active' : ''}`}
              onClick={() => setManagerView('ledger')}
            >
              <BarChart3 size={14} />
              <span>Capability Ledger</span>
            </button>

            <button
              type="button"
              className={`growth-manager-nav-btn ${managerView === 'timeline' ? 'active' : ''}`}
              onClick={() => setManagerView('timeline')}
            >
              <History size={14} />
              <span>Store Activity Stream</span>
              <span className="growth-manager-nav-badge">
                {growthTimeline.length}
              </span>
            </button>
          </div>

          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* ── SUB-VIEW 1: OPPORTUNITY PIPELINE ── */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {managerView === 'pipeline' && (
            <div>
              {/* Promotion Experiment System State Banner */}
              {promoSystemState && (
                <div style={{
                  background: promoSystemState.capacity_full ? 'rgba(234, 88, 12, 0.07)' : 'rgba(5, 150, 105, 0.06)',
                  border: `1px solid ${promoSystemState.capacity_full ? 'rgba(234, 88, 12, 0.25)' : 'rgba(5, 150, 105, 0.25)'}`,
                  borderRadius: '8px',
                  padding: '0.65rem 0.95rem',
                  marginBottom: '1rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '8px'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Activity size={16} color={promoSystemState.capacity_full ? '#EA580C' : '#059669'} />
                    <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--ink)' }}>
                      Active Promotion Experiments: <strong>{promoSystemState.active_experiments_count} / {promoSystemState.max_active_experiments}</strong>
                    </span>
                    <span style={{ fontSize: '0.74rem', color: 'var(--ink-secondary)' }}>
                      ({promoSystemState.legacy_unmanaged_count} legacy unmanaged boosts preserved)
                    </span>
                  </div>
                  <span style={{
                    fontSize: '0.7rem',
                    fontWeight: 700,
                    padding: '3px 8px',
                    borderRadius: '4px',
                    background: promoSystemState.capacity_full ? '#FFEDD5' : '#ECFDF5',
                    color: promoSystemState.capacity_full ? '#C2410C' : '#047857',
                    letterSpacing: '0.03em'
                  }}>
                    {promoSystemState.capacity_full ? 'CAPACITY FULL (OBSERVING)' : `${promoSystemState.available_capacity} SLOTS AVAILABLE`}
                  </span>
                </div>
              )}

              {/* Opportunities Filter Bar */}
              <div className="console-toolbar" style={{ marginBottom: '1rem' }}>
                <div className="toolbar-search-wrap" style={{ flex: 1 }}>
                  <Search size={14} color="var(--ink-muted)" />
                  <input
                    type="text"
                    placeholder="Search opportunities by title, SKU, or business problem…"
                    value={oppSearch}
                    onChange={(e) => setOppSearch(e.target.value)}
                  />
                </div>

                <div className="toolbar-controls-right">
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {[
                      { id: 'ALL', label: `All (${growthOpportunities.length})` },
                      { id: 'RECOVER_CART', label: 'Cart Recovery' },
                      { id: 'CROSS_SELL', label: 'Cross-Sell' },
                      { id: 'PROMOTE_PRODUCT', label: 'Promotion' },
                      { id: 'NO_ACTION', label: 'Diagnostic' }
                    ].map(tab => (
                      <button
                        key={tab.id}
                        type="button"
                        className={`filter-chip ${oppFilter === tab.id ? 'active' : ''}`}
                        onClick={() => setOppFilter(tab.id)}
                        style={{ fontSize: '0.75rem', padding: '4px 9px' }}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {filteredOpportunities.length === 0 ? (
                <div className="console-card" style={{ padding: '2.5rem', textAlign: 'center' }}>
                  <CheckCircle2 size={32} color="#059669" style={{ margin: '0 auto 0.75rem' }} />
                  <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--ink)', marginBottom: '0.35rem' }}>
                    {growthOpportunities.length === 0 ? 'All Growth Opportunities Addressed' : 'No Opportunities Match Filter'}
                  </h3>
                  <p style={{ fontSize: '0.85rem', color: 'var(--ink-secondary)', maxWidth: '500px', margin: '0 auto' }}>
                    {growthOpportunities.length === 0
                      ? 'CartPilot is actively monitoring incoming buyer carts and catalog stock. New recovery, cross-sell, and inventory opportunities will appear automatically.'
                      : 'Try adjusting your search query or filter chip above to view other growth opportunities.'}
                  </p>
                </div>
              ) : (
                <div className="growth-opp-grid">
                  {filteredOpportunities.map((opp) => {
                    const actionType = opp.selected_action?.action_type || opp.action_type || opp.type;
                    const isExpanded = !!expandedWhyAction[opp.opportunity_id];
                    const estValue = opp.estimated_opportunity_value_rupees ?? opp.est_revenue_rupees ?? 0;
                    const evValue = opp.expected_value_rupees ?? 0;
                    const confPct = Math.round((opp.confidence || 0.5) * 100);
                    const isStagnation = actionType === 'PROMOTE_PRODUCT' || (opp.goal && opp.goal.includes('INVENTORY'));
                    const isNoAction = opp.selected_action?.action_type === 'NO_ACTION' || !opp.action_executable;

                    return (
                      <div key={opp.opportunity_id} className={`growth-opp-card ${isNoAction ? 'no-action-card' : ''}`}>
                        <div>
                          {/* Card Top: Badges & Value */}
                          <div className="growth-opp-header">
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                              <span className={`growth-action-badge ${
                                actionType === 'RECOVER_CART' ? 'recover' :
                                actionType === 'CROSS_SELL' ? 'cross_sell' :
                                isNoAction ? 'no_action' :
                                isStagnation ? 'promote' : 'promote'
                              }`}>
                                {actionType === 'RECOVER_CART' && <Clock size={11} />}
                                {actionType === 'CROSS_SELL' && <TrendingUp size={11} />}
                                {isStagnation && !isNoAction && <Sparkles size={11} />}
                                {isNoAction && <Info size={11} />}
                                {isNoAction ? 'INVENTORY_HEALTHY' : isStagnation ? 'INVENTORY_STAGNATION' : actionType}
                              </span>

                              {opp.evidence?.opportunity_reason && (
                                <span style={{ fontSize: '0.68rem', fontWeight: 700, background: '#EFF6FF', border: '1px solid #BFDBFE', padding: '2px 7px', borderRadius: '4px', color: '#1E40AF', letterSpacing: '0.02em' }}>
                                  {opp.evidence.opportunity_reason.replace(/_/g, ' ')}
                                </span>
                              )}

                              {opp.evidence?.product_state && (
                                <span style={{ fontSize: '0.68rem', fontWeight: 600, background: 'var(--bg-paper-tint)', border: '1px solid var(--hairline)', padding: '2px 7px', borderRadius: '4px', color: 'var(--ink-secondary)' }}>
                                  {opp.evidence.product_state.replace(/_/g, ' ')}
                                </span>
                              )}
                            </div>

                            <div style={{ textAlign: 'right' }}>
                              {opp.inventory_value_exposure_rupees > 0 && (
                                <div style={{ fontSize: '0.71rem', color: 'var(--ink-muted)', marginBottom: '1px' }}>
                                  Inventory Value Exposure: <strong>₹{opp.inventory_value_exposure_rupees.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong>
                                </div>
                              )}
                              {estValue > 0 ? (
                                <div>
                                  <span style={{ fontSize: '0.92rem', fontWeight: 700, color: '#059669', fontFamily: 'var(--font-mono)' }}>
                                    +₹{estValue.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                                  </span>
                                  <span style={{ fontSize: '0.64rem', color: 'var(--ink-muted)', fontWeight: 600, marginLeft: '3px', textTransform: 'uppercase' }}>
                                    {opp.opportunity_nature || (isStagnation ? 'Projected Opportunity — Heuristic' : 'EST.')}
                                  </span>
                                </div>
                              ) : (
                                <span style={{ fontSize: '0.72rem', color: 'var(--ink-muted)', fontWeight: 600 }}>
                                  {isNoAction ? 'NO ACTION REQUIRED' : 'DIAGNOSTIC ONLY'}
                                </span>
                              )}
                              {evValue > 0 && (
                                <div style={{ fontSize: '0.68rem', color: 'var(--ink-muted)', fontFamily: 'var(--font-mono)' }}>
                                  EV: ₹{evValue.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Business Problem / Title */}
                          <div className="growth-opp-title">
                            {opp.business_problem || opp.title}
                          </div>

                          {/* Evidence Summary Chips — Explicit Signals */}
                          {opp.evidence && (
                            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', margin: '0.4rem 0 0.6rem' }}>
                              {opp.evidence.recommendation_offer_count != null && (
                                <span style={{ fontSize: '0.7rem', background: '#FEF3C7', color: '#92400E', padding: '2px 6px', borderRadius: '4px' }}>
                                  Recommendation Offers: {opp.evidence.recommendation_offer_count}
                                </span>
                              )}
                              {opp.evidence.cart_appearances_count != null && (
                                <span style={{ fontSize: '0.7rem', background: '#EFF6FF', color: '#1E40AF', padding: '2px 6px', borderRadius: '4px' }}>
                                  Cart Appearances: {opp.evidence.cart_appearances_count}
                                </span>
                              )}
                              {opp.evidence.orders_count != null && (
                                <span style={{ fontSize: '0.7rem', background: '#ECFDF5', color: '#065F46', padding: '2px 6px', borderRadius: '4px' }}>
                                  Orders: {opp.evidence.orders_count}
                                </span>
                              )}
                              {opp.evidence.actual_impressions_recorded && (
                                <span style={{ fontSize: '0.7rem', background: 'var(--bg-paper-tint)', border: '1px solid var(--hairline)', color: 'var(--ink-muted)', padding: '2px 6px', borderRadius: '4px' }}>
                                  Actual Impressions: Not recorded in V1
                                </span>
                              )}
                              {opp.evidence.matched_controls && (
                                <span style={{ fontSize: '0.7rem', background: '#F5F3FF', color: '#6D28D9', padding: '2px 6px', borderRadius: '4px' }}>
                                  Matched Controls: {opp.evidence.matched_controls.length} category peers
                                </span>
                              )}
                              {opp.evidence.cart_count && (
                                <span style={{ fontSize: '0.7rem', background: '#FEF3C7', color: '#92400E', padding: '2px 6px', borderRadius: '4px' }}>
                                  {opp.evidence.cart_count} abandoned carts
                                </span>
                              )}
                              {opp.evidence.top_cart_idle_hours != null && (
                                <span style={{ fontSize: '0.7rem', background: 'var(--bg-paper-tint)', border: '1px solid var(--hairline)', color: 'var(--ink-secondary)', padding: '2px 6px', borderRadius: '4px' }}>
                                  Idle: {opp.evidence.top_cart_idle_hours}h
                                </span>
                              )}
                              {opp.evidence.statistical_lift && (
                                <span style={{ fontSize: '0.7rem', background: '#ECFDF5', color: '#065F46', padding: '2px 6px', borderRadius: '4px' }}>
                                  {opp.evidence.statistical_lift}x Lift ({opp.evidence.co_occurrences} co-orders)
                                </span>
                              )}
                              {opp.evidence.stock_units != null && (
                                <span style={{ fontSize: '0.7rem', background: '#EFF6FF', color: '#1E40AF', padding: '2px 6px', borderRadius: '4px' }}>
                                  {opp.evidence.stock_units} units in stock
                                </span>
                              )}
                              {opp.evidence.days_of_inventory != null && (
                                <span style={{ fontSize: '0.7rem', background: opp.evidence.days_of_inventory > 60 ? '#FEF3C7' : '#ECFDF5', color: opp.evidence.days_of_inventory > 60 ? '#92400E' : '#065F46', padding: '2px 6px', borderRadius: '4px' }}>
                                  {opp.evidence.days_of_inventory}d coverage
                                </span>
                              )}
                              {opp.evidence.sales_velocity_daily != null && (
                                <span style={{ fontSize: '0.7rem', background: 'var(--bg-paper-tint)', border: '1px solid var(--hairline)', color: 'var(--ink-secondary)', padding: '2px 6px', borderRadius: '4px' }}>
                                  Velocity: {opp.evidence.sales_velocity_daily}/day
                                </span>
                              )}
                              {opp.evidence.buyer_relevance_score != null && (
                                <span style={{ fontSize: '0.7rem', background: '#F5F3FF', color: '#6D28D9', padding: '2px 6px', borderRadius: '4px' }}>
                                  Relevance: {Math.round(opp.evidence.buyer_relevance_score * 100)}%
                                </span>
                              )}
                            </div>
                          )}

                          {/* Confidence Row */}
                          <div className="growth-confidence-row">
                            <div className="growth-confidence-meta">
                              <span>Confidence: {confPct}%</span>
                              <span style={{ fontSize: '0.7rem', color: opp.is_empirical_confidence ? '#059669' : 'var(--ink-muted)' }}>
                                {opp.confidence_label || (opp.is_empirical_confidence ? 'Empirical Benchmark' : 'Heuristic Prior')}
                              </span>
                            </div>
                            <div className="growth-conf-bar-bg">
                              <div
                                className="growth-conf-bar-fill"
                                style={{
                                  width: `${confPct}%`,
                                  background: opp.confidence >= 0.7 ? '#059669' : opp.confidence >= 0.4 ? '#D97706' : '#6B7280'
                                }}
                              />
                            </div>
                          </div>

                          {/* Policy Check Status */}
                          {opp.policy_status && (
                            <div style={{ margin: '0.5rem 0', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.72rem', color: opp.policy_status.approved ? '#059669' : '#D97706' }}>
                              <Shield size={12} />
                              <span>{opp.policy_status.approved ? 'Policy Approved: ₹0 Action Cost · ₹0 Financial Exposure' : opp.policy_status.reason}</span>
                            </div>
                          )}

                          {/* Selected Action Box */}
                          <div className="growth-opp-action-box">
                            <div style={{ fontWeight: 600, color: 'var(--ink)', fontSize: '0.8rem', marginBottom: '2px' }}>
                              Recommended Action: {opp.selected_action?.title || opp.recommended_action}
                            </div>
                            {opp.selected_action?.description && (
                              <div style={{ fontSize: '0.75rem', color: 'var(--ink-secondary)', lineHeight: 1.35 }}>
                                {opp.selected_action.description}
                              </div>
                            )}
                          </div>

                          {/* Interactive "Why this action?" Accordion */}
                          {opp.why_this_action && (
                            <div style={{ marginTop: '0.6rem' }}>
                              <button
                                type="button"
                                onClick={() => toggleWhyAction(opp.opportunity_id)}
                                style={{
                                  background: 'none',
                                  border: 'none',
                                  padding: '2px 0',
                                  fontSize: '0.74rem',
                                  fontWeight: 600,
                                  color: '#059669',
                                  cursor: 'pointer',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '4px'
                                }}
                              >
                                <HelpCircle size={13} />
                                <span>Why this action? (Explainability & Safety)</span>
                                {isExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                              </button>

                              {isExpanded && (
                                <div style={{
                                  marginTop: '6px',
                                  padding: '10px 12px',
                                  background: 'var(--bg-paper-tint)',
                                  border: '1px solid var(--hairline)',
                                  borderRadius: '6px',
                                  fontSize: '0.74rem',
                                  lineHeight: 1.45,
                                  color: 'var(--ink)'
                                }}>
                                  <div style={{ marginBottom: '6px' }}>
                                    <strong style={{ color: 'var(--ink)' }}>Observed Evidence:</strong>
                                    <ul style={{ margin: '3px 0 0 16px', padding: 0 }}>
                                      {opp.why_this_action.evidence_summary?.map((ev, i) => (
                                        <li key={i} style={{ color: 'var(--ink-secondary)' }}>{ev}</li>
                                      ))}
                                    </ul>
                                  </div>

                                  {opp.evidence?.stage2_llm_decision && (
                                    <div style={{ marginBottom: '6px', padding: '6px 8px', background: opp.evidence.stage2_llm_decision === 'ACCEPT' ? '#ECFDF5' : '#FEF3C7', borderRadius: '4px' }}>
                                      <strong style={{ color: opp.evidence.stage2_llm_decision === 'ACCEPT' ? '#065F46' : '#92400E' }}>
                                        Stage 2 LLM Review ({opp.evidence.stage2_llm_decision}):
                                      </strong>
                                      <div style={{ color: 'var(--ink-secondary)', marginTop: '2px' }}>
                                        {opp.evidence.stage2_llm_reasoning}
                                      </div>
                                    </div>
                                  )}

                                  <div style={{ marginBottom: '6px' }}>
                                    <strong style={{ color: 'var(--ink)' }}>Expected Value Calculation:</strong>
                                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.71rem', color: '#059669', marginTop: '2px' }}>
                                      {opp.why_this_action.calculation_formula}
                                    </div>
                                  </div>

                                  <div style={{ marginBottom: '6px' }}>
                                    <strong style={{ color: 'var(--ink)' }}>Historical Baseline:</strong>
                                    <div style={{ color: 'var(--ink-secondary)', marginTop: '2px' }}>
                                      {opp.why_this_action.historical_baseline}
                                    </div>
                                  </div>

                                  <div style={{ marginBottom: '6px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                                    <div>
                                      <strong style={{ color: 'var(--ink)' }}>Action Cost:</strong>
                                      <div style={{ color: 'var(--ink-secondary)' }}>{opp.why_this_action.action_cost_explanation}</div>
                                    </div>
                                    <div>
                                      <strong style={{ color: 'var(--ink)' }}>Financial Exposure:</strong>
                                      <div style={{ color: 'var(--ink-secondary)' }}>{opp.why_this_action.financial_exposure_explanation}</div>
                                    </div>
                                  </div>

                                  <div style={{ borderTop: '1px solid var(--hairline)', paddingTop: '6px', marginTop: '6px' }}>
                                    <div style={{ color: '#065F46', marginBottom: '2px' }}>
                                      <strong>Will do:</strong> {opp.why_this_action.will_do}
                                    </div>
                                    <div style={{ color: '#991B1B' }}>
                                      <strong>Will NOT do:</strong> {opp.why_this_action.will_not_do}
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Card Actions */}
                        <div className="growth-opp-card-actions">
                          <button
                            type="button"
                            className="btn-growth-dismiss"
                            onClick={() => handleDismissGrowthAction(opp.opportunity_id)}
                          >
                            Dismiss
                          </button>

                          {opp.action_executable ? (
                            <button
                              type="button"
                              className="btn-growth-execute"
                              disabled={executingActionId === opp.opportunity_id}
                              onClick={() => handleExecuteGrowthAction(opp)}
                            >
                              {executingActionId === opp.opportunity_id ? (
                                <RefreshCw size={13} className="spin-anim" />
                              ) : (
                                <ArrowRight size={13} />
                              )}
                              <span>
                                {actionType === 'RECOVER_CART' ? 'Reissue Link' :
                                 isStagnation ? 'Start 14d Experiment' :
                                 actionType === 'CROSS_SELL' ? 'Prioritize Cross-Sell' :
                                 'Execute Action'}
                              </span>
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="btn-growth-dismiss"
                              style={{ borderColor: 'var(--hairline)', color: 'var(--ink-muted)', cursor: 'default' }}
                              disabled
                            >
                              {isNoAction ? 'No Action Needed' : 'Diagnostic Review'}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Payment Safety & Guardrail Guarantee */}
              <div className="console-card" style={{ marginTop: '1.5rem', background: 'var(--bg-paper-tint)', padding: '1rem 1.25rem', border: '1px solid var(--hairline)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <Shield size={18} color="#059669" />
                  <div>
                    <strong style={{ fontSize: '0.82rem', color: 'var(--ink)' }}>Non-Monetary Preparatory Safety Guarantee: </strong>
                    <span style={{ fontSize: '0.78rem', color: 'var(--ink-secondary)' }}>
                      All actions are strictly non-monetary (reissuing payment links, boosting discoverability, prioritizing recommendations). Customer authorization is strictly required for checkout transactions.
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  className="btn-link"
                  onClick={() => setActiveTab('policy')}
                  style={{ fontSize: '0.78rem', fontWeight: 600, color: '#059669', background: 'none', border: 'none', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                >
                  <span>Policy Settings</span>
                  <ArrowRight size={12} />
                </button>
              </div>
            </div>
          )}

          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* ── SUB-VIEW 2: CONTROLLED PROMOTION EXPERIMENTS (DiD) ── */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {managerView === 'experiments' && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', flexWrap: 'wrap', gap: '8px' }}>
                <div>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--ink)', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Activity size={17} color="#2563EB" />
                    <span>Controlled Promotion Experiments (Difference-in-Differences)</span>
                  </h3>
                  <p style={{ fontSize: '0.78rem', color: 'var(--ink-secondary)', marginTop: '2px' }}>
                    14-day horizon vs minimum 2 matched category controls · Day 4 Early-Kill enabled · Day 14 Decision Gate
                  </p>
                </div>

                <div style={{ fontSize: '0.75rem', padding: '4px 10px', background: '#EFF6FF', color: '#1E40AF', borderRadius: '4px', fontWeight: 600, border: '1px solid #BFDBFE' }}>
                  Capacity: {promoSystemState?.active_experiments_count || 0} / {promoSystemState?.max_active_experiments || 5} Active Experiments
                </div>
              </div>

              {promotionExperiments.length === 0 ? (
                <div className="console-card" style={{ padding: '2.5rem', textAlign: 'center', color: 'var(--ink-muted)' }}>
                  <Activity size={28} color="#2563EB" style={{ margin: '0 auto 0.75rem' }} />
                  <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--ink)', marginBottom: '0.35rem' }}>
                    No Promotion Experiments Launched Yet
                  </h4>
                  <p style={{ fontSize: '0.82rem', color: 'var(--ink-secondary)', maxWidth: '480px', margin: '0 auto 1rem' }}>
                    Launch an inventory experiment from the Opportunity Pipeline to begin 14-day Difference-in-Differences causal tracking against unboosted category controls.
                  </p>
                  <button
                    type="button"
                    className="btn-console-primary"
                    onClick={() => setManagerView('pipeline')}
                    style={{ fontSize: '0.78rem', margin: '0 auto' }}
                  >
                    <Zap size={13} />
                    <span>Go to Opportunity Pipeline</span>
                  </button>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {promotionExperiments.map((exp) => {
                    const isActive = exp.status === 'ACTIVE';
                    const isEarlyKilled = !!exp.early_killed;
                    const controls = Array.isArray(exp.control_skus)
                      ? exp.control_skus
                      : (typeof exp.control_skus === 'string' ? JSON.parse(exp.control_skus || '[]') : []);

                    const startDate = new Date(exp.started_at);
                    const now = new Date();
                    const elapsedDays = Math.max(1, Math.floor((now - startDate) / (1000 * 60 * 60 * 24)));
                    const isDay14Gate = exp.status === 'COMPLETED' && !isEarlyKilled && (exp.merchant_decision === 'PENDING' || !exp.merchant_decision);

                    return (
                      <div
                        key={exp.id}
                        className="console-card"
                        style={{
                          padding: '1.2rem',
                          border: isDay14Gate ? '2px solid #2563EB' : isActive ? '1px solid #A7F3D0' : '1px solid var(--hairline)',
                          background: isDay14Gate ? 'rgba(37, 99, 235, 0.02)' : isActive ? 'rgba(5, 150, 105, 0.02)' : 'var(--bg-paper)'
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '10px' }}>
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                              <span style={{
                                fontSize: '0.72rem',
                                fontWeight: 700,
                                padding: '2px 8px',
                                borderRadius: '4px',
                                background: isActive ? '#ECFDF5' : isEarlyKilled ? '#FEE2E2' : '#EFF6FF',
                                color: isActive ? '#065F46' : isEarlyKilled ? '#991B1B' : '#1E40AF',
                                textTransform: 'uppercase'
                              }}>
                                {isActive ? `Day ${elapsedDays} of 14 · ACTIVE` : isEarlyKilled ? 'EARLY KILLED (DAY 4)' : `COMPLETED · ${exp.outcome_status || 'FINISHED'}`}
                              </span>

                              {exp.opportunity_reason && (
                                <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--ink-secondary)', background: 'var(--bg-paper-tint)', padding: '2px 6px', borderRadius: '4px', border: '1px solid var(--hairline)' }}>
                                  {exp.opportunity_reason.replace(/_/g, ' ')}
                                </span>
                              )}

                              <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--ink-muted)' }}>
                                ID: {exp.id}
                              </span>
                            </div>

                            <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--ink)', margin: '0.4rem 0 0.2rem' }}>
                              {exp.sku} · Treatment vs {controls.length} Matched Controls
                            </h4>

                            <div style={{ fontSize: '0.78rem', color: 'var(--ink-secondary)' }}>
                              Controls: {controls.map(c => typeof c === 'object' ? `${c.name || c.sku} (${c.sku})` : c).join(', ')}
                            </div>
                          </div>

                          <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: '0.75rem', color: 'var(--ink-muted)' }}>
                              Liquidated Units: <strong>{exp.units_liquidated || 0}</strong> · Orders: <strong>{exp.orders_during_experiment || 0}</strong>
                            </div>
                            <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#059669', fontFamily: 'var(--font-mono)', marginTop: '2px' }}>
                              Realized Revenue: ₹{((exp.realized_revenue_paise || 0) / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </div>
                            {exp.matched_control_lift_estimate != null && (
                              <div style={{ fontSize: '0.74rem', color: '#2563EB', fontWeight: 600, marginTop: '2px' }}>
                                Matched-Control Lift Estimate: {exp.matched_control_lift_estimate > 0 ? `+${(exp.matched_control_lift_estimate * 100).toFixed(1)}%` : `${(exp.matched_control_lift_estimate * 100).toFixed(1)}%`}
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Early Kill Banner if Applicable */}
                        {isEarlyKilled && (
                          <div style={{ marginTop: '0.75rem', padding: '8px 10px', background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: '6px', fontSize: '0.76rem', color: '#991B1B' }}>
                            <strong>Early-Kill Triggered:</strong> {exp.early_kill_reason || 'Treatment failed to outperform active category controls by Day 4.'} Boost safely reverted to 1.0x.
                          </div>
                        )}

                        {/* Day 14 Decision Gate Buttons */}
                        {isDay14Gate && (
                          <div style={{ marginTop: '1rem', padding: '10px 12px', background: '#F8FAFC', border: '1px solid #CBD5E1', borderRadius: '6px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                              <div>
                                <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#1E293B' }}>
                                  Day-14 Decision Gate: Choose Final Strategy
                                </div>
                                <div style={{ fontSize: '0.74rem', color: 'var(--ink-secondary)' }}>
                                  Experiment finished. Select permanent standing boost, organic reversion, or future re-test.
                                </div>
                              </div>

                              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                                <button
                                  type="button"
                                  style={{
                                    padding: '6px 12px',
                                    fontSize: '0.75rem',
                                    fontWeight: 600,
                                    background: '#059669',
                                    color: '#FFF',
                                    border: 'none',
                                    borderRadius: '4px',
                                    cursor: 'pointer'
                                  }}
                                  disabled={isSubmittingDecision[exp.id]}
                                  onClick={() => handleExperimentDecision(exp.id, 'KEEP_STANDING_BOOST')}
                                >
                                  Keep as Standing Boost (1.35x)
                                </button>

                                <button
                                  type="button"
                                  style={{
                                    padding: '6px 12px',
                                    fontSize: '0.75rem',
                                    fontWeight: 600,
                                    background: '#475569',
                                    color: '#FFF',
                                    border: 'none',
                                    borderRadius: '4px',
                                    cursor: 'pointer'
                                  }}
                                  disabled={isSubmittingDecision[exp.id]}
                                  onClick={() => handleExperimentDecision(exp.id, 'REVERT_TO_ORGANIC')}
                                >
                                  Revert to Organic (1.0x)
                                </button>

                                <button
                                  type="button"
                                  style={{
                                    padding: '6px 12px',
                                    fontSize: '0.75rem',
                                    fontWeight: 600,
                                    background: 'transparent',
                                    color: '#2563EB',
                                    border: '1px solid #2563EB',
                                    borderRadius: '4px',
                                    cursor: 'pointer'
                                  }}
                                  disabled={isSubmittingDecision[exp.id]}
                                  onClick={() => handleExperimentDecision(exp.id, 'RE_RUN_LATER')}
                                >
                                  Re-run Later (7d Cooldown)
                                </button>
                              </div>
                            </div>
                          </div>
                        )}

                        {exp.merchant_decision && exp.merchant_decision !== 'PENDING' && (
                          <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--ink-muted)' }}>
                            Merchant Strategic Decision: <strong>{exp.merchant_decision.replace(/_/g, ' ')}</strong>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* ── SUB-VIEW 3: OBSERVATIONAL LEGACY BOOST REMEDIATION QUEUE ── */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {managerView === 'legacy' && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '8px' }}>
                <div>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--ink)', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Shield size={16} color="#D97706" />
                    <span>Observational Legacy Boost Remediation Queue</span>
                  </h3>
                  <p style={{ fontSize: '0.78rem', color: 'var(--ink-secondary)', marginTop: '2px' }}>
                    Benchmarked against category median velocities · Non-causal audit queue
                  </p>
                </div>

                <span style={{ fontSize: '0.74rem', color: '#D97706', background: '#FEF3C7', border: '1px solid #FCD34D', padding: '3px 9px', borderRadius: '4px', fontWeight: 600 }}>
                  Legacy boost assessment — observational, not experimental.
                </span>
              </div>

              {/* Filter Toolbar & Helper Note */}
              <div style={{ background: '#FFFBEB', border: '1px solid #FDE68A', padding: '0.6rem 0.9rem', borderRadius: '6px', fontSize: '0.76rem', color: '#92400E', marginBottom: '0.85rem', lineHeight: 1.4 }}>
                <strong>How this works:</strong> The filter tabs below sort products by the <strong>AI's diagnostic analysis</strong>. On each product row, you have full control to choose any of the 3 actions: 
                <span style={{ color: '#065F46', fontWeight: 600 }}> Keep</span> (leave 1.35x boost permanently), 
                <span style={{ color: '#991B1B', fontWeight: 600 }}> Retire</span> (turn off boost back to organic 1.0x), or 
                <span style={{ color: '#1E40AF', fontWeight: 600 }}> Experiment</span> (launch a 14-day controlled test vs category peers).
              </div>

              <div className="console-toolbar" style={{ marginBottom: '1rem' }}>
                <div className="toolbar-search-wrap" style={{ flex: 1 }}>
                  <Search size={14} color="var(--ink-muted)" />
                  <input
                    type="text"
                    placeholder="Search legacy products by name, SKU, or category…"
                    value={legacySearch}
                    onChange={(e) => { setLegacySearch(e.target.value); setLegacyPage(1); }}
                  />
                </div>

                <div className="toolbar-controls-right">
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {[
                      { id: 'ALL', label: `All Products (${legacyAssessments.length})` },
                      { id: 'KEEP', label: `AI Suggests Keep (${legacyAssessments.filter(l => l.suggested_action === 'KEEP').length})` },
                      { id: 'RETIRE', label: `AI Suggests Retire (${legacyAssessments.filter(l => l.suggested_action === 'RETIRE').length})` },
                      { id: 'CONVERT_TO_EXPERIMENT', label: `AI Suggests Experiment (${legacyAssessments.filter(l => l.suggested_action === 'CONVERT_TO_EXPERIMENT').length})` }
                    ].map(btn => (
                      <button
                        key={btn.id}
                        type="button"
                        className={`filter-chip ${legacyFilter === btn.id ? 'active' : ''}`}
                        onClick={() => { setLegacyFilter(btn.id); setLegacyPage(1); }}
                        style={{ fontSize: '0.74rem', padding: '4px 9px' }}
                      >
                        {btn.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {legacyAssessments.length === 0 ? (
                <div className="console-card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--ink-muted)', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={24} color="#059669" style={{ margin: '0 auto 0.5rem' }} />
                  No unmanaged legacy boosts in the catalog. All boosted items are managed via controlled promotion experiments.
                </div>
              ) : (
                <div className="console-table-card">
                  <div className="console-scroll-box" style={{ maxHeight: '480px' }}>
                    <table className="console-table">
                      <thead>
                        <tr>
                          <th>Product / SKU</th>
                          <th>Category</th>
                          <th>Stock</th>
                          <th>Obs. Velocity vs Median</th>
                          <th>AI Suggested Action & Rationale</th>
                          <th style={{ textAlign: 'right' }}>Your Merchant Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {paginatedLegacyAssessments.length === 0 ? (
                          <tr>
                            <td colSpan="6" className="table-empty-cell">
                              No legacy boosts match the current filter.
                            </td>
                          </tr>
                        ) : (
                          paginatedLegacyAssessments.map((leg) => {
                            const isSuggestedKeep = leg.suggested_action === 'KEEP';
                            const isSuggestedRetire = leg.suggested_action === 'RETIRE';
                            const isSuggestedExp = leg.suggested_action === 'CONVERT_TO_EXPERIMENT';

                            return (
                              <tr key={leg.sku}>
                                <td>
                                  <strong>{leg.name}</strong>
                                  <div style={{ fontSize: '0.7rem', color: 'var(--ink-muted)' }}>{leg.sku} · ₹{leg.price_rupees}</div>
                                </td>
                                <td>{leg.category}</td>
                                <td>{leg.stock} units</td>
                                <td>
                                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{leg.velocity_daily}/day</span>
                                  <span style={{ fontSize: '0.7rem', color: 'var(--ink-muted)', marginLeft: '4px' }}>
                                    (Median: {leg.category_median_velocity}/day)
                                  </span>
                                </td>
                                <td>
                                  <span style={{
                                    fontSize: '0.72rem',
                                    fontWeight: 700,
                                    padding: '2px 6px',
                                    borderRadius: '4px',
                                    background: isSuggestedKeep ? '#ECFDF5' : isSuggestedRetire ? '#FEF2F2' : '#EFF6FF',
                                    color: isSuggestedKeep ? '#065F46' : isSuggestedRetire ? '#991B1B' : '#1E40AF'
                                  }}>
                                    {leg.suggested_action.replace(/_/g, ' ')}
                                  </span>
                                  <div style={{ fontSize: '0.72rem', color: 'var(--ink-secondary)', marginTop: '2px' }}>{leg.reason}</div>
                                </td>
                                <td style={{ textAlign: 'right' }}>
                                  <div style={{ display: 'inline-flex', gap: '4px' }}>
                                    <button
                                      type="button"
                                      style={{
                                        padding: '4px 8px',
                                        fontSize: '0.72rem',
                                        fontWeight: isSuggestedKeep ? 700 : 500,
                                        borderRadius: '4px',
                                        border: isSuggestedKeep ? '2px solid #059669' : '1px solid #10B981',
                                        background: isSuggestedKeep ? '#ECFDF5' : 'transparent',
                                        color: '#047857',
                                        cursor: 'pointer'
                                      }}
                                      disabled={isReconcilingSku[leg.sku]}
                                      onClick={() => handleReconcileLegacyBoost(leg.sku, 'keep')}
                                      title="Keep 1.35x boost permanently on this product"
                                    >
                                      {isReconcilingSku[leg.sku] ? '…' : 'Keep'}
                                    </button>
                                    <button
                                      type="button"
                                      style={{
                                        padding: '4px 8px',
                                        fontSize: '0.72rem',
                                        fontWeight: isSuggestedRetire ? 700 : 500,
                                        borderRadius: '4px',
                                        border: isSuggestedRetire ? '2px solid #DC2626' : '1px solid #EF4444',
                                        background: isSuggestedRetire ? '#FEF2F2' : 'transparent',
                                        color: '#B91C1C',
                                        cursor: 'pointer'
                                      }}
                                      disabled={isReconcilingSku[leg.sku]}
                                      onClick={() => handleReconcileLegacyBoost(leg.sku, 'retire')}
                                      title="Remove 1.35x boost and revert product to organic 1.0x"
                                    >
                                      {isReconcilingSku[leg.sku] ? '…' : 'Retire'}
                                    </button>
                                    <button
                                      type="button"
                                      style={{
                                        padding: '4px 8px',
                                        fontSize: '0.72rem',
                                        fontWeight: isSuggestedExp ? 700 : 500,
                                        borderRadius: '4px',
                                        border: isSuggestedExp ? '2px solid #2563EB' : '1px solid #3B82F6',
                                        background: isSuggestedExp ? '#EFF6FF' : 'transparent',
                                        color: '#1D4ED8',
                                        cursor: 'pointer'
                                      }}
                                      disabled={isReconcilingSku[leg.sku]}
                                      onClick={() => handleReconcileLegacyBoost(leg.sku, 'convert_to_experiment')}
                                      title="Launch 14-day controlled Difference-in-Differences experiment vs category peers"
                                    >
                                      {isReconcilingSku[leg.sku] ? '…' : 'Experiment'}
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>

                  {/* Pagination Bar */}
                  <div className="console-pagination">
                    <span>
                      Showing {Math.min(filteredLegacyAssessments.length, (legacyPage - 1) * LEGACY_PAGE_SIZE + 1)}–{Math.min(filteredLegacyAssessments.length, legacyPage * LEGACY_PAGE_SIZE)} of {filteredLegacyAssessments.length} legacy SKUs
                    </span>
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <button
                        type="button"
                        className="console-page-btn"
                        disabled={legacyPage <= 1}
                        onClick={() => setLegacyPage(prev => Math.max(1, prev - 1))}
                      >
                        <ChevronLeft size={13} />
                        <span>Prev</span>
                      </button>
                      <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)' }}>
                        Page {legacyPage} of {totalLegacyPages}
                      </span>
                      <button
                        type="button"
                        className="console-page-btn"
                        disabled={legacyPage >= totalLegacyPages}
                        onClick={() => setLegacyPage(prev => Math.min(totalLegacyPages, prev + 1))}
                      >
                        <span>Next</span>
                        <ChevronRight size={13} />
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* ── SUB-VIEW 4: AGENT PERFORMANCE & CAPABILITY LEDGER ── */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {managerView === 'ledger' && (
            <div>
              {growthLearning && (
                <div className="growth-learning-card" style={{ marginTop: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '0.75rem' }}>
                    <div>
                      <h3 style={{ fontFamily: 'var(--font-serif)', fontSize: '1.15rem', fontWeight: 600, color: 'var(--ink)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Activity size={18} color="#059669" />
                        <span>Agent Performance & Capability Ledger</span>
                      </h3>
                      <p style={{ fontSize: '0.82rem', color: 'var(--ink-secondary)', marginTop: '2px' }}>
                        Empirical capability ledger distinguishing preparation vs exposure vs buyer acceptance vs realized revenue.
                      </p>
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.74rem', padding: '4px 10px', background: 'var(--bg-paper-tint)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--hairline)' }}>
                      Spend Ceiling: ₹{(growthLearning.spend_cap_rupees || 10000).toLocaleString('en-IN')} · Autonomy Threshold: ₹{(growthLearning.autonomy_threshold_rupees || 2500).toLocaleString('en-IN')}
                    </div>
                  </div>

                  <div className="console-table-scroll">
                    <table className="console-table">
                      <thead>
                        <tr>
                          <th>Growth Capability</th>
                          <th>Opportunities Detected</th>
                          <th>Offers / Interventions</th>
                          <th>Accepted / Recovered</th>
                          <th>Conversion Rate</th>
                          <th>Realized Incremental Lift</th>
                          <th>Model Calibration Baseline</th>
                        </tr>
                      </thead>
                      <tbody>
                        {/* Capability 1: Cross-Sell */}
                        <tr>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
                              <span className="growth-action-badge cross_sell">CROSS_SELL</span>
                              <span>Pre-Checkout Recommendations</span>
                            </div>
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>
                            {growthLearning.capabilities?.CROSS_SELL?.opportunities_detected || 0}
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>
                            {growthLearning.capabilities?.CROSS_SELL?.total_offers || 0}
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)', color: '#059669', fontWeight: 700 }}>
                            {growthLearning.capabilities?.CROSS_SELL?.accepted || 0}
                          </td>
                          <td>
                            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#059669' }}>
                              {Math.round((growthLearning.capabilities?.CROSS_SELL?.acceptance_rate || 0) * 100)}%
                            </span>
                          </td>
                          <td>
                            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#059669' }}>
                              ₹{(growthLearning.capabilities?.CROSS_SELL?.realized_incremental_rupees || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </span>
                          </td>
                          <td style={{ fontSize: '0.78rem', color: 'var(--ink-muted)' }}>
                            {growthLearning.capabilities?.CROSS_SELL?.model_source}
                          </td>
                        </tr>

                        {/* Capability 2: Recovery */}
                        <tr>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
                              <span className="growth-action-badge recover">RECOVER_CART</span>
                              <span>Abandoned Cart Link Recovery</span>
                            </div>
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>
                            {growthLearning.capabilities?.RECOVER_CART?.opportunities_detected || 0}
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>
                            {growthLearning.capabilities?.RECOVER_CART?.total_attempts || 0}
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)', color: '#059669', fontWeight: 700 }}>
                            {growthLearning.capabilities?.RECOVER_CART?.recovered || 0}
                          </td>
                          <td>
                            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#059669' }}>
                              {growthLearning.capabilities?.RECOVER_CART?.recovery_rate != null ? `${Math.round(growthLearning.capabilities.RECOVER_CART.recovery_rate * 100)}%` : 'Baseline (38%)'}
                            </span>
                          </td>
                          <td>
                            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#059669' }}>
                              ₹{(growthLearning.capabilities?.RECOVER_CART?.realized_incremental_rupees || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </span>
                            <div style={{ fontSize: '0.65rem', color: 'var(--ink-muted)' }}>
                              (60% of ₹{(growthLearning.capabilities?.RECOVER_CART?.gross_recovered_rupees || 0).toLocaleString('en-IN')})
                            </div>
                          </td>
                          <td style={{ fontSize: '0.78rem', color: 'var(--ink-muted)' }}>
                            {growthLearning.capabilities?.RECOVER_CART?.model_source}
                          </td>
                        </tr>

                        {/* Capability 3: Search Boost */}
                        <tr>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
                              <span className="growth-action-badge promote">PROMOTE_PRODUCT</span>
                              <span>Inventory Velocity 1.35x Search Boost</span>
                            </div>
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>
                            {growthLearning.capabilities?.PROMOTE_PRODUCT?.opportunities_detected || 0}
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>
                            {growthLearning.capabilities?.PROMOTE_PRODUCT?.boosted_skus_count || 0} SKUs
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-secondary)' }}>
                            Active Boost
                          </td>
                          <td>
                            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#2563EB' }}>
                              1.35x Multiplier
                            </span>
                          </td>
                          <td>
                            <span style={{ fontSize: '0.78rem', color: 'var(--ink-muted)' }}>
                              Observed post-boost settlements
                            </span>
                          </td>
                          <td style={{ fontSize: '0.78rem', color: 'var(--ink-muted)' }}>
                            {growthLearning.capabilities?.PROMOTE_PRODUCT?.model_source}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* ── SUB-VIEW 5: STORE ACTIVITY STREAM ── */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {managerView === 'timeline' && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '8px' }}>
                <div>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--ink)', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <History size={16} color="#059669" />
                    <span>Agent Activity Stream (Real Store Events)</span>
                  </h3>
                  <p style={{ fontSize: '0.78rem', color: 'var(--ink-secondary)', marginTop: '2px' }}>
                    Audited chronological activity stream across all store transactions and agent cycles
                  </p>
                </div>

                <span style={{ fontSize: '0.74rem', color: 'var(--ink-muted)', fontFamily: 'var(--font-mono)' }}>
                  Total Events Recorded: {growthTimeline.length}
                </span>
              </div>

              {/* Timeline Toolbar */}
              <div className="console-toolbar" style={{ marginBottom: '1rem' }}>
                <div className="toolbar-search-wrap" style={{ flex: 1 }}>
                  <Search size={14} color="var(--ink-muted)" />
                  <input
                    type="text"
                    placeholder="Search event detail, reference ID, or event type…"
                    value={timelineSearch}
                    onChange={(e) => setTimelineSearch(e.target.value)}
                  />
                </div>

                <div className="toolbar-controls-right">
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {[
                      { id: 'ALL', label: `All (${growthTimeline.length})` },
                      { id: 'RECOVER', label: 'Recovery' },
                      { id: 'PROMOTE', label: 'Promote' },
                      { id: 'CROSS_SELL', label: 'Cross-Sell' },
                      { id: 'POLICY', label: 'Policy' }
                    ].map(tab => (
                      <button
                        key={tab.id}
                        type="button"
                        className={`filter-chip ${timelineFilter === tab.id ? 'active' : ''}`}
                        onClick={() => setTimelineFilter(tab.id)}
                        style={{ fontSize: '0.74rem', padding: '4px 8px' }}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="console-card" style={{ padding: '0.75rem 1rem' }}>
                <div className="console-scroll-box" style={{ maxHeight: '520px' }}>
                  {filteredTimeline.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--ink-muted)', fontSize: '0.85rem' }}>
                      No activity stream events match the filter.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {filteredTimeline.slice(0, timelineVisibleCount).map((evt, idx) => {
                        const isOutcome = evt.event_type === 'revenue_outcome';
                        const isAction = evt.event_type === 'action_executed';
                        const isPolicy = evt.event_type === 'policy_check';

                        return (
                          <div
                            key={evt.id || idx}
                            style={{
                              display: 'flex',
                              alignItems: 'flex-start',
                              gap: '12px',
                              padding: '8px 12px',
                              borderRadius: '6px',
                              background: isOutcome ? '#ECFDF5' : isAction ? 'var(--bg-paper-tint)' : '#FFF',
                              border: isOutcome ? '1px solid #A7F3D0' : '1px solid var(--hairline)'
                            }}
                          >
                            <div style={{ marginTop: '2px' }}>
                              {isOutcome ? (
                                <CheckCircle2 size={16} color="#059669" />
                              ) : isAction ? (
                                <Zap size={16} color="#2563EB" />
                              ) : isPolicy ? (
                                <Shield size={16} color="#D97706" />
                              ) : (
                                <Clock size={16} color="var(--ink-muted)" />
                              )}
                            </div>

                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                                <strong style={{ fontSize: '0.82rem', color: isOutcome ? '#065F46' : 'var(--ink)' }}>
                                  {evt.title}
                                </strong>
                                <span style={{ fontSize: '0.7rem', color: 'var(--ink-muted)', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
                                  {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
                                </span>
                              </div>
                              <div style={{ fontSize: '0.76rem', color: 'var(--ink-secondary)', marginTop: '2px', lineHeight: 1.35 }}>
                                {evt.detail}
                              </div>
                            </div>

                            {evt.mode && (
                              <span style={{ fontSize: '0.65rem', padding: '2px 6px', borderRadius: '4px', textTransform: 'uppercase', fontWeight: 600, background: evt.mode === 'autonomous' ? '#ECFDF5' : 'var(--bg-paper-tint)', color: evt.mode === 'autonomous' ? '#065F46' : 'var(--ink-muted)' }}>
                                {evt.mode}
                              </span>
                            )}
                          </div>
                        );
                      })}

                      {filteredTimeline.length > timelineVisibleCount && (
                        <div style={{ paddingTop: '8px', textAlign: 'center' }}>
                          <button
                            type="button"
                            className="btn-load-more"
                            onClick={() => setTimelineVisibleCount(prev => prev + 50)}
                            style={{ margin: '0 auto' }}
                          >
                            <ChevronDown size={14} />
                            <span>Load More Events (Showing {timelineVisibleCount} of {filteredTimeline.length})</span>
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

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

              <KpiTooltip
                title="Total Catalog SKUs"
                category="Catalog Inventory"
                description="Total unique product units registered in the active store catalog and available for vector search."
                formula="COUNT(DISTINCT sku FROM catalog)"
                source="catalog table"
                align="left"
              />
            </div>
            <div className="console-kpi-card">
              <div className="kpi-label">Active Promoted Items</div>
              <div className="kpi-value">
                {catalogSummary.boosted_items}
              </div>
              <div className="kpi-sub">1.35x rank uplift applied</div>

              <KpiTooltip
                title="Active Promoted Items"
                category="Search Boost Multiplier"
                description="Products receiving a 1.35x rank multiplier in buyer semantic discovery and recommendation scoring."
                formula="1.35 × CosineSimilarity(query, sku)"
                source="catalog.boosted = 1"
              />
            </div>
            <div className="console-kpi-card">
              <div className="kpi-label">Out of Stock SKUs</div>
              <div className="kpi-value">
                {catalogSummary.out_of_stock_items}
              </div>
              <div className="kpi-sub">Triggers Substitution Agent</div>

              <KpiTooltip
                title="Out of Stock SKUs"
                category="Inventory Availability"
                description="Catalog products with zero stock that autonomously trigger semantic alternative proposals."
                formula="COUNT(sku FROM catalog WHERE stock = 0)"
                source="catalog.stock = 0"
              />
            </div>
            <div className="console-kpi-card">
              <div className="kpi-label">Distinct Categories</div>
              <div className="kpi-value">
                {catalogSummary.categories_count}
              </div>
              <div className="kpi-sub">Governed by policy whitelist</div>

              <KpiTooltip
                title="Distinct Categories"
                category="Taxonomy Governance"
                description="Unique product categories validated against the merchant category policy whitelist."
                formula="COUNT(DISTINCT category FROM catalog)"
                source="catalog • policy_config"
                align="right"
              />
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

            {(catalogTotal > 50 || catalogHasMore) && (
              <div className="table-load-more-bar">
                <span>
                  Showing <strong>{catalogItems.length}</strong> of <strong>{catalogTotal}</strong> products (50 items per network batch)
                </span>
                {catalogHasMore ? (
                  <button
                    type="button"
                    className="btn-load-more"
                    onClick={handleLoadMoreCatalog}
                    disabled={isLoadingMoreCatalog}
                  >
                    {isLoadingMoreCatalog ? (
                      <>
                        <RefreshCw size={13} className="animate-spin" />
                        <span>Fetching next 50 rows from database…</span>
                      </>
                    ) : (
                      <>
                        <ChevronDown size={14} />
                        <span>Fetch Next 50 Products from DB</span>
                      </>
                    )}
                  </button>
                ) : (
                  <span style={{ fontSize: '0.74rem', color: 'var(--ink-muted)' }}>
                    ✓ All {catalogTotal} products loaded from database
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* ── TAB 3: Growth Rules Inspector & Live Recommendation Sandbox ── */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {activeTab === 'growth-rules' && (
        <div className="console-tab-content">
          {/* Top Performance KPI Metrics */}
          <div className="console-kpi-grid">
            <div className="console-kpi-card">
              <div className="kpi-label">Active Growth Rules</div>
              <div className="kpi-value">
                {rulesSummary.active_rules}
              </div>
              <div className="kpi-sub">
                {rulesSummary.verified_rules || 0} Data-Verified · {rulesSummary.category_compat_rules || 0} Category Graph (Live)
              </div>

              <KpiTooltip
                title="Active Growth Rules"
                category="Rule Pipeline"
                description="Total active cross-sell association rules currently powering Tier 1 and Tier 2 recommendations."
                formula="Data_Verified_Rules + Category_Compat_Graph_Rules"
                source="basket_pairs • category_compatibility"
                align="left"
              />
            </div>

            <div className="console-kpi-card">
              <div className="kpi-label">Total Customer Orders</div>
              <div className="kpi-value">{rulesSummary.total_orders || 0}</div>
              <div className="kpi-sub">Across customer shopping sessions</div>

              <KpiTooltip
                title="Total Customer Orders"
                category="Traffic Volume"
                description="Total shopping sessions that reached cart proposal or order settlement."
                formula="COUNT(DISTINCT intent_id FROM intent_mandates)"
                source="intent_mandates table"
              />
            </div>

            <div className="console-kpi-card">
              <div className="kpi-label">Upsell Attachment Rate</div>
              <div className="kpi-value">
                {rulesSummary.overall_conversion_pct}%
              </div>
              <div className="kpi-sub">{rulesSummary.total_accepted || 0} upsells picked across {rulesSummary.total_orders || 0} orders</div>

              <KpiTooltip
                title="Upsell Attachment Rate"
                category="Conversion Efficiency"
                description="Percentage of recommended cross-sell products accepted by customers into their final carts."
                formula="(Accepted_Upsells / Total_Offered_Upsells) × 100%"
                source="upsell_events.accepted = 1"
              />
            </div>

            <div className="console-kpi-card">
              <div className="kpi-label">Attributable Revenue Lift</div>
              <div className="kpi-value">
                ₹{rulesSummary.total_revenue_lift_rupees.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
              </div>
              <div className="kpi-sub">Incremental revenue generated</div>

              <KpiTooltip
                title="Attributable Revenue Lift"
                category="Incremental GMV"
                description="Cumulative gross rupee lift added to customer baskets exclusively through accepted recommendations."
                formula="∑(cart_total_after_paise - cart_total_before_paise)"
                source="upsell_events.total_revenue_lift_paise"
                align="right"
              />
            </div>
          </div>

          {/* Sub-tab Navigation */}
          <div className="growth-subtabs-nav">
            <button
              type="button"
              className={`growth-subtab-btn ${growthSubTab === 'live_preview' ? 'active' : ''}`}
              onClick={() => setGrowthSubTab('live_preview')}
            >
              <Sparkles size={14} />
              <span>Live Recommendation Preview (Sandbox)</span>
            </button>
            <button
              type="button"
              className={`growth-subtab-btn ${growthSubTab === 'verified' ? 'active' : ''}`}
              onClick={() => { setGrowthSubTab('verified'); setRuleStatusFilter('data_verified'); }}
            >
              <CheckCircle2 size={14} />
              <span>Data-Verified Association Rules</span>
              <span className="growth-manager-nav-badge">{rulesSummary.verified_rules || 0}</span>
            </button>
            <button
              type="button"
              className={`growth-subtab-btn ${growthSubTab === 'retired' ? 'active' : ''}`}
              onClick={() => { setGrowthSubTab('retired'); setRuleStatusFilter('retired'); }}
            >
              <Archive size={14} />
              <span>Retired Legacy Priors</span>
              <span className="growth-manager-nav-badge">{rulesSummary.retired_priors || 0}</span>
            </button>
          </div>

          {/* ── SUB-TAB 1: Live Recommendation Preview Sandbox ─────────────── */}
          {growthSubTab === 'live_preview' && (
            <div className="live-sandbox-container">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div className="live-badge-glow">
                      <span className="live-pulse-dot" />
                      <span>COMPUTED LIVE ON DEMAND · ZERO DATABASE PERSISTENCE</span>
                    </div>
                  </div>
                  <p style={{ fontSize: '0.8rem', color: 'var(--ink-secondary)', marginTop: '0.35rem' }}>
                    Evaluates live catalog stock, category compatibility graph, and 384-d dense embeddings fresh on every call.
                  </p>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <button
                    type="button"
                    className="btn-console-outline"
                    onClick={() => handleFetchLivePreview(previewSku)}
                    disabled={isPreviewLoading}
                  >
                    {isPreviewLoading ? <RefreshCw size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                    <span>Re-evaluate Live</span>
                  </button>
                </div>
              </div>

              {/* Product Selector & Quick Presets */}
              <div style={{ marginTop: '1.25rem', padding: '1rem', background: 'var(--bg-paper-tint)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--hairline)' }}>
                <div style={{ fontSize: '0.78rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--ink-secondary)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
                  Select Trigger Product to Test Recommendations:
                </div>
                
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                  {[
                    { label: 'Party Glasses', sku: 'SUN-FAS-PAR-157' },
                    { label: 'Generic Motorcycle', sku: 'MOT-GEN-GEN-113' },
                    { label: 'Men Check Shirt', sku: 'MEN-FAS-CHE-086' },
                    { label: 'Calvin Klein CK One', sku: 'FRA-CAL-CKO-027' },
                    { label: 'American Football', sku: 'SPO-BRD-AME-137' },
                    { label: 'Puma Future Rider', sku: 'MEN-PUM-PUM-090' }
                  ].map((preset) => (
                    <button
                      key={preset.sku}
                      type="button"
                      className={`filter-chip ${previewSku === preset.sku ? 'active' : ''}`}
                      onClick={() => {
                        setPreviewSku(preset.sku);
                        handleFetchLivePreview(preset.sku);
                      }}
                      style={{ fontSize: '0.78rem' }}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>

                {/* Dropdown for entire catalog */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <select
                    className="console-select"
                    value={previewSku}
                    onChange={(e) => {
                      setPreviewSku(e.target.value);
                      handleFetchLivePreview(e.target.value);
                    }}
                    style={{ flex: 1, padding: '7px 10px', fontSize: '0.82rem' }}
                  >
                    {catalogItems.map((item) => (
                      <option key={item.sku} value={item.sku}>
                        {item.name} ({item.category}) — ₹{(item.price_paise / 100).toFixed(0)} [{item.sku}]
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Live Preview Output */}
              {isPreviewLoading ? (
                <div style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--ink-muted)' }}>
                  <RefreshCw size={24} className="animate-spin" style={{ margin: '0 auto 0.75rem auto' }} />
                  <p>Running live category graph scoping & dense embedding ranking…</p>
                </div>
              ) : previewData ? (
                <div style={{ marginTop: '1.25rem' }}>
                  {/* Trigger Item Banner */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '0.75rem 1rem', background: '#FFF', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-sm)' }}>
                    {previewData.trigger_image && (
                      <img src={previewData.trigger_image} alt="" style={{ width: 44, height: 44, objectFit: 'cover', borderRadius: 'var(--radius-xs)', border: '1px solid var(--hairline)' }} />
                    )}
                    <div>
                      <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--ink)' }}>
                        Trigger Cart Product: {previewData.trigger_name}
                      </div>
                      <div style={{ display: 'flex', gap: '8px', fontSize: '0.75rem', color: 'var(--ink-secondary)', marginTop: '2px' }}>
                        <span className="category-micro-tag">{previewData.trigger_category}</span>
                        <span>₹{previewData.trigger_price_rupees}</span>
                        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-muted)' }}>{previewData.trigger_sku}</span>
                      </div>
                    </div>
                  </div>

                  {/* Graph Reasoning Path Box */}
                  <div className="graph-path-box">
                    <div className="graph-path-title">
                      <Layers size={13} color="var(--accent-teal)" />
                      <span>Category Compatibility Graph Reasoning Path: '{previewData.trigger_category}' ({previewData.compatible_categories.length} Compatible Categories)</span>
                    </div>
                    <div className="graph-path-chips">
                      {previewData.compatible_categories.length === 0 ? (
                        <span style={{ fontSize: '0.78rem', color: 'var(--ink-muted)' }}>No category compatibility rules found for {previewData.trigger_category}.</span>
                      ) : (
                        previewData.compatible_categories.map((c, i) => (
                          <div key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: '#FFF', border: '1px solid var(--hairline)', padding: '5px 10px', borderRadius: 'var(--radius-xs)', fontSize: '0.75rem' }}>
                            <span style={{ fontWeight: 700, color: 'var(--ink)' }}>{c.compatible_category}</span>
                            <ArrowRight size={11} color="var(--ink-muted)" />
                            <span style={{ color: 'var(--ink-secondary)', fontSize: '0.72rem' }}>{c.reasoning}</span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Live-Matched Candidates Grid */}
                  <div style={{ marginTop: '1.25rem' }}>
                    <div style={{ fontSize: '0.78rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--ink-secondary)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
                      Top Live-Ranked Cross-Sell Recommendations ({previewData.candidates.length}):
                    </div>

                    {previewData.candidates.length === 0 ? (
                      <div className="table-empty-cell" style={{ background: '#FFF', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-sm)' }}>
                        No in-stock compatible items found in the catalog.
                      </div>
                    ) : (
                      <div className="live-candidates-grid">
                        {previewData.candidates.map((cand, idx) => (
                          <div key={cand.sku} className="live-candidate-card">
                            <div className="candidate-img-row">
                              {cand.image_url ? (
                                <img src={cand.image_url} alt="" className="candidate-img-thumb" />
                              ) : (
                                <div className="candidate-img-thumb" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                  <Package size={20} color="var(--ink-muted)" />
                                </div>
                              )}
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={cand.name}>
                                  #{idx + 1} {cand.name}
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
                                  <span className="category-micro-tag" style={{ fontSize: '0.68rem' }}>{cand.category}</span>
                                  <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--ink)' }}>₹{(cand.price_paise / 100).toFixed(0)}</span>
                                </div>
                              </div>
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                              <span className="source-tag-catmatch" style={{ fontSize: '0.68rem' }}>
                                <Layers size={10} style={{ display: 'inline', marginRight: 2 }} />
                                Live Category Match
                              </span>
                              {cand.cosine_similarity !== undefined && (
                                <span className="stat-badge support" style={{ fontSize: '0.66rem', padding: '1px 5px' }}>
                                  Sim: {(cand.cosine_similarity * 100).toFixed(0)}%
                                </span>
                              )}
                              {cand.boosted && (
                                <span className="boost-badge" style={{ fontSize: '0.66rem', padding: '1px 5px' }}>
                                  <Sparkles size={9} /> Partner Boosted
                                </span>
                              )}
                            </div>

                            <div style={{ fontSize: '0.76rem', color: 'var(--ink-secondary)', lineHeight: 1.35, background: 'var(--bg-paper-tint)', padding: '6px 8px', borderRadius: 'var(--radius-xs)', border: '1px solid var(--hairline)' }}>
                              "{cand.reason}"
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          )}

          {/* ── SUB-TAB 2: Data-Verified Association Rules ─────────────────── */}
          {growthSubTab === 'verified' && (
            <div>
              {growthRules.length === 0 ? (
                <div style={{ padding: '2rem', background: 'var(--bg-card)', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-md)', textAlign: 'center', marginBottom: '1.5rem' }}>
                  <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 44, height: 44, borderRadius: '50%', background: '#F0FDF4', color: '#16A34A', marginBottom: '0.75rem' }}>
                    <CheckCircle2 size={24} />
                  </div>
                  <h4 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--ink)', marginBottom: '0.35rem' }}>
                    Empirical Verification Gating Active (≥ 8 Co-occurrences &amp; Lift &gt; 1.2 Needed)
                  </h4>
                  <p style={{ fontSize: '0.85rem', color: 'var(--ink-secondary)', maxWidth: '580px', margin: '0 auto', lineHeight: 1.45 }}>
                    Data-verified association rules require at least 8 co-occurrences and Lift &gt; 1.2. Currently 0 pairs have crossed this threshold. Cold-start cross-sell recommendations are handled live by the Category Compatibility Graph and semantic embeddings.
                  </p>
                </div>
              ) : (
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
                        {growthRules.map((rule) => {
                          const isMuted = rule.muted;
                          return (
                            <tr key={rule.rule_id} className={isMuted ? 'muted-rule-row' : ''}>
                              <td>
                                <div className="rule-pair-visual">
                                  <div className="rule-item-box">
                                    <div className="rule-item-name">{rule.trigger_name}</div>
                                    <div className="rule-item-meta">
                                      <span className="category-micro-tag">{rule.trigger_category}</span>
                                      <span>₹{rule.trigger_price_rupees}</span>
                                    </div>
                                  </div>
                                  <ArrowRight size={14} className="rule-arrow-icon" />
                                  <div className="rule-item-box target">
                                    <div className="rule-item-name">{rule.target_name}</div>
                                    <div className="rule-item-meta">
                                      <span className="category-micro-tag">{rule.target_category}</span>
                                      <span>₹{rule.target_price_rupees}</span>
                                    </div>
                                  </div>
                                </div>
                              </td>
                              <td>
                                <div className="source-tag-verified">
                                  <CheckCircle2 size={12} />
                                  <span>Data-Verified Rule</span>
                                </div>
                                <div className="rule-stat-badges" style={{ marginTop: '0.35rem' }}>
                                  <span className="stat-badge lift">{rule.lift?.toFixed(2)}x Lift</span>
                                  <span className="stat-badge support">{rule.co_occurrence_count} orders ({(rule.support * 100).toFixed(1)}% Sup)</span>
                                </div>
                              </td>
                              <td>
                                <span className="llm-reasoning-quote">"{rule.plain_language}"</span>
                              </td>
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
                                    <strong>{rule.conversion_rate_pct}%</strong>
                                  </div>
                                </div>
                              </td>
                              <td style={{ textAlign: 'right' }}>
                                <button
                                  type="button"
                                  className={isMuted ? 'btn-rule-unmute' : 'btn-rule-mute'}
                                  onClick={() => handleToggleMuteRule(rule)}
                                  disabled={mutingRuleId === rule.rule_id}
                                >
                                  {isMuted ? <Volume2 size={13} /> : <VolumeX size={13} />}
                                  <span>{isMuted ? 'Unmute' : 'Mute'}</span>
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  {(rulesTotal > 50 || rulesHasMore) && (
                    <div className="table-load-more-bar">
                      <span>
                        Showing <strong>{growthRules.length}</strong> of <strong>{rulesTotal}</strong> rules (50 items per network batch)
                      </span>
                      {rulesHasMore ? (
                        <button
                          type="button"
                          className="btn-load-more"
                          onClick={handleLoadMoreRules}
                          disabled={isLoadingMoreRules}
                        >
                          {isLoadingMoreRules ? (
                            <>
                              <RefreshCw size={13} className="animate-spin" />
                              <span>Fetching next 50 rules from database…</span>
                            </>
                          ) : (
                            <>
                              <ChevronDown size={14} />
                              <span>Fetch Next 50 Rules from DB</span>
                            </>
                          )}
                        </button>
                      ) : (
                        <span style={{ fontSize: '0.74rem', color: 'var(--ink-muted)' }}>
                          ✓ All {rulesTotal} rules loaded from database
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── SUB-TAB 3: Retired Legacy Priors Archive ───────────────────── */}
          {growthSubTab === 'retired' && (
            <div>
              <div style={{ padding: '1rem 1.25rem', background: '#F9FAFB', border: '1px solid #E5E7EB', borderRadius: 'var(--radius-sm)', marginBottom: '1.25rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 700, fontSize: '0.85rem', color: '#4B5563' }}>
                  <Archive size={15} />
                  <span>Retired Legacy Per-SKU Priors ({rulesSummary.retired_priors || 0} rows)</span>
                </div>
                <p style={{ fontSize: '0.78rem', color: '#6B7280', marginTop: '0.25rem', lineHeight: 1.4 }}>
                  These static pair rows were retired to eliminate the combinatorial-enumeration problem and prevent catalog staleness. All rows have <code>retired = 1</code> and are completely excluded from live buyer recommendation queries. Preserved for audit & historical reference.
                </p>
              </div>

              <div className="console-table-card">
                <div className="console-table-scroll">
                  <table className="console-table">
                    <thead>
                      <tr>
                        <th style={{ width: '35%' }}>Legacy Pair (Trigger → Target)</th>
                        <th style={{ width: '20%' }}>Status</th>
                        <th>Original AI Prior Reasoning</th>
                      </tr>
                    </thead>
                    <tbody>
                      {growthRules.length === 0 ? (
                        <tr>
                          <td colSpan="3" className="table-empty-cell">No retired priors recorded.</td>
                        </tr>
                      ) : (
                        growthRules.map((rule) => (
                          <tr key={rule.rule_id} style={{ opacity: 0.75 }}>
                            <td>
                              <div style={{ fontSize: '0.82rem', fontWeight: 600 }}>{rule.trigger_name} → {rule.target_name}</div>
                              <div style={{ fontSize: '0.72rem', color: 'var(--ink-muted)' }}>{rule.sku_a} → {rule.sku_b}</div>
                            </td>
                            <td>
                              <span className="source-tag-retired">
                                <Archive size={10} style={{ display: 'inline', marginRight: 2 }} />
                                Retired (Legacy Prior)
                              </span>
                            </td>
                            <td style={{ fontSize: '0.78rem', color: 'var(--ink-secondary)' }}>
                              "{rule.reasoning || rule.plain_language}"
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>

                {(rulesTotal > 50 || rulesHasMore) && (
                  <div className="table-load-more-bar">
                    <span>
                      Showing <strong>{growthRules.length}</strong> of <strong>{rulesTotal}</strong> retired priors (50 items per network batch)
                    </span>
                    {rulesHasMore ? (
                      <button
                        type="button"
                        className="btn-load-more"
                        onClick={handleLoadMoreRules}
                        disabled={isLoadingMoreRules}
                      >
                        {isLoadingMoreRules ? (
                          <>
                            <RefreshCw size={13} className="animate-spin" />
                            <span>Fetching next 50 priors from database…</span>
                          </>
                        ) : (
                          <>
                            <ChevronDown size={14} />
                            <span>Fetch Next 50 Priors from DB</span>
                          </>
                        )}
                      </button>
                    ) : (
                      <span style={{ fontSize: '0.74rem', color: 'var(--ink-muted)' }}>
                        ✓ All {rulesTotal} retired priors loaded from database
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

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
                      compatPairs.slice(0, compatVisibleCount).map((pair, idx) => (
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

                {compatPairs.length > 50 && (
                  <div className="table-load-more-bar">
                    <span>
                      Showing <strong>{Math.min(compatVisibleCount, compatPairs.length)}</strong> of <strong>{compatPairs.length}</strong> category pairs
                    </span>
                    {compatVisibleCount < compatPairs.length && (
                      <button
                        type="button"
                        className="btn-load-more"
                        onClick={() => setCompatVisibleCount(prev => prev + 50)}
                      >
                        <ChevronDown size={14} />
                        <span>Load Next 50 Pairs</span>
                      </button>
                    )}
                  </div>
                )}
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
                    Trained over real order sequences only (<span style={{ fontFamily: 'var(--font-mono)' }}>is_synthetic = 0</span>). Requires ≥ {embeddingStatus.min_orders_required || 10} real completed orders.
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

              <div style={{ padding: '1rem 1.25rem', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', background: '#F9FAFB', borderTop: '1px solid #E5E7EB' }}>
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
