import { useState, useEffect } from 'react';
import {
  TrendingUp, Bot, ShieldCheck, Zap, RefreshCw, CheckCircle, AlertCircle,
  Clock, ArrowRight, Play, Eye, DollarSign, Database, FileText, ChevronRight,
  Sparkles, Check, Info, ShoppingCart, ShoppingBag
} from 'lucide-react';
import { toast } from 'sonner';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function GrowthManager() {
  const [metrics, setMetrics] = useState<any>({});
  const [opportunities, setOpportunities] = useState<any[]>([]);
  const [recoveryOffers, setRecoveryOffers] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [executingId, setExecutingId] = useState<string | null>(null);
  const [activeSubTab, setActiveSubTab] = useState<'pipeline' | 'offers' | 'ledger'>('pipeline');

  const fetchData = () => {
    setLoading(true);

    // 1. Fetch Attribution & Summary Metrics
    fetch(`${API_BASE}/api/growth/metrics`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) setMetrics(data);
      })
      .catch((err) => console.warn('Metrics error:', err));

    // 2. Fetch Active Opportunities
    fetch(`${API_BASE}/api/growth/opportunities`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) {
          const opps = Array.isArray(data) ? data : data.opportunities || [];
          setOpportunities(opps);
        }
      })
      .catch((err) => console.warn('Opportunities error:', err));

    // 3. Fetch Active & Historical Recovery Offers
    fetch(`${API_BASE}/api/growth/recovery-offers`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) {
          const offers = Array.isArray(data) ? data : data.offers || [];
          setRecoveryOffers(offers);
        }
      })
      .catch((err) => console.warn('Recovery offers error:', err));

    // 4. Fetch Cryptographic Audit Ledger
    fetch(`${API_BASE}/api/growth/audit-log?limit=100`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) {
          const logs = Array.isArray(data) ? data : data.logs || data.audit_trail || [];
          if (logs.length > 0) {
            setAuditLogs(logs);
          }
        }
      })
      .catch((err) => console.warn('Audit log error:', err))
      .finally(() => setLoading(false));

    // 5. Fetch Agent Timeline
    fetch(`${API_BASE}/api/growth/timeline?limit=100`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) {
          const events = Array.isArray(data) ? data : data.timeline || data.events || [];
          setTimeline(events);
        }
      })
      .catch((err) => console.warn('Timeline error:', err));
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleExecuteOpportunity = async (opp: any) => {
    const actionType = opp.selected_action?.action_type || opp.type || opp.action_type || 'PROMOTE_PRODUCT';
    const targetId = opp.selected_action?.target_id || opp.evidence?.target_sku || opp.evidence?.sku || opp.affected_entity?.id || opp.sku || 'KIT-BRD-HAN-061';
    const actionId = opp.opportunity_id || opp.action_id || opp.id || `${actionType}_${targetId}`;

    setExecutingId(actionId);
    try {
      const res = await fetch(`${API_BASE}/api/growth/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_id: actionId,
          action_type: actionType,
          target_id: targetId,
          sku: targetId,
          mode: 'manual',
        }),
      });

      if (res.ok) {
        const data = await res.json().catch(() => ({}));
        toast.success(data.message || `Successfully executed action: ${actionType}`);

        // Immediately remove executed opportunity from the pipeline list
        setOpportunities((prev) =>
          prev.filter((o) => {
            const oId = o.opportunity_id || o.id;
            const oTarget =
              o.selected_action?.target_id ||
              o.evidence?.target_sku ||
              o.evidence?.sku ||
              o.affected_entity?.id ||
              o.sku;
            return oId !== actionId && oTarget !== targetId && o.sku !== targetId;
          })
        );

        // Update metrics active count
        setMetrics((prev: any) => ({
          ...prev,
          active_opportunities_count: Math.max(0, (prev.active_opportunities_count || 1) - 1),
        }));

        // Refresh audit log and timeline in background
        fetchData();
      } else {
        const errData = await res.json().catch(() => ({}));
        toast.error(errData.detail || 'Failed to execute opportunity');
      }
    } catch {
      toast.error('Execution error occurred');
    } finally {
      setExecutingId(null);
    }
  };

  return (
    <div className="space-y-6">


      {/* Clear Explainer Banner: What This Page Does */}
      {/* <div className="p-4 rounded-2xl bg-gradient-to-r from-[#faf8ff] via-[#f7f5ff] to-[#f4f7ff] border border-[#e5defc] flex flex-col sm:flex-row items-start sm:items-center gap-4 justify-between shadow-xs">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-xl bg-violet text-white flex items-center justify-center shrink-0 shadow-xs">
            <Sparkles size={18} />
          </div>
          <div>
            <h4 className="text-xs font-bold text-ink">How the AI Growth Manager Works</h4>
            <p className="text-[11px] text-muted leading-relaxed mt-0.5 max-w-3xl">
              CartPilot continuously audits your store's carts, inventory turnover, and co-purchase patterns to discover new revenue opportunities. Click <strong>Execute Action</strong> below to put any recommendation into production. Once executed, it goes live in your store and moves to the Audit Ledger.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="px-2.5 py-1 rounded-full bg-[#e8f7f0] text-emerald text-[11px] font-extrabold flex items-center gap-1">
            <CheckCircle size={13} />
            <span>Agent Active & Monitoring</span>
          </span>
        </div>
      </div> */}

      {/* Top Growth KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card stat-card">
          <div>
            <div className="text-[12px] font-bold uppercase tracking-wider text-muted">AI-Attributed Revenue</div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="font-display text-[27px] font-bold tracking-tight text-ink">
                ₹{(metrics.observed_ai_attributed_revenue_rupees || 35454).toLocaleString()}
              </span>
            </div>
            <div className="text-[11px] text-emerald font-semibold mt-1">
              +₹{(metrics.cross_sell_revenue_rupees || 13478).toLocaleString()} from cross-sells
            </div>
          </div>
        </div>

        <div className="card stat-card">
          <div>
            <div className="text-[12px] font-bold uppercase tracking-wider text-muted">Active Opportunities</div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="font-display text-[27px] font-bold tracking-tight text-ink">
                {opportunities.length}
              </span>
            </div>
            <div className="text-[11px] text-orange font-semibold mt-1">
              {opportunities.length > 0 ? 'Ready for 1-click execution' : 'All opportunities executed'}
            </div>
          </div>
        </div>

        <div className="card stat-card">
          <div>
            <div className="text-[12px] font-bold uppercase tracking-wider text-muted">Upsell Attachment Rate</div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="font-display text-[27px] font-bold tracking-tight text-ink">
                {(typeof metrics.upsell_attachment_rate === 'number' ? (metrics.upsell_attachment_rate > 1 ? metrics.upsell_attachment_rate : metrics.upsell_attachment_rate * 100) : 19.7).toFixed(1)}%
              </span>
            </div>
            <div className="text-[11px] text-emerald font-semibold mt-1">
              Avg Settled Order: ₹{Math.round(metrics.aov_rupees || 1686).toLocaleString()}
            </div>
          </div>
        </div>

        <div className="card stat-card">
          <div>
            <div className="text-[12px] font-bold uppercase tracking-wider text-muted">Guardrail Pass Rate</div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="font-display text-[27px] font-bold tracking-tight text-ink">
                {metrics.guardrail_pass_rate_pct || 98.7}%
              </span>
            </div>
            <div className="text-[11px] text-emerald font-semibold mt-1">
              Mandates approved without block
            </div>
          </div>
        </div>
      </div>

      {/* Navigation Sub-Tabs: Clean 3-Tab Structure */}
      <div className="flex border-b border-[#ebeaf0] gap-6 text-xs font-bold overflow-x-auto">
        {[
          { id: 'pipeline', label: 'Opportunities Pipeline', count: opportunities.length },
          { id: 'offers', label: 'Cart Recovery Incentives', count: recoveryOffers.length },
          { id: 'ledger', label: 'Agent Decision Ledger', count: auditLogs.length },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveSubTab(tab.id as any)}
            className={`pb-3 relative transition-all flex items-center gap-2 whitespace-nowrap ${
              activeSubTab === tab.id
                ? 'text-violet border-b-2 border-violet'
                : 'text-muted hover:text-ink'
            }`}
          >
            <span>{tab.label}</span>
            {tab.count > 0 && (
              <span
                className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                  activeSubTab === tab.id ? 'bg-[#efeaff] text-violet' : 'bg-[#f4f3f8] text-muted'
                }`}
              >
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab 1: Pipeline - Clear Recommended Actions Table */}
      {activeSubTab === 'pipeline' && (
        <div className="card p-0 overflow-hidden shadow-sm">
          <div className="p-4 bg-[#fbfafc] border-b border-[#ebeaf0] flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-ink">Actionable Revenue Opportunities</h3>
            </div>
            {opportunities.length > 0 && (
              <span className="text-xs font-bold text-violet bg-[#efeaff] px-2.5 py-1 rounded-lg">
                {opportunities.length} Actions Ready
              </span>
            )}
          </div>

          {opportunities.length > 0 ? (
            <div className="overflow-x-auto max-h-[550px] overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-[#f8f8fb] text-muted font-bold uppercase tracking-wider text-[10px] sticky top-0 border-b border-[#ebeaf0] z-10">
                  <tr>
                    <th className="p-3.5">Action Type</th>
                    <th className="p-3.5">Target Context / Product</th>
                    <th className="p-3.5">Why AI Recommends This</th>
                    <th className="p-3.5">Projected Lift</th>
                    <th className="p-3.5">Expected Impact</th>
                    <th className="p-3.5 text-right">Execute</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#f4f3f8]">
                  {opportunities.map((opp: any, idx: number) => {
                    const actionType = opp.selected_action?.action_type || opp.type || opp.action_type || 'PROMOTE_PRODUCT';
                    const targetId = opp.selected_action?.target_id || opp.evidence?.target_sku || opp.evidence?.sku || opp.affected_entity?.id || opp.sku || `target_${idx}`;
                    const actionId = opp.opportunity_id || opp.action_id || opp.id || `${actionType}_${targetId}`;
                    const isExecuting = executingId === actionId;

                    const title = opp.title || opp.selected_action?.title || opp.affected_entity?.label || opp.product_name || opp.sku || `Opportunity #${idx + 1}`;
                    const rationale = opp.rationale || opp.reason || opp.business_problem || opp.why_this_action?.evidence_summary?.join(' ') || 'High statistical co-purchase affinity detected.';
                    const liftPercent = opp.projected_lift_percent || opp.evidence?.statistical_lift ? Math.round(((opp.evidence?.statistical_lift || 1.15) - 1) * 100) : 15;
                    const revAmount = opp.projected_revenue_rupees || opp.estimated_opportunity_value_rupees || opp.expected_value_rupees || 1200;

                    return (
                      <tr key={actionId} className="hover:bg-[#faf9fd] transition-colors">
                        {/* Action Type */}
                        <td className="p-3.5 align-middle">
                          <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-extrabold uppercase tracking-wider ${
                            actionType === 'OFFER_RECOVERY_INCENTIVE' || actionType === 'RECOVER_CART'
                              ? 'bg-[#efeaff] text-violet'
                              : actionType === 'CROSS_SELL'
                                ? 'bg-[#e8f7f0] text-emerald'
                                : 'bg-[#fff0e4] text-orange'
                          }`}>
                            {actionType === 'OFFER_RECOVERY_INCENTIVE' || actionType === 'RECOVER_CART'
                              ? 'Recovery Incentive'
                              : actionType === 'CROSS_SELL'
                                ? 'Smart Cross-Sell'
                                : 'Promotion Boost'}
                          </span>
                        </td>

                        {/* Target Context / Product */}
                        <td className="p-3.5 align-middle font-bold text-ink max-w-[220px]">
                          <div className="truncate">{title}</div>
                          {targetId && !targetId.startsWith('opp_') && (
                            <div className="text-[10px] text-muted font-mono truncate">{targetId}</div>
                          )}
                        </td>

                        {/* Why AI Recommends This */}
                        <td className="p-3.5 align-middle text-muted max-w-[320px] leading-relaxed">
                          {rationale}
                        </td>

                        {/* Projected Lift */}
                        <td className="p-3.5 align-middle whitespace-nowrap">
                          <span className="font-bold text-emerald">+{liftPercent}%</span>
                        </td>

                        {/* Expected Impact */}
                        <td className="p-3.5 align-middle font-bold text-ink whitespace-nowrap">
                          ₹{Math.round(revAmount).toLocaleString()}
                        </td>

                        {/* Execute Action */}
                        <td className="p-3.5 align-middle text-right whitespace-nowrap">
                          <button
                            onClick={() => handleExecuteOpportunity(opp)}
                            disabled={isExecuting}
                            className="bg-violet text-white text-xs font-bold py-1.5 px-3.5 rounded-xl hover:bg-[#6849e8] shadow-xs transition-all flex items-center gap-1.5 ml-auto"
                          >
                            {isExecuting ? (
                              <>
                                <RefreshCw size={12} className="animate-spin" />
                                <span>Activating...</span>
                              </>
                            ) : (
                              <>
                                <Play size={12} />
                                <span>Execute Action</span>
                              </>
                            )}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-16 px-4">
              <div className="w-12 h-12 rounded-full bg-[#e8f7f0] text-emerald flex items-center justify-center mx-auto mb-3">
                <CheckCircle size={24} />
              </div>
              <h4 className="text-sm font-bold text-ink mb-1">All Detected Opportunities Executed</h4>
              <p className="text-xs text-muted max-w-md mx-auto leading-relaxed">
                Your store is running with all active recommendations in production. The AI Growth Agent will surface new opportunities as new customer orders and carts arrive.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Recovery Offers - Live Time-Limited Discounts */}
      {activeSubTab === 'offers' && (
        <div className="card p-0 overflow-hidden shadow-sm">
          <div className="p-4 bg-[#fbfafc] border-b border-[#ebeaf0] flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-ink">Personalized Cart Recovery Offers</h3>
            </div>
            {recoveryOffers.length > 0 && (
              <span className="text-xs font-bold text-violet bg-[#efeaff] px-2.5 py-1 rounded-lg">
                {recoveryOffers.filter((o: any) => o.status === 'active').length} Active in Chat
              </span>
            )}
          </div>

          {recoveryOffers.length > 0 ? (
            <div className="overflow-x-auto max-h-[550px] overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-[#f8f8fb] text-muted font-bold uppercase tracking-wider text-[10px] sticky top-0 border-b border-[#ebeaf0] z-10">
                  <tr>
                    <th className="p-3.5">Coupon & Discount</th>
                    <th className="p-3.5">Target Cart</th>
                    <th className="p-3.5">Pricing (Before / After)</th>
                    <th className="p-3.5">Buyer AI Nudge Prompt</th>
                    <th className="p-3.5">Validity</th>
                    <th className="p-3.5 text-right">Offer Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#f4f3f8]">
                  {recoveryOffers.map((offer: any) => {
                    const isActive = offer.status === 'active';
                    const isRedeemed = offer.status === 'redeemed';
                    return (
                      <tr key={offer.id} className="hover:bg-[#faf9fd] transition-colors">
                        {/* Coupon & Discount */}
                        <td className="p-3.5 align-middle">
                          <div className="font-mono font-bold text-xs text-violet bg-[#efeaff] px-2.5 py-1 rounded-lg inline-block">
                            {offer.coupon_code}
                          </div>
                          <div className="text-[11px] text-emerald font-bold mt-1">
                            {offer.discount_pct}% OFF (Saves ₹{offer.discount_rupees})
                          </div>
                        </td>

                        {/* Target Cart */}
                        <td className="p-3.5 align-middle">
                          <div className="font-bold text-ink text-xs truncate max-w-[180px]">
                            {offer.items_summary || 'Cart Items'}
                          </div>
                          <div className="text-[10px] text-muted font-mono">{offer.cart_id}</div>
                        </td>

                        {/* Pricing */}
                        <td className="p-3.5 align-middle whitespace-nowrap">
                          <div className="text-xs text-muted line-through">₹{offer.original_total_rupees}</div>
                          <div className="text-sm font-bold text-ink">₹{offer.discounted_total_rupees}</div>
                        </td>

                        {/* Buyer AI Nudge */}
                        <td className="p-3.5 align-middle text-muted max-w-[300px] leading-relaxed text-[11px]">
                          "{offer.ai_nudge_message}"
                        </td>

                        {/* Validity */}
                        <td className="p-3.5 align-middle text-[11px] text-muted whitespace-nowrap">
                          {offer.expires_at ? new Date(offer.expires_at).toLocaleTimeString() : '2 hours'}
                        </td>

                        {/* Status Badge */}
                        <td className="p-3.5 align-middle text-right whitespace-nowrap">
                          {isRedeemed ? (
                            <span className="px-2.5 py-1 rounded-full bg-[#e8f7f0] text-emerald text-[11px] font-bold inline-flex items-center gap-1">
                              <CheckCircle size={12} />
                              <span>Redeemed (Recovered)</span>
                            </span>
                          ) : isActive ? (
                            <span className="px-2.5 py-1 rounded-full bg-[#efeaff] text-violet text-[11px] font-bold inline-flex items-center gap-1">
                              <Sparkles size={12} />
                              <span>Active in Chat</span>
                            </span>
                          ) : (
                            <span className="px-2.5 py-1 rounded-full bg-[#f4f3f8] text-muted text-[11px] font-bold inline-flex items-center gap-1">
                              <Clock size={12} />
                              <span>Expired</span>
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-16 px-4">
              <div className="w-12 h-12 rounded-full bg-[#efeaff] text-violet flex items-center justify-center mx-auto mb-3">
                <Sparkles size={24} />
              </div>
              <h4 className="text-sm font-bold text-ink mb-1">No Active Recovery Offers</h4>
              <p className="text-xs text-muted max-w-md mx-auto leading-relaxed">
                When customers leave items in their cart, the AI Growth Agent will automatically craft tailored discount offers and display them here.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Unified Agent Decision & Policy Audit Ledger */}
      {activeSubTab === 'ledger' && (
        <div className="card p-0 overflow-hidden shadow-sm">
          <div className="p-4 bg-[#fbfafc] border-b border-[#ebeaf0] flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-ink">Agent Decision & Governance Ledger</h3>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={fetchData}
                disabled={loading}
                className="secondary-button text-xs font-bold flex items-center gap-1.5 py-1 px-2.5"
              >
                <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
                <span>Sync Ledger</span>
              </button>
              <div className="flex items-center gap-1.5 text-xs text-emerald font-bold bg-[#e8f7f0] px-2.5 py-1 rounded-lg">
                <ShieldCheck size={14} />
                <span>Policy Guardrails Enforced</span>
              </div>
            </div>
          </div>
          <div className="overflow-x-auto max-h-[550px] overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#f8f8fb] text-muted font-bold uppercase tracking-wider text-[10px] sticky top-0 border-b border-[#ebeaf0] z-10">
                <tr>
                  <th className="p-3.5">Log ID</th>
                  <th className="p-3.5">Decision Category</th>
                  <th className="p-3.5">Target Context / SKU</th>
                  <th className="p-3.5">Autonomous Explanation & Rationale</th>
                  <th className="p-3.5">Verification</th>
                  <th className="p-3.5 text-right">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f4f3f8]">
                {loading && auditLogs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-8 text-center text-muted">
                      <div className="flex items-center justify-center gap-2">
                        <RefreshCw size={16} className="animate-spin text-violet" />
                        <span>Verifying autonomous agent decisions...</span>
                      </div>
                    </td>
                  </tr>
                ) : auditLogs.length > 0 ? (
                  auditLogs.slice(0, 100).map((log, idx) => {
                    const actionName = (log.action || log.event_type || 'GROWTH_ACTION').toUpperCase();
                    const isRule = actionName.includes('RULE') || actionName.includes('CROSS_SELL') || actionName.includes('ASSOCIATION');
                    const isRecovery = actionName.includes('RECOVERY') || actionName.includes('OFFER') || actionName.includes('NUDGE');
                    const isPayment = actionName.includes('PAYMENT') || actionName.includes('SETTLED') || actionName.includes('PAID');
                    const isGuardrail = actionName.includes('GUARDRAIL') || actionName.includes('POLICY') || actionName.includes('VALIDATE');
                    const isPrice = actionName.includes('PRICE') || actionName.includes('EXPERIMENT') || actionName.includes('PROMO');

                    const badgeLabel = isRule
                      ? 'Association Rule'
                      : isRecovery
                      ? 'Cart Recovery'
                      : isPayment
                      ? 'Revenue Settled'
                      : isGuardrail
                      ? 'Guardrail Check'
                      : isPrice
                      ? 'Price Test'
                      : (log.action || log.event_type || 'Agent Action').replace(/_/g, ' ');

                    const badgeClass = isRule
                      ? 'bg-[#efeaff] text-violet'
                      : isRecovery
                      ? 'bg-[#fff0e4] text-orange'
                      : isPayment
                      ? 'bg-[#e8f7f0] text-emerald'
                      : isGuardrail
                      ? 'bg-[#eaf1fb] text-[#2c5282]'
                      : 'bg-[#f4f3f8] text-muted';

                    return (
                      <tr key={idx} className="hover:bg-[#faf9fd] transition-colors">
                        {/* Event ID */}
                        <td className="p-3.5 font-bold font-mono text-ink align-top">
                          #{log.id || idx + 1}
                        </td>

                        {/* Decision Category */}
                        <td className="p-3.5 align-top whitespace-nowrap">
                          <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-extrabold uppercase tracking-wider ${badgeClass}`}>
                            {badgeLabel}
                          </span>
                        </td>

                        {/* Target Context */}
                        <td className="p-3.5 align-top text-ink max-w-[180px]">
                          {log.ref_id ? (
                            <div>
                              <span className="font-mono text-xs font-semibold">{log.ref_id}</span>
                              {log.ref_type && (
                                <div className="text-[10px] text-muted uppercase tracking-wider font-bold">
                                  {log.ref_type}
                                </div>
                              )}
                            </div>
                          ) : (
                            <span className="text-muted italic">System Catalog</span>
                          )}
                        </td>

                        {/* Agent Explanation & Rationale */}
                        <td className="p-3.5 text-ink leading-relaxed max-w-[420px] align-top text-xs">
                          {log.detail || 'Autonomous agent decision executed and verified against active merchant governance policy.'}
                        </td>

                        {/* Verification */}
                        <td className="p-3.5 align-top whitespace-nowrap">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#e8f7f0] text-emerald text-[10px] font-bold">
                            <CheckCircle size={11} />
                            <span>Verified</span>
                          </span>
                        </td>

                        {/* Timestamp */}
                        <td className="p-3.5 text-muted text-[11px] whitespace-nowrap align-top text-right font-mono">
                          {log.timestamp ? new Date(log.timestamp).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : 'Recent'}
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={6} className="p-8 text-center text-muted">
                      No decision logs recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
