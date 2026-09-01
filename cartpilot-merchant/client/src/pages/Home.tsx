import { useEffect, useState, useRef, useMemo } from "react";
import { Link, useLocation } from "wouter";
import { useAuth } from "../contexts/AuthContext";
import {
  Activity, ArrowUpRight, BarChart3, Bell, Bot, Boxes, ChevronRight, CircleHelp,
  CloudSun, Command, Compass, CreditCard, FlaskConical, Gauge, LayoutDashboard,
  Network, Plus, Save, Search, Settings2, ShieldCheck,
  ShoppingCart, Store, Sun, TrendingUp, Users, X, Zap, LogOut, CheckCircle, Trash2,
  Lock, RefreshCw, Play, Sliders, FileText, Download, ChevronDown, Check, AlertCircle,
  PanelLeftClose, PanelLeftOpen, Clock, ArrowRight
} from "lucide-react";
import { toast } from "sonner";
import GrowthManager from "./merchant/GrowthManager";
import GrowthRules from "./merchant/GrowthRules";
import AuditTrail from "./merchant/AuditTrail";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const NAV_ITEMS = [
  { label: "Overview", path: "/merchant", icon: LayoutDashboard, group: "Command Center" },
  { label: "AI Growth Manager", path: "/merchant/growth", icon: TrendingUp, group: "Autonomous Growth", badge: "Agentic" },
  { label: "Growth Rules & RecSys Lab", path: "/merchant/rules", icon: SparklesIcon, group: "Autonomous Growth" },
  { label: "Promotion Experiments", path: "/merchant/experiments", icon: FlaskConical, group: "Autonomous Growth" },
  { label: "Catalog & Senses", path: "/merchant/catalog", icon: Boxes, group: "Store Management" },
  { label: "Category Compatibility", path: "/merchant/recommendations", icon: Network, group: "Store Management" },
  { label: "Order Audit Trail", path: "/merchant/audit", icon: ShieldCheck, group: "Store Management", badge: "Verified" },
  { label: "Policy Guardrails", path: "/merchant/policy", icon: Sliders, group: "Store Management" },
];

function SparklesIcon(props: any) {
  return <Zap {...props} />;
}

function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

function useApi<T>(path: string, fallback: T) {
  const [data, setData] = useState<T>(fallback);
  useEffect(() => {
    fetch(apiUrl(path))
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setData)
      .catch(() => setData(fallback));
  }, [path]);
  return data;
}

// ── App Brand Logo (Dark Emerald Rounded Square with Shopping Cart) ─────────
function Logo({ collapsed }: { collapsed?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className="logo-mark" style={{ background: "#115e59", color: "#ffffff", borderRadius: "9px" }}>
        <ShoppingCart size={17} strokeWidth={2.4} color="#ffffff" />
      </div>
      {!collapsed && (
        <span className="font-display text-[19px] font-bold tracking-tight text-ink logo-text">
          CartPilot
        </span>
      )}
    </div>
  );
}

function Sidebar({ collapsed }: { collapsed: boolean }) {
  const [location] = useLocation();
  const { user } = useAuth();
  const [showHelpModal, setShowHelpModal] = useState(false);

  return (
    <>
      <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
        {/* Brand Header cleanly positioned without overlapping toggle button */}
        <div className={`flex items-center pt-5 pb-3 ${collapsed ? "justify-center px-0" : "px-5 justify-between"}`}>
          <Logo collapsed={collapsed} />
        </div>

        {/* Navigation Groups */}
        <nav className="px-3 mt-3 flex-1 overflow-y-auto">
          {["Command Center", "Autonomous Growth", "Store Management"].map((group) => (
            <div key={group} className="mb-5">
              {!collapsed && <div className="eyebrow px-3 mb-1.5">{group}</div>}
              {NAV_ITEMS.filter((n) => n.group === group).map((item) => {
                const Icon = item.icon;
                const active =
                  location === item.path ||
                  (item.path === "/merchant" && (location === "/" || location === "/merchant"));
                return (
                  <Link key={item.path} href={item.path}>
                    <div
                      className={`nav-item ${active ? "active" : ""}`}
                      title={collapsed ? item.label : undefined}
                    >
                      <Icon size={16} />
                      {!collapsed && <span>{item.label}</span>}
                      {!collapsed && item.badge && <span className="live-badge">{item.badge}</span>}
                    </div>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Sidebar Bottom: Clean Help & App Overview Button */}
        <div className="sidebar-bottom">
          {!collapsed ? (
            <button
              onClick={() => setShowHelpModal(true)}
              className="w-full flex items-center justify-between p-2.5 rounded-xl bg-[#faf9fd] hover:bg-[#efeaff] border border-[#efedf5] hover:border-violet/30 text-ink transition-all group shadow-sm text-left"
            >
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-lg bg-[#efeaff] text-violet flex items-center justify-center group-hover:bg-violet group-hover:text-white transition-colors">
                  <CircleHelp size={15} />
                </div>
                <div>
                  <div className="text-[12px] font-bold text-ink leading-tight">About CartPilot</div>
                  <div className="text-[10px] text-muted">What our app does</div>
                </div>
              </div>
              <ChevronRight size={14} className="text-muted group-hover:text-violet transition-colors" />
            </button>
          ) : (
            <button
              onClick={() => setShowHelpModal(true)}
              className="w-10 h-10 mx-auto rounded-xl bg-[#faf9fd] hover:bg-[#efeaff] border border-[#efedf5] hover:border-violet/30 text-violet flex items-center justify-center transition-all shadow-sm"
              title="About CartPilot — What this app does"
            >
              <CircleHelp size={18} />
            </button>
          )}
        </div>
      </aside>

      {/* About CartPilot Interactive Help Modal */}
      {showHelpModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-xl w-full shadow-2xl border border-[#ebeaf0] overflow-hidden animate-in fade-in zoom-in-95">
            {/* Modal Header */}
            <div className="p-5 bg-gradient-to-r from-[#115e59] to-[#0f766e] text-white flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-white/15 backdrop-blur-sm flex items-center justify-center text-white">
                  <ShoppingCart size={18} strokeWidth={2.4} />
                </div>
                <div>
                  <h3 className="font-display text-base font-bold leading-tight">About CartPilot</h3>
                  <p className="text-xs text-white/80">Autonomous Commerce & Growth Platform</p>
                </div>
              </div>
              <button
                onClick={() => setShowHelpModal(false)}
                className="w-8 h-8 rounded-lg bg-white/10 hover:bg-white/20 flex items-center justify-center text-white transition-all"
              >
                <X size={16} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
              <div className="p-3.5 rounded-xl bg-[#faf9fd] border border-[#efedf5] text-xs text-ink leading-relaxed">
                <strong className="text-violet">CartPilot</strong> is an AI-powered autonomous commerce platform that helps merchants maximize revenue through automated merchandising, intelligent recommendation pipelines, and safe buyer checkout workflows.
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                <div className="p-3.5 rounded-xl border border-[#ebeaf0] bg-white hover:border-violet/40 transition-all shadow-sm">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-base">📈</span>
                    <h4 className="font-display text-xs font-bold text-ink">Autonomous Growth (DiD)</h4>
                  </div>
                  <p className="text-[11px] text-muted leading-relaxed">
                    Runs A/B price experiments, measures causal revenue lift via Difference-in-Differences, and locks proven promotions permanently.
                  </p>
                </div>

                <div className="p-3.5 rounded-xl border border-[#ebeaf0] bg-white hover:border-violet/40 transition-all shadow-sm">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-base">⚡</span>
                    <h4 className="font-display text-xs font-bold text-ink">3-Tier RecSys Engine</h4>
                  </div>
                  <p className="text-[11px] text-muted leading-relaxed">
                    Combines Item2Vec neural embeddings (Tier 1), empirical co-purchase rules (Tier 2), and semantic category compatibility (Tier 3).
                  </p>
                </div>

                <div className="p-3.5 rounded-xl border border-[#ebeaf0] bg-white hover:border-violet/40 transition-all shadow-sm">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-base">🌦️</span>
                    <h4 className="font-display text-xs font-bold text-ink">Environmental Merchandising</h4>
                  </div>
                  <p className="text-[11px] text-muted leading-relaxed">
                    Adjusts catalog visibility weights in real-time based on live city weather, seasonal conditions, and upcoming festivals.
                  </p>
                </div>

                <div className="p-3.5 rounded-xl border border-[#ebeaf0] bg-white hover:border-violet/40 transition-all shadow-sm">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-base">🛡️</span>
                    <h4 className="font-display text-xs font-bold text-ink">Guardrails & Audit Ledger</h4>
                  </div>
                  <p className="text-[11px] text-muted leading-relaxed">
                    Strict spend caps, autonomy thresholds, and an immutable SHA-256 cryptographic audit trail for all orders and decisions.
                  </p>
                </div>
              </div>

              <div className="pt-2 flex justify-end">
                <button
                  onClick={() => setShowHelpModal(false)}
                  className="px-4 py-2 rounded-xl bg-violet text-white text-xs font-bold shadow-md hover:bg-[#6849d8] transition-all"
                >
                  Got it, close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ── Top Navigation Header with Robot Autonomy Dropdown & Merchant Store Name ─
function Header({ collapsed, onToggleCollapse }: { collapsed: boolean; onToggleCollapse: () => void }) {
  const { user, logout } = useAuth();
  const [, setLocation] = useLocation();

  const [growthMode, setGrowthMode] = useState("autonomous");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [runningWorker, setRunningWorker] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(apiUrl("/api/growth/worker-status"))
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.mode) setGrowthMode(d.mode);
      })
      .catch(() => {});

    const handleOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  const handleModeChange = async (mode: string) => {
    setGrowthMode(mode);
    setDropdownOpen(false);
    try {
      await fetch(apiUrl("/api/growth/worker-status"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      toast.success(`Agent Autonomy Mode: ${mode.toUpperCase()}`);
    } catch {
      toast.error("Failed to update autonomy mode");
    }
  };

  const handleRunNow = async () => {
    setRunningWorker(true);
    try {
      const res = await fetch(apiUrl("/api/growth/worker-run-now"), { method: "POST" });
      if (res.ok) {
        toast.success("Autonomous optimization worker executed successfully!");
      }
    } catch {
      toast.error("Worker trigger failed");
    } finally {
      setRunningWorker(false);
    }
  };

  return (
    <header className="topbar">
      {/* Left side: Clean Sidebar Collapse Toggle + Merchant Business Name */}
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleCollapse}
          className="p-2 rounded-xl text-muted hover:text-ink hover:bg-white border border-transparent hover:border-[#ebeaf0] shadow-none hover:shadow-sm transition-all"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>

        <div className="h-5 w-px bg-[#ebeaf0] hidden sm:block" />

        {/* Merchant Business Name & Workspace Badge */}
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#115e59] text-white flex items-center justify-center text-xs font-bold shadow-sm shrink-0">
            {user?.storeName ? user.storeName.slice(0, 1).toUpperCase() : "N"}
          </div>
          <div>
            <div className="font-display text-sm font-bold text-ink leading-tight truncate max-w-[220px] sm:max-w-[320px]">
              {user?.storeName || "Northstar Supply"}
            </div>
            <div className="text-[10px] text-muted font-medium flex items-center gap-1.5">
              <span>Merchant Workspace</span>
              <span className="w-1 h-1 rounded-full bg-muted opacity-40" />
              <span className="text-emerald font-semibold">Store Live</span>
            </div>
          </div>
        </div>
      </div>

      <div className="ml-auto flex items-center gap-3">
        {/* Robot Agent Autonomy Dropdown Button */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 px-3 py-1.5 bg-white hover:bg-[#faf9fd] border border-[#ebeaf0] rounded-xl text-xs font-bold text-ink shadow-sm transition-all"
            title="Agent Autonomy Controller"
          >
            <div className="w-6 h-6 rounded-lg bg-[#efeaff] text-violet flex items-center justify-center">
              <Bot size={15} />
            </div>
            <span className="capitalize">{growthMode}</span>
            <span className="w-2 h-2 rounded-full bg-[#2a9a71] animate-pulse" />
            <ChevronDown size={14} className={`text-muted transition-transform ${dropdownOpen ? "rotate-180" : ""}`} />
          </button>

          {/* Autonomy Dropdown Menu */}
          {dropdownOpen && (
            <div className="absolute right-0 mt-2 w-72 bg-white border border-[#ebeaf0] rounded-2xl shadow-xl p-3 z-50 animate-in fade-in zoom-in-95">
              <div className="px-2 py-1.5 mb-2 border-b border-[#f4f3f8]">
                <div className="eyebrow text-violet">AI Merchandising Autonomy</div>
                <p className="text-[11px] text-muted mt-0.5">Control how autonomous agents execute price & catalog shifts.</p>
              </div>

              <div className="space-y-1">
                {[
                  { id: "manual", title: "Manual Mode", desc: "Human confirms all actions before apply" },
                  { id: "suggested", title: "Suggested Mode", desc: "Agent drafts opportunities; 1-click execution" },
                  { id: "autonomous", title: "Autonomous Mode", desc: "Agent self-runs DiD experiments & pricing shifts" },
                ].map((m) => (
                  <button
                    key={m.id}
                    onClick={() => handleModeChange(m.id)}
                    className={`w-full text-left p-2.5 rounded-xl transition-all flex items-start justify-between ${
                      growthMode === m.id
                        ? "bg-[#efeaff] text-violet font-bold"
                        : "hover:bg-[#fbfafc] text-ink font-semibold"
                    }`}
                  >
                    <div>
                      <div className="text-xs">{m.title}</div>
                      <div className="text-[10px] text-muted font-normal mt-0.5">{m.desc}</div>
                    </div>
                    {growthMode === m.id && <Check size={14} className="text-violet shrink-0 mt-0.5" />}
                  </button>
                ))}
              </div>

              <div className="mt-3 pt-2 border-t border-[#f4f3f8]">
                <button
                  onClick={handleRunNow}
                  disabled={runningWorker}
                  className="w-full py-2 bg-violet text-white text-xs font-bold rounded-lg shadow-sm hover:bg-[#6849d8] flex items-center justify-center gap-1.5 transition-all"
                >
                  <RefreshCw size={13} className={runningWorker ? "animate-spin" : ""} />
                  <span>{runningWorker ? "Optimizing..." : "Run Optimization Cycle Now"}</span>
                </button>
              </div>
            </div>
          )}
        </div>

        <button className="icon-button" title="Notifications">
          <Bell size={17} />
          <span className="notification-dot" />
        </button>

        <div className="profile pl-2 border-l border-[#ebeaf0]">
          <div className="profile-avatar">
            {user?.name ? user.name.slice(0, 2).toUpperCase() : "JD"}
          </div>
          <span className="hidden sm:inline text-xs font-semibold text-ink">{user?.name || "Jamie Diaz"}</span>
          <button
            onClick={() => {
              logout();
              setLocation("/auth");
            }}
            title="Sign Out"
            className="p-1.5 text-muted hover:text-ink hover:bg-[#f4f3f8] rounded-lg transition-all ml-1"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </header>
  );
}

function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        <div className="eyebrow text-violet mb-2">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`card ${className}`}>{children}</div>;
}

// ── Modern KPI Stat Card with Icon Positioned Top-Right ─────────────────────
function Stat({ label, value, delta, icon: Icon, tint }: any) {
  return (
    <Card className="stat-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[12px] font-bold text-muted uppercase tracking-wider">{label}</div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-display text-[27px] font-bold tracking-tight text-ink">{value}</span>
            <span className="text-[11px] font-bold text-emerald">{delta}</span>
          </div>
        </div>
        <div className={`stat-icon shrink-0 ${tint}`}>
          <Icon size={18} />
        </div>
      </div>
    </Card>
  );
}

// ── Interactive Chart Component with Dropdown Timeframe ──────────────────────
interface ChartPoint {
  date: string;
  orders: number;
  crossSells: number;
  revenueRupees: number;
}

const DATA_30D: ChartPoint[] = [
  { date: "Aug 03", orders: 120, crossSells: 45, revenueRupees: 8400 },
  { date: "Aug 06", orders: 165, crossSells: 62, revenueRupees: 11200 },
  { date: "Aug 09", orders: 230, crossSells: 95, revenueRupees: 16800 },
  { date: "Aug 12", orders: 195, crossSells: 80, revenueRupees: 14300 },
  { date: "Aug 15", orders: 280, crossSells: 120, revenueRupees: 21500 },
  { date: "Aug 18", orders: 340, crossSells: 145, revenueRupees: 26200 },
  { date: "Aug 21", orders: 410, crossSells: 178, revenueRupees: 31900 },
  { date: "Aug 24", orders: 480, crossSells: 210, revenueRupees: 38400 },
  { date: "Aug 27", orders: 560, crossSells: 245, revenueRupees: 45200 },
  { date: "Aug 31", orders: 642, crossSells: 289, revenueRupees: 52800 },
];

const DATA_14D: ChartPoint[] = DATA_30D.slice(4);
const DATA_7D: ChartPoint[] = DATA_30D.slice(6);

function InteractiveCommerceChart() {
  const [timeframe, setTimeframe] = useState<"7D" | "14D" | "30D">("30D");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [showOrders, setShowOrders] = useState(true);
  const [showCrossSells, setShowCrossSells] = useState(true);
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const dropdownRef = useRef<HTMLDivElement>(null);
  const data = timeframe === "7D" ? DATA_7D : timeframe === "14D" ? DATA_14D : DATA_30D;

  const svgRef = useRef<SVGSVGElement>(null);
  const width = 700;
  const height = 200;
  const maxVal = 800;

  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  const getPoints = (key: "orders" | "crossSells") => {
    return data.map((d, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - (d[key] / maxVal) * height;
      return { x, y, val: d[key] };
    });
  };

  const ordersPoints = getPoints("orders");
  const crossSellsPoints = getPoints("crossSells");

  const buildSmoothPath = (pts: { x: number; y: number }[]) => {
    if (pts.length === 0) return "";
    let d = `M ${pts[0].x} ${pts[0].y}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i];
      const p1 = pts[i + 1];
      const mx = (p0.x + p1.x) / 2;
      d += ` C ${mx} ${p0.y}, ${mx} ${p1.y}, ${p1.x} ${p1.y}`;
    }
    return d;
  };

  const ordersPath = buildSmoothPath(ordersPoints);
  const crossSellsPath = buildSmoothPath(crossSellsPoints);

  const ordersArea = `${ordersPath} L ${width} ${height} L 0 ${height} Z`;
  const crossSellsArea = `${crossSellsPath} L ${width} ${height} L 0 ${height} Z`;

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const mouseX = Math.max(0, Math.min(width, ((e.clientX - rect.left) / rect.width) * width));
    const step = width / (data.length - 1);
    const idx = Math.max(0, Math.min(data.length - 1, Math.round(mouseX / step)));
    setHoveredIdx(idx);
  };

  const activePoint = hoveredIdx !== null ? data[hoveredIdx] : data[data.length - 1];
  const activeX = hoveredIdx !== null ? (hoveredIdx / (data.length - 1)) * width : width;

  return (
    <Card className="chart-card">
      <div className="card-heading flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3>AI Commerce Activity</h3>
          <p>Interactive tracking of autonomous orders and recommendation cross-sells</p>
        </div>

        {/* Timeframe Dropdown Menu */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 px-3 py-1.5 bg-[#f4f3f8] hover:bg-[#eae8f2] border border-[#ebeaf0] rounded-xl text-xs font-bold text-ink transition-all shadow-sm"
          >
            <span>{timeframe === "7D" ? "Last 7 Days" : timeframe === "14D" ? "Last 14 Days" : "Last 30 Days"}</span>
            <ChevronDown size={14} className={`text-muted transition-transform ${dropdownOpen ? "rotate-180" : ""}`} />
          </button>

          {dropdownOpen && (
            <div className="absolute right-0 mt-1.5 w-36 bg-white border border-[#ebeaf0] rounded-xl shadow-lg p-1 z-30">
              {[
                { id: "7D", label: "Last 7 Days" },
                { id: "14D", label: "Last 14 Days" },
                { id: "30D", label: "Last 30 Days" },
              ].map((t) => (
                <button
                  key={t.id}
                  onClick={() => {
                    setTimeframe(t.id as any);
                    setDropdownOpen(false);
                    setHoveredIdx(null);
                  }}
                  className={`w-full text-left px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center justify-between ${
                    timeframe === t.id
                      ? "bg-[#efeaff] text-violet"
                      : "text-ink hover:bg-[#faf9fd]"
                  }`}
                >
                  <span>{t.label}</span>
                  {timeframe === t.id && <Check size={13} />}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Metric Filter Toggles & Live Tooltip Strip */}
      <div className="flex flex-wrap items-center justify-between gap-4 mt-5 mb-3">
        <div className="chart-legend !my-0">
          <button
            onClick={() => setShowOrders(!showOrders)}
            className={`flex items-center gap-1.5 text-xs font-semibold cursor-pointer ${
              showOrders ? "text-ink" : "text-muted opacity-50"
            }`}
          >
            <span className="legend-dot bg-violet" />
            AI-Influenced Orders ({data[data.length - 1].orders})
          </button>
          <button
            onClick={() => setShowCrossSells(!showCrossSells)}
            className={`flex items-center gap-1.5 text-xs font-semibold cursor-pointer ${
              showCrossSells ? "text-ink" : "text-muted opacity-50"
            }`}
          >
            <span className="legend-dot bg-orange" />
            Cross-Sell Conversions ({data[data.length - 1].crossSells})
          </button>
        </div>

        {/* Dynamic Hover Insight Card */}
        {activePoint && (
          <div className="flex items-center gap-3 bg-[#faf9fd] border border-[#e8e4f5] px-3 py-1.5 rounded-xl text-xs font-bold">
            <span className="text-muted">{activePoint.date}:</span>
            <span className="text-violet">{activePoint.orders} Orders</span>
            <span className="text-orange">{activePoint.crossSells} Cross-sells</span>
            <span className="text-emerald font-mono">+₹{activePoint.revenueRupees.toLocaleString()} Lift</span>
          </div>
        )}
      </div>

      {/* Interactive SVG Canvas */}
      <div className="chart">
        <div className="chart-y">
          <span>800</span>
          <span>600</span>
          <span>400</span>
          <span>200</span>
          <span>0</span>
        </div>
        <div className="chart-area">
          <div className="grid-lines" />
          <svg
            ref={svgRef}
            viewBox={`0 0 ${width} ${height}`}
            preserveAspectRatio="none"
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setHoveredIdx(null)}
            className="cursor-crosshair overflow-visible"
          >
            <defs>
              <linearGradient id="fill-violet" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0" stopColor="#7657e8" stopOpacity=".26" />
                <stop offset="1" stopColor="#7657e8" stopOpacity="0" />
              </linearGradient>
              <linearGradient id="fill-orange" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0" stopColor="#e89756" stopOpacity=".22" />
                <stop offset="1" stopColor="#e89756" stopOpacity="0" />
              </linearGradient>
            </defs>

            {/* Orders Area & Curve */}
            {showOrders && (
              <>
                <path d={ordersArea} fill="url(#fill-violet)" />
                <path
                  d={ordersPath}
                  fill="none"
                  stroke="#7657e8"
                  strokeWidth="3"
                  vectorEffect="non-scaling-stroke"
                />
              </>
            )}

            {/* Cross-sells Area & Curve */}
            {showCrossSells && (
              <>
                <path d={crossSellsArea} fill="url(#fill-orange)" />
                <path
                  d={crossSellsPath}
                  fill="none"
                  stroke="#e89756"
                  strokeWidth="2.5"
                  strokeDasharray="4 3"
                  vectorEffect="non-scaling-stroke"
                />
              </>
            )}

            {/* Interactive Vertical Cursor Line */}
            {hoveredIdx !== null && (
              <>
                <line
                  x1={activeX}
                  y1={0}
                  x2={activeX}
                  y2={height}
                  stroke="#7657e8"
                  strokeWidth="1.5"
                  strokeDasharray="3 3"
                />
                {showOrders && (
                  <circle
                    cx={activeX}
                    cy={ordersPoints[hoveredIdx].y}
                    r="5"
                    fill="#7657e8"
                    stroke="#fff"
                    strokeWidth="2"
                  />
                )}
                {showCrossSells && (
                  <circle
                    cx={activeX}
                    cy={crossSellsPoints[hoveredIdx].y}
                    r="4.5"
                    fill="#e89756"
                    stroke="#fff"
                    strokeWidth="2"
                  />
                )}
              </>
            )}
          </svg>

          <div className="chart-x">
            {data.map((d, i) => (
              <span key={i} className={hoveredIdx === i ? "text-violet font-bold" : ""}>
                {d.date}
              </span>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}

// ── Overview Component with Working Report Export ────────────────────────────
function Overview() {
  const metrics: any = useApi("/api/growth/metrics", {
    observed_ai_attributed_revenue_rupees: 24891,
    total_orders_count: 642,
    aov_rupees: 86.4,
    guardrail_pass_rate_pct: 98.7,
  });

  const seasonal: any = useApi("/api/catalog/seasonal-context", {
    season: "Monsoon",
    weather: { description: "Rainy & overcast", temp_celsius: 28, city: "Delhi" },
    boost_weight: 1.15,
    upcoming_festivals: ["Raksha Bandhan", "Onam"],
  });

  const timelineData: any = useApi("/api/growth/timeline?limit=10", { timeline: [] });
  const auditData: any = useApi("/api/growth/audit-log?limit=10", { logs: [] });

  const rawTimeline = Array.isArray(timelineData?.timeline)
    ? timelineData.timeline
    : Array.isArray(timelineData?.events)
    ? timelineData.events
    : [];
  const rawLogs = Array.isArray(auditData?.logs) ? auditData.logs : [];

  const activityList =
    rawTimeline.length > 0
      ? rawTimeline.map((t: any) => ({
          id: t.id,
          type: t.action_type || t.event_type?.toUpperCase() || "AUTONOMOUS_ACTION",
          title: t.title || t.event_name || "Autonomous Decision",
          desc: t.detail || t.description || "Evaluated catalog and executed recommendation.",
          time: t.timestamp
            ? new Date(t.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) +
              ", " +
              new Date(t.timestamp).toLocaleDateString([], { month: "short", day: "numeric" })
            : "Just now",
          status: t.status?.toUpperCase() || (t.event_type === "revenue_outcome" ? "SETTLED" : "VERIFIED"),
        }))
      : rawLogs.map((l: any) => ({
          id: l.id,
          type: l.ref_type?.toUpperCase() || "AUDIT_EVENT",
          title: l.action || l.event_type || "Agent Action",
          desc: l.detail || "Autonomous merchant agent executed action and verified with policy.",
          time: l.timestamp
            ? new Date(l.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) +
              ", " +
              new Date(l.timestamp).toLocaleDateString([], { month: "short", day: "numeric" })
            : "Just now",
          status: "VERIFIED",
        }));

  const weatherObj = typeof seasonal?.weather === "object" && seasonal?.weather !== null ? seasonal.weather : null;
  const weatherDesc = weatherObj?.description || weatherObj?.condition || (typeof seasonal?.weather === "string" ? seasonal.weather : "Rainy & overcast");
  const temperature = weatherObj?.temp_celsius ?? (typeof seasonal?.temperature === "number" ? seasonal.temperature : 28);
  const cityName = weatherObj?.city || (typeof seasonal?.city === "string" ? seasonal.city : "Delhi");
  const seasonName = seasonal?.season_label || seasonal?.season || "Monsoon";
  const boostMultiplier = seasonal?.boost_weight || 1.15;
  const festivalsRaw = seasonal?.upcoming_festivals || seasonal?.festivals || ["Raksha Bandhan", "Onam"];
  const festivalsStr = Array.isArray(festivalsRaw)
    ? festivalsRaw.map((f: any) => (typeof f === "object" && f !== null ? f.name || f.title || "Festival" : String(f))).join(", ")
    : "Standard Season";

  const handleExportReport = () => {
    const headers = ["Metric", "Value", "Notes"];
    const rows = [
      ["Report Date", new Date().toISOString().slice(0, 10), "Executive Commerce Summary"],
      ["AI-Attributed Revenue (INR)", String(metrics.observed_ai_attributed_revenue_rupees || 24891), "Direct lift from RecSys"],
      ["Autonomous Orders Count", String(metrics.total_orders_count || 642), "Orders handled autonomously"],
      ["Average Order Value (INR)", String(metrics.aov_rupees || 86.4), "AOV across catalog"],
      ["Guardrail Pass Rate", `${metrics.guardrail_pass_rate_pct || 98.7}%`, "Mandates approved without block"],
      ["Current Season", seasonName, cityName],
      ["Seasonal Boost Multiplier", `${boostMultiplier}x`, "Dynamic environmental weight"],
      ["Active Festivals", festivalsStr, "Festival merchandising"]
    ];

    const csvContent = [headers.join(","), ...rows.map((r) => r.map((c) => `"${c}"`).join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `cartpilot_executive_report_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    toast.success("Downloaded executive report CSV!");
  };

  return (
    <>
      <PageHeader
        eyebrow="Autonomous Commerce Pulse"
        title="Store Overview"
        description="Your autonomous agents are continuously optimizing catalog pricing, seasonal visibility, and checkout guardrails."
        action={
          <button className="primary-button" onClick={handleExportReport}>
            <Download size={15} /> Export Report
          </button>
        }
      />

      <div className="stat-grid">
        <Stat
          label="AI-Attributed Revenue"
          value={`₹${(metrics.observed_ai_attributed_revenue_rupees || 24891).toLocaleString()}`}
          delta="+18.4%"
          icon={TrendingUp}
          tint="tint-violet"
        />
        <Stat
          label="Autonomous Orders"
          value={metrics.total_orders_count || 642}
          delta="+12.8%"
          icon={Bot}
          tint="tint-orange"
        />
        <Stat
          label="Avg. Order Value"
          value={`₹${Math.round(metrics.aov_rupees || 86)}`}
          delta="+6.2%"
          icon={CreditCard}
          tint="tint-green"
        />
        <Stat
          label="Guardrail Pass Rate"
          value={`${metrics.guardrail_pass_rate_pct || 98.7}%`}
          delta="+1.4%"
          icon={Gauge}
          tint="tint-blue"
        />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.45fr_0.9fr] mt-5">
        {/* Interactive Chart with Dropdown Timeframe */}
        <InteractiveCommerceChart />

        {/* Live Environmental Context Card */}
        <Card>
          <div className="card-heading">
            <div>
              <h3>Live Environmental Senses</h3>
              <p>Dynamic context shaping RecSys weights</p>
            </div>
            <CloudSun size={20} className="text-violet" />
          </div>
          <div className="weather-block">
            <Sun size={30} />
            <div>
              <div className="font-display text-2xl font-bold">
                {temperature}°C{" "}
                <span className="text-sm font-sans font-medium opacity-75">{weatherDesc}</span>
              </div>
              <div className="text-xs opacity-75">
                {cityName} · {seasonName}
              </div>
            </div>
          </div>
          <div className="sense-row">
            <span>Active Festival Context</span>
            <strong>{festivalsStr}</strong>
          </div>
          <div className="sense-row">
            <span>Category Multiplier</span>
            <strong className="text-emerald font-bold">
              {boostMultiplier}× Visibility Boost
            </strong>
          </div>
        </Card>
      </div>

      {/* Top 10 Autonomous Agent Decisions & Activity Table */}
      <Card className="p-0 overflow-hidden shadow-sm mt-6">
        <div className="p-4 bg-[#fbfafc] border-b border-[#ebeaf0] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-lg bg-[#efeaff] text-violet flex items-center justify-center">
                <Bot size={14} />
              </div>
              <h3 className="font-display text-sm font-bold text-ink">Recent Autonomous Agent Activity (Top 10)</h3>
            </div>
            <p className="text-xs text-muted mt-0.5">
              Live automated merchandising decisions, price experiments, and cart recovery triggers.
            </p>
          </div>

          <Link href="/merchant/growth">
            <button className="secondary-button text-xs font-bold flex items-center gap-1.5 self-start sm:self-auto hover:text-violet">
              <Clock size={13} />
              <span>View Full Agent Decision Timeline →</span>
            </button>
          </Link>
        </div>

        <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8f8fb] text-muted font-bold uppercase tracking-wider text-[10px] sticky top-0 border-b border-[#ebeaf0] z-10">
              <tr>
                <th className="p-3.5">Action Event / Type</th>
                <th className="p-3.5">Context & Rationale</th>
                <th className="p-3.5">Timestamp</th>
                <th className="p-3.5 text-right">Agent Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f4f3f8]">
              {activityList.length > 0 ? (
                activityList.slice(0, 10).map((act: any, idx: number) => (
                  <tr key={act.id || idx} className="hover:bg-[#faf9fd] transition-colors">
                    <td className="p-3.5 align-top">
                      <div className="font-bold text-ink">{act.title}</div>
                      <span className="text-[10px] font-mono text-muted uppercase tracking-wider">{act.type}</span>
                    </td>
                    <td className="p-3.5 align-top text-muted max-w-[420px] leading-relaxed text-xs">
                      {act.desc}
                    </td>
                    <td className="p-3.5 align-top text-muted text-[11px] whitespace-nowrap font-mono">
                      {act.time}
                    </td>
                    <td className="p-3.5 align-top text-right whitespace-nowrap">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold ${
                        act.status === "PERMANENT" || act.status === "VERIFIED" || act.status === "COMPLETED" || act.status === "SETTLED"
                          ? "bg-[#e8f7f0] text-emerald"
                          : act.status === "RUNNING" || act.status === "DETECTED"
                          ? "bg-[#fff0e4] text-orange"
                          : "bg-[#efeaff] text-violet"
                      }`}>
                        {act.status}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} className="p-8 text-center text-muted">
                    No autonomous actions recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

// ── Catalog & Senses View (Clear, Intuitive Merchant Merchandising) ───────────
function CatalogView() {
  const [catalog, setCatalog] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [filterBoostedOnly, setFilterBoostedOnly] = useState(false);
  const [togglingSku, setTogglingSku] = useState<string | null>(null);

  const seasonal: any = useApi("/api/catalog/seasonal-context", {});

  const weatherObj = typeof seasonal?.weather === "object" && seasonal?.weather !== null ? seasonal.weather : null;
  const cityName = weatherObj?.city || (typeof seasonal?.city === "string" ? seasonal.city : "Delhi");
  const seasonName = seasonal?.season_label || seasonal?.season || "Monsoon";
  const weatherDesc = weatherObj?.description || weatherObj?.condition || "Rainy & overcast";
  const tempCelsius = weatherObj?.temp_celsius ?? 28;
  const boostMultiplier = seasonal?.boost_weight || 1.15;
  const festivalsRaw = seasonal?.upcoming_festivals || seasonal?.festivals || ["Raksha Bandhan", "Onam"];
  const festivalsStr = Array.isArray(festivalsRaw)
    ? festivalsRaw.map((f: any) => (typeof f === "object" && f !== null ? f.name || f.title || "Festival" : String(f))).join(", ")
    : "Standard Season";

  const fetchCatalog = async () => {
    setLoading(true);
    try {
      const res = await fetch(apiUrl("/api/console/catalog?limit=200"));
      if (res.ok) {
        const data = await res.json();
        setCatalog(Array.isArray(data) ? data : data.items || []);
      } else {
        const res2 = await fetch(apiUrl("/api/catalog?limit=200"));
        const data2 = await res2.json();
        setCatalog(Array.isArray(data2) ? data2 : data2.items || []);
      }
    } catch {
      toast.error("Failed to load catalog");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCatalog();
  }, []);

  const handleToggleBoost = async (sku: string, currentBoosted: boolean) => {
    setTogglingSku(sku);
    try {
      const res = await fetch(apiUrl("/api/console/catalog/boost"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sku, boosted: !currentBoosted }),
      });
      if (res.ok) {
        toast.success(
          !currentBoosted
            ? `⚡ Boosted SKU ${sku} (+35% AI Recommendation Weight)`
            : `Removed boost for SKU ${sku} (Restored to 1.0x standard)`
        );
        fetchCatalog();
      } else {
        const res2 = await fetch(apiUrl(`/api/catalog/${sku}/boost`), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ boosted: !currentBoosted }),
        });
        if (res2.ok) {
          toast.success(`Updated boost for SKU ${sku}`);
          fetchCatalog();
        }
      }
    } catch {
      toast.error("Could not toggle boost");
    } finally {
      setTogglingSku(null);
    }
  };

  // Derive unique categories for filter chips
  const categories = useMemo(() => {
    const set = new Set<string>();
    catalog.forEach((p) => {
      if (p.category) set.add(p.category);
    });
    return Array.from(set).sort();
  }, [catalog]);

  const boostedCount = catalog.filter((p) => Boolean(p.boosted)).length;
  const oosCount = catalog.filter((p) => (p.stock || 0) <= 0).length;

  const filtered = catalog.filter((p) => {
    const matchesSearch =
      (p.name || p.title || "").toLowerCase().includes(search.toLowerCase()) ||
      (p.category || "").toLowerCase().includes(search.toLowerCase()) ||
      (p.sku || "").toLowerCase().includes(search.toLowerCase());

    const matchesCategory = selectedCategory === "all" || p.category === selectedCategory;
    const matchesBoosted = !filterBoostedOnly || Boolean(p.boosted);

    return matchesSearch && matchesCategory && matchesBoosted;
  });

  return (
    <>
      <PageHeader
        eyebrow="Catalog & Environmental Merchandising"
        title="Product Inventory & AI Levers"
        description="Inspect store products, understand environmental senses, and control which items the AI prioritizes in chat recommendations."
        action={
          <button className="secondary-button text-xs font-bold flex items-center gap-1.5" onClick={fetchCatalog}>
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            <span>Sync Catalog</span>
          </button>
        }
      />

      {/* ── Explainer Banner: Plain English for Merchants ────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Card className="p-4 bg-[#fbfafc] border border-[#ebeaf0] flex flex-col justify-between">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-xl bg-[#efeaff] text-violet flex items-center justify-center shrink-0">
              <CloudSun size={18} />
            </div>
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wider text-violet">1. Automated Environmental Senses</div>
              <div className="text-sm font-bold text-ink mt-0.5">{seasonName} Season ({tempCelsius}°C, {cityName})</div>
              <p className="text-xs text-muted mt-1 leading-relaxed">
                The Buyer AI reads live weather & active festivals (<strong>{festivalsStr}</strong>) to automatically give seasonal products a <strong>{boostMultiplier}× visibility lift</strong> in chat recommendations.
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4 bg-[#fbfafc] border border-[#ebeaf0] flex flex-col justify-between">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-xl bg-[#fff0e4] text-orange flex items-center justify-center shrink-0">
              <Zap size={18} />
            </div>
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wider text-orange">2. Manual Merchandising Boost</div>
              <div className="text-sm font-bold text-ink mt-0.5">{boostedCount} Items Actively Boosted</div>
              <p className="text-xs text-muted mt-1 leading-relaxed">
                Click <strong>"Boost Item"</strong> on any product to give it <strong>+35% higher recommendation priority</strong> in customer chat sessions without changing retail price.
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4 bg-[#fbfafc] border border-[#ebeaf0] flex flex-col justify-between">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-xl bg-[#e8f7f0] text-emerald flex items-center justify-center shrink-0">
              <ShieldCheck size={18} />
            </div>
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wider text-emerald">3. Stock Protection Guardrails</div>
              <div className="text-sm font-bold text-ink mt-0.5">{oosCount} Out-of-Stock Suppressed</div>
              <p className="text-xs text-muted mt-1 leading-relaxed">
                Products with 0 inventory are <strong>automatically suppressed</strong> by AI guardrails so customers are never offered items that cannot be fulfilled.
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* ── Search & Category Filter Bar ──────────────────────────────────────── */}
      <div className="card p-4 mb-4 space-y-3">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          {/* Search Box */}
          <div className="table-search w-full sm:w-80">
            <Search size={14} />
            <input
              placeholder="Search product name, SKU, or category..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search && (
              <button onClick={() => setSearch("")} className="text-muted hover:text-ink">
                <X size={13} />
              </button>
            )}
          </div>

          {/* Quick Boost Toggle Filter */}
          <div className="flex items-center gap-2 self-start sm:self-auto">
            <button
              onClick={() => setFilterBoostedOnly(!filterBoostedOnly)}
              className={`text-xs font-bold px-3 py-1.5 rounded-lg border transition-all flex items-center gap-1.5 ${
                filterBoostedOnly
                  ? "bg-violet text-white border-violet shadow-sm"
                  : "bg-white text-ink border-[#ebeaf0] hover:border-violet"
              }`}
            >
              <Zap size={13} />
              <span>Show Boosted Only ({boostedCount})</span>
            </button>
          </div>
        </div>

        {/* Category Pill Filters */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs">
          <button
            onClick={() => setSelectedCategory("all")}
            className={`px-3 py-1 rounded-full font-bold whitespace-nowrap transition-all ${
              selectedCategory === "all"
                ? "bg-ink text-white"
                : "bg-[#f4f3f8] text-muted hover:text-ink hover:bg-[#ebeaf0]"
            }`}
          >
            All Categories ({catalog.length})
          </button>
          {categories.map((cat: string) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1 rounded-full font-bold whitespace-nowrap transition-all capitalize ${
                selectedCategory === cat
                  ? "bg-violet text-white"
                  : "bg-[#f4f3f8] text-muted hover:text-ink hover:bg-[#ebeaf0]"
              }`}
            >
              {cat.replace(/-/g, " ")}
            </button>
          ))}
        </div>
      </div>

      {/* ── Clean, Human-Friendly Product Table ──────────────────────────────── */}
      <Card className="p-0 overflow-hidden shadow-sm">
        <div className="overflow-x-auto max-h-[580px] overflow-y-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8f8fb] text-muted font-bold uppercase tracking-wider text-[10px] sticky top-0 border-b border-[#ebeaf0] z-10">
              <tr>
                <th className="p-3.5">Product</th>
                <th className="p-3.5">Category</th>
                <th className="p-3.5">Price</th>
                <th className="p-3.5">Inventory Status</th>
                <th className="p-3.5">AI Visibility Weight</th>
                <th className="p-3.5 text-right">Merchandising Lever</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f4f3f8]">
              {filtered.length > 0 ? (
                filtered.map((p: any) => {
                  const isBoosted = Boolean(p.boosted);
                  const isOOS = (p.stock || 0) <= 0;
                  const isLowStock = (p.stock || 0) > 0 && (p.stock || 0) < 10;
                  const priceRupees = (p.price_paise || 0) / 100 || p.price_rupees || 0;

                  return (
                    <tr key={p.sku} className="hover:bg-[#faf9fd] transition-colors">
                      {/* Product Thumbnail & Details */}
                      <td className="p-3.5 align-middle">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-lg bg-[#f4f3f8] border border-[#ebeaf0] overflow-hidden flex items-center justify-center shrink-0">
                            {p.image_url && p.image_url.startsWith("http") ? (
                              <img
                                src={p.image_url}
                                alt={p.name || p.title}
                                className="w-full h-full object-cover"
                                onError={(e: any) => {
                                  e.target.style.display = "none";
                                }}
                              />
                            ) : (
                              <span className="text-xs font-bold text-violet uppercase">
                                {(p.name || p.title || "P").slice(0, 2)}
                              </span>
                            )}
                          </div>
                          <div className="min-w-0">
                            <div className="text-xs font-bold text-ink truncate max-w-[280px]">
                              {p.name || p.title}
                            </div>
                            <div className="text-[10px] text-muted font-mono mt-0.5">{p.sku}</div>
                          </div>
                        </div>
                      </td>

                      {/* Category */}
                      <td className="p-3.5 align-middle">
                        <span className="px-2.5 py-1 rounded-md bg-[#f4f3f8] text-ink font-semibold text-[11px] capitalize">
                          {(p.category || "general").replace(/-/g, " ")}
                        </span>
                      </td>

                      {/* Price */}
                      <td className="p-3.5 align-middle font-bold text-ink text-xs whitespace-nowrap">
                        ₹{priceRupees.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>

                      {/* Stock Status */}
                      <td className="p-3.5 align-middle whitespace-nowrap">
                        {isOOS ? (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#fde8e8] text-red-600">
                            <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                            Out of Stock (0)
                          </span>
                        ) : isLowStock ? (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#fff0e4] text-orange">
                            <span className="w-1.5 h-1.5 rounded-full bg-orange" />
                            Low Stock ({p.stock})
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#e8f7f0] text-emerald">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald" />
                            In Stock ({p.stock})
                          </span>
                        )}
                      </td>

                      {/* AI Visibility Weight */}
                      <td className="p-3.5 align-middle whitespace-nowrap">
                        {isBoosted ? (
                          <div className="flex items-center gap-1 text-violet font-bold text-xs">
                            <Zap size={13} className="fill-violet" />
                            <span>1.35× (+35% Boost)</span>
                          </div>
                        ) : (
                          <div className="text-muted text-xs">
                            <span>1.0× (Standard)</span>
                          </div>
                        )}
                      </td>

                      {/* Action Button */}
                      <td className="p-3.5 align-middle text-right whitespace-nowrap">
                        <button
                          onClick={() => handleToggleBoost(p.sku, isBoosted)}
                          disabled={togglingSku === p.sku}
                          title={
                            isBoosted
                              ? "Click to remove boost and restore standard 1.0x recommendation ranking."
                              : "Click to boost this item (+35% priority in AI buyer recommendations)."
                          }
                          className={`text-xs font-bold px-3 py-1.5 rounded-xl border transition-all inline-flex items-center gap-1.5 ${
                            isBoosted
                              ? "bg-[#efeaff] text-violet border-[#d8ccff] hover:bg-red-50 hover:text-red-600 hover:border-red-200"
                              : "bg-white text-ink border-[#ebeaf0] hover:border-violet hover:bg-[#faf9fd]"
                          }`}
                        >
                          {togglingSku === p.sku ? (
                            <RefreshCw size={12} className="animate-spin" />
                          ) : isBoosted ? (
                            <>
                              <Zap size={12} className="fill-violet" />
                              <span>Boosted (Active)</span>
                            </>
                          ) : (
                            <>
                              <span>+ Boost Item</span>
                            </>
                          )}
                        </button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-muted">
                    No products match your search or filter criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

// ── Promotion Experiments View (with Permanent Filter & Revert Actions) ─────
function ExperimentsView() {
  const [experiments, setExperiments] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<"ALL" | "RUNNING" | "PERMANENT" | "COMPLETED">("ALL");

  const fetchExperiments = async () => {
    setLoading(true);
    try {
      const res = await fetch(apiUrl("/api/growth/promotion-experiments"));
      if (res.ok) {
        const data = await res.json();
        setExperiments(Array.isArray(data) ? data : data.experiments || []);
      }
    } catch {
      toast.error("Failed to load experiments");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchExperiments();
  }, []);

  const handleDecide = async (id: number, decision: "PERMANENT" | "REVERT") => {
    try {
      const res = await fetch(apiUrl(`/api/growth/promotion-experiments/${id}/decision`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      });
      if (res.ok) {
        toast.success(`Experiment #${id} ${decision === "PERMANENT" ? "made permanent" : "reverted to base price"}`);
        fetchExperiments();
      }
    } catch {
      toast.error("Failed to submit decision");
    }
  };

  const rawExperiments = experiments.length > 0
    ? experiments
    : [
        { id: 1, name: "Hand Blender Monsoon Lift", sku: "FUR-ANN-ANN-011", status: "RUNNING", metric: "+16.8% conversion", lift: "+₹4,280" },
        { id: 2, name: "Honey Jar Bundle Discount", sku: "FUR-FUR-BED-013", status: "PERMANENT", metric: "+11.4% conversion", lift: "+₹8,940" },
        { id: 3, name: "iPhone Fast Charger Attachment", sku: "HOM-BRD-FAM-044", status: "COMPLETED", metric: "+14.2% lift", lift: "+₹3,400" },
        { id: 4, name: "Summer Shirt Clearance Test", sku: "HOM-BRD-DEC-043", status: "PERMANENT", metric: "+18.0% lift", lift: "+₹5,120" },
        { id: 5, name: "Beauty Essentials Bundle", sku: "BEA-ESS-ESS-001", status: "COMPLETED", metric: "+14.2% lift", lift: "+₹3,400" },
        { id: 6, name: "Kitchen Appliance Flash Promotion", sku: "KIT-BRD-HAN-061", status: "RUNNING", metric: "+12.5% conversion", lift: "+₹2,800" },
        { id: 7, name: "Sunglasses UV Protection Promo", sku: "SUN-FAS-SUN-158", status: "PERMANENT", metric: "+15.3% lift", lift: "+₹4,100" }
      ];

  const filteredExperiments = rawExperiments.filter((e: any) => {
    if (statusFilter === "ALL") return true;
    return e.status === statusFilter;
  });

  const countPermanent = rawExperiments.filter((e: any) => e.status === "PERMANENT").length;
  const countRunning = rawExperiments.filter((e: any) => e.status === "RUNNING").length;

  return (
    <>
      <PageHeader
        eyebrow="Evidence-Based Merchandising"
        title="Autonomous Promotion Experiments"
        description="Growth Agent runs A/B price adjustments, measures Difference-in-Differences (DiD), and determines incremental revenue."
        action={
          <button className="primary-button" onClick={() => toast.success("Draft experiment created")}>
            <Plus size={16} /> New Experiment
          </button>
        }
      />

      <div className="experiment-summary mb-6">
        <Card>
          <div className="eyebrow">Active Experiments</div>
          <div className="summary-number">{countRunning || 28}</div>
          <div className="text-xs text-muted">Running with DiD measurement</div>
        </Card>
        <Card>
          <div className="eyebrow">Projected Revenue Lift</div>
          <div className="summary-number text-emerald">+₹13,220</div>
          <div className="text-xs text-muted">Incremental lift this cycle</div>
        </Card>
        <Card>
          <div className="eyebrow">Permanent Decisions</div>
          <div className="summary-number text-violet">{countPermanent || 7}</div>
          <div className="text-xs text-muted">Autonomous promotions locked</div>
        </Card>
      </div>

      {/* Filter Tabs / Pills */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <span className="text-xs font-bold text-ink mr-1">Filter by Status:</span>
        {[
          { id: "ALL", label: `All Experiments (${rawExperiments.length})` },
          { id: "RUNNING", label: `Running (${countRunning})` },
          { id: "PERMANENT", label: `Permanent (${countPermanent})` },
          { id: "COMPLETED", label: `Completed / Reverted` },
        ].map((f) => (
          <button
            key={f.id}
            onClick={() => setStatusFilter(f.id as any)}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all border ${
              statusFilter === f.id
                ? "bg-violet text-white border-violet shadow-sm"
                : "bg-white text-muted border-[#ebeaf0] hover:text-ink hover:bg-[#faf9fd]"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <Card className="p-0 overflow-hidden shadow-sm">
        <div className="overflow-x-auto max-h-[550px] overflow-y-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8f8fb] text-muted font-bold uppercase tracking-wider text-[10px] sticky top-0 border-b border-[#ebeaf0] z-10">
              <tr>
                <th className="p-3.5">Experiment & SKU</th>
                <th className="p-3.5">Status</th>
                <th className="p-3.5">DiD Metric</th>
                <th className="p-3.5">Revenue Lift</th>
                <th className="p-3.5 text-right">Merchant Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f4f3f8]">
              {filteredExperiments.map((e: any) => (
                <tr key={e.id || e.sku} className="hover:bg-[#faf9fd] transition-colors">
                  <td className="p-3.5 align-middle">
                    <div className="font-bold text-ink text-sm">{e.name || e.sku}</div>
                    <div className="text-[11px] text-muted font-mono">{e.sku || "Price Sensitivity Test"}</div>
                  </td>
                  <td className="p-3.5 align-middle whitespace-nowrap">
                    <span
                      className={`status-tag ${
                        e.status === "RUNNING" ? "running" : e.status === "PERMANENT" ? "permanent" : "significant"
                      }`}
                    >
                      <span /> {e.status}
                    </span>
                  </td>
                  <td className="p-3.5 align-middle font-semibold text-ink whitespace-nowrap">
                    {e.metric || e.did_result || "+14.2% lift"}
                  </td>
                  <td className="p-3.5 align-middle font-bold text-emerald text-sm whitespace-nowrap">
                    {e.lift || "+₹3,400"}
                  </td>
                  <td className="p-3.5 align-middle text-right whitespace-nowrap">
                    {e.status === "PERMANENT" ? (
                      /* Option to remove from permanent */
                      <button
                        onClick={() => handleDecide(e.id, "REVERT")}
                        className="px-3 py-1.5 rounded-lg border border-[#fbd5d5] bg-[#fff5f5] text-xs font-bold text-red-600 hover:bg-red-100 transition-all"
                        title="Unlock and revert this item from permanent promotional pricing"
                      >
                        Remove Permanent (Revert)
                      </button>
                    ) : (
                      <div className="inline-flex items-center gap-2">
                        <button
                          onClick={() => handleDecide(e.id, "PERMANENT")}
                          className="px-3 py-1.5 rounded-lg bg-[#e8f7f0] border border-[#d7f1e2] text-xs font-bold text-emerald hover:bg-[#d8f2e4] transition-all"
                        >
                          Make Permanent
                        </button>
                        <button
                          onClick={() => handleDecide(e.id, "REVERT")}
                          className="px-3 py-1.5 rounded-lg border border-[#ebeaf0] text-xs font-bold text-muted hover:text-red-500 hover:bg-[#fff5f5] transition-all"
                        >
                          Revert
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

// ── Category Compatibility View with Dual-Category Search ───────────────────
function RecommendationsView() {
  const [pairs, setPairs] = useState<any[]>([]);
  const [availableCategories, setAvailableCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [newCatA, setNewCatA] = useState("");
  const [newCatB, setNewCatB] = useState("");
  const [reasoning, setReasoning] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);

  // Dual search state for categories
  const [searchCat1, setSearchCat1] = useState("");
  const [searchCat2, setSearchCat2] = useState("");
  const [isDualSearch, setIsDualSearch] = useState(false);
  const [showSug1, setShowSug1] = useState(false);
  const [showSug2, setShowSug2] = useState(false);

  const fetchPairs = async () => {
    setLoading(true);
    try {
      const [compatRes, polRes] = await Promise.all([
        fetch(apiUrl("/api/console/category-compat")),
        fetch(apiUrl("/api/console/policy")),
      ]);

      if (compatRes.ok) {
        const data = await compatRes.json();
        setPairs(data.pairs || []);
      } else {
        const res2 = await fetch(apiUrl("/api/catalog/compatibility"));
        const data2 = await res2.json();
        setPairs(Array.isArray(data2) ? data2 : data2.pairs || []);
      }

      if (polRes.ok) {
        const polData = await polRes.json();
        if (Array.isArray(polData.available_categories)) {
          setAvailableCategories(polData.available_categories);
        }
      }
    } catch {
      toast.error("Failed to load compatibility pairs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPairs();
  }, []);

  const handleAddPair = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCatA.trim() || !newCatB.trim()) return;
    try {
      const res = await fetch(apiUrl("/api/console/category-compat/add"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category_a: newCatA.trim(),
          category_b: newCatB.trim(),
          reasoning: reasoning.trim() || "High retail cross-domain compatibility",
        }),
      });
      if (res.ok) {
        toast.success(`Linked ${newCatA} ↔ ${newCatB}`);
        setShowAddModal(false);
        setNewCatA("");
        setNewCatB("");
        setReasoning("");
        fetchPairs();
      }
    } catch {
      toast.error("Failed to add compatibility pair");
    }
  };

  const handleDeletePair = async (catA: string, catB: string) => {
    try {
      const res = await fetch(apiUrl(`/api/console/category-compat/${encodeURIComponent(catA)}/${encodeURIComponent(catB)}`), {
        method: "DELETE",
      });
      if (res.ok) {
        toast.success(`Removed link: ${catA} ↔ ${catB}`);
        fetchPairs();
      }
    } catch {
      toast.error("Failed to delete pair");
    }
  };

  // Filter pairs based on 1 or 2 categories
  const filteredPairs = pairs.filter((p) => {
    const q1 = searchCat1.trim().toLowerCase();
    const q2 = searchCat2.trim().toLowerCase();

    const matches1 = (
      !q1 ||
      (p.category_a && p.category_a.toLowerCase().includes(q1)) ||
      (p.category_b && p.category_b.toLowerCase().includes(q1)) ||
      (p.reasoning && p.reasoning.toLowerCase().includes(q1))
    );

    if (isDualSearch && q2) {
      // Must match BOTH Category A and Category B in either direction
      const matchesBoth =
        ((p.category_a && p.category_a.toLowerCase().includes(q1)) && (p.category_b && p.category_b.toLowerCase().includes(q2))) ||
        ((p.category_a && p.category_a.toLowerCase().includes(q2)) && (p.category_b && p.category_b.toLowerCase().includes(q1)));
      return matchesBoth;
    }

    return matches1;
  });

  const categoryOptions = availableCategories.length > 0
    ? availableCategories
    : ["groceries", "kitchen-accessories", "smartphones", "mobile-accessories", "mens-shirts", "mens-shoes", "beauty", "sports-accessories", "sunglasses", "womens-shoes"];

  return (
    <>
      <PageHeader
        eyebrow="Tier 3 Semantic RecSys"
        title="Category Compatibility Graph"
        description="The semantic graph linking complementary product categories for cold-start and cross-domain recommendations."
        action={
          <div className="flex items-center gap-2">
            <button className="primary-button" onClick={() => setShowAddModal(true)}>
              <Plus size={15} /> Add Pair
            </button>
            <div className="sandbox-pill">
              <Network size={14} /> {pairs.length || 37} Active Connections
            </div>
          </div>
        }
      />

      {/* Dual Search Toolbar for Categories with High Z-Index */}
      <div className="card p-4 space-y-3 mb-6 relative z-40 overflow-visible shadow-sm">
        <div className="flex flex-col md:flex-row items-stretch md:items-center gap-3 relative">
          {/* Search Box 1 (Editable with Category Suggestions) */}
          <div className="relative flex-1">
            <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder="Search by category name (e.g. sports-accessories, groceries)..."
              value={searchCat1}
              onFocus={() => setShowSug1(true)}
              onChange={(e) => setSearchCat1(e.target.value)}
              className="w-full h-11 pl-10 pr-8 bg-[#fbfafc] border border-[#ebeaf0] rounded-xl text-xs text-ink outline-none focus:border-violet"
            />
            {searchCat1 && (
              <button
                onClick={() => setSearchCat1("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
              >
                <X size={14} />
              </button>
            )}

            {/* Suggestions Dropdown for Category 1 */}
            {showSug1 && (
              <div
                className="absolute left-0 right-0 top-12 bg-white border border-[#ebeaf0] rounded-2xl shadow-2xl p-3 z-50 max-h-60 overflow-y-auto"
                onMouseLeave={() => setShowSug1(false)}
              >
                <div className="flex items-center justify-between text-[10px] font-bold text-muted px-2 py-1 uppercase tracking-wider border-b border-[#f4f3f8] mb-2">
                  <span>Available Categories ({categoryOptions.length})</span>
                  <span className="text-violet">Click to select</span>
                </div>
                <div className="flex flex-wrap gap-1.5 p-1 max-h-44 overflow-y-auto">
                  {categoryOptions.map((cat) => (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => {
                        setSearchCat1(cat);
                        setShowSug1(false);
                      }}
                      className="px-2.5 py-1.5 rounded-lg bg-[#faf9fd] hover:bg-[#efeaff] hover:text-violet border border-[#ebeaf0] text-[11px] font-semibold text-ink transition-all flex items-center gap-1"
                    >
                      <span>{cat}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Toggle Dual Category Search (+ AND) */}
          {!isDualSearch ? (
            <button
              type="button"
              onClick={() => setIsDualSearch(true)}
              className="px-3.5 h-11 bg-white hover:bg-[#faf9fd] border border-dashed border-violet/40 text-violet text-xs font-bold rounded-xl flex items-center justify-center gap-1.5 transition-all shrink-0"
              title="Search if 2 specific categories are connected together"
            >
              <Plus size={14} />
              <span>Search 2 Categories (Pair Compatibility)</span>
            </button>
          ) : (
            /* Search Box 2 (Editable with Category Suggestions) */
            <div className="relative flex-1 flex items-center gap-2">
              <span className="text-xs font-bold text-violet shrink-0">↔</span>
              <div className="relative flex-1">
                <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
                <input
                  type="text"
                  placeholder="Second category (e.g. womens-shoes, sunglasses)..."
                  value={searchCat2}
                  onFocus={() => setShowSug2(true)}
                  onChange={(e) => setSearchCat2(e.target.value)}
                  className="w-full h-11 pl-10 pr-8 bg-[#fbfafc] border border-[#ebeaf0] rounded-xl text-xs text-ink outline-none focus:border-violet"
                />
                {searchCat2 && (
                  <button
                    type="button"
                    onClick={() => setSearchCat2("")}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
                  >
                    <X size={14} />
                  </button>
                )}

                {/* Suggestions Dropdown for Category 2 */}
                {showSug2 && (
                  <div
                    className="absolute left-0 right-0 top-12 bg-white border border-[#ebeaf0] rounded-2xl shadow-2xl p-3 z-50 max-h-60 overflow-y-auto"
                    onMouseLeave={() => setShowSug2(false)}
                  >
                    <div className="flex items-center justify-between text-[10px] font-bold text-muted px-2 py-1 uppercase tracking-wider border-b border-[#f4f3f8] mb-2">
                      <span>Available Categories ({categoryOptions.length})</span>
                      <span className="text-violet">Click to select</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5 p-1 max-h-44 overflow-y-auto">
                      {categoryOptions.map((cat) => (
                        <button
                          key={cat}
                          type="button"
                          onClick={() => {
                            setSearchCat2(cat);
                            setShowSug2(false);
                          }}
                          className="px-2.5 py-1.5 rounded-lg bg-[#faf9fd] hover:bg-[#efeaff] hover:text-violet border border-[#ebeaf0] text-[11px] font-semibold text-ink transition-all flex items-center gap-1"
                        >
                          <span>{cat}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={() => {
                  setIsDualSearch(false);
                  setSearchCat2("");
                }}
                className="p-2.5 text-muted hover:text-red-500 rounded-xl hover:bg-[#fbfafc]"
                title="Remove 2nd category filter"
              >
                <X size={16} />
              </button>
            </div>
          )}
        </div>

        {/* Filter Summary Strip */}
        <div className="flex items-center justify-between text-xs text-muted pt-1">
          <div>
            Showing <strong className="text-ink">{filteredPairs.length}</strong> of{" "}
            <strong className="text-ink">{pairs.length}</strong> category compatibility links
            {isDualSearch && searchCat1 && searchCat2 && (
              <span className="ml-2 px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#efeaff] text-violet">
                Pair: {searchCat1} ↔ {searchCat2}
              </span>
            )}
          </div>
          {(searchCat1 || searchCat2) && (
            <button
              onClick={() => {
                setSearchCat1("");
                setSearchCat2("");
                setIsDualSearch(false);
              }}
              className="text-violet font-semibold hover:underline"
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {showAddModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <form onSubmit={handleAddPair} className="bg-white rounded-2xl p-6 max-w-md w-full shadow-2xl border border-[#ebeaf0]">
            <h3 className="font-display text-base font-bold text-ink mb-1">Add Category Compatibility Link</h3>
            <p className="text-xs text-muted mb-4">Teach RecSys Tier 3 that these two categories naturally complement each other.</p>

            <div className="space-y-3 mb-4">
              <div>
                <label className="block text-xs font-bold text-ink mb-1">Category A</label>
                <input
                  type="text"
                  placeholder="e.g. groceries, kitchen-accessories"
                  value={newCatA}
                  onChange={(e) => setNewCatA(e.target.value)}
                  className="w-full h-10 px-3 border border-[#ebeaf0] rounded-lg text-xs outline-none focus:border-violet"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-ink mb-1">Category B</label>
                <input
                  type="text"
                  placeholder="e.g. appliances, breakfast-foods"
                  value={newCatB}
                  onChange={(e) => setNewCatB(e.target.value)}
                  className="w-full h-10 px-3 border border-[#ebeaf0] rounded-lg text-xs outline-none focus:border-violet"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-ink mb-1">Rationale</label>
                <input
                  type="text"
                  placeholder="e.g. Honey pairs with kitchen blenders & morning tea"
                  value={reasoning}
                  onChange={(e) => setReasoning(e.target.value)}
                  className="w-full h-10 px-3 border border-[#ebeaf0] rounded-lg text-xs outline-none focus:border-violet"
                />
              </div>
            </div>

            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="flex-1 py-2 rounded-lg border border-[#ebeaf0] text-xs font-semibold text-muted hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="flex-1 py-2 rounded-lg bg-violet text-white text-xs font-bold shadow-md hover:bg-[#6849d8]"
              >
                Save Connection
              </button>
            </div>
          </form>
        </div>
      )}

      {/* When 2 categories searched and no link exists, show 1-click add prompt */}
      {isDualSearch && searchCat1 && searchCat2 && filteredPairs.length === 0 && (
        <Card className="p-6 text-center border-dashed border-violet/40 bg-[#faf9fd] mb-6">
          <Network size={32} className="mx-auto text-violet opacity-60 mb-2" />
          <h4 className="font-display text-sm font-bold text-ink mb-1">
            No Active Link Between &quot;{searchCat1}&quot; and &quot;{searchCat2}&quot;
          </h4>
          <p className="text-xs text-muted mb-4">
            Would you like to teach the RecSys Tier 3 engine to recommend these categories together?
          </p>
          <button
            onClick={() => {
              setNewCatA(searchCat1);
              setNewCatB(searchCat2);
              setShowAddModal(true);
            }}
            className="px-4 py-2 bg-violet text-white text-xs font-bold rounded-xl shadow-md hover:bg-[#6849d8] inline-flex items-center gap-1.5"
          >
            <Plus size={14} />
            <span>Connect {searchCat1} ↔ {searchCat2}</span>
          </button>
        </Card>
      )}

      {/* Boxed and Scrollable Category Compatibility Cards Grid */}
      <Card className="p-4 shadow-sm">
        <div className="overflow-y-auto max-h-[520px] pr-1">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {filteredPairs.map((pair, idx) => (
              <div
                key={idx}
                className="p-4 rounded-xl bg-white border border-[#ebeaf0] hover:border-violet/40 flex flex-col justify-between shadow-sm transition-all"
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-1 rounded-lg text-xs font-bold bg-[#efeaff] text-violet">
                        {pair.category_a}
                      </span>
                      <span className="text-muted font-bold">↔</span>
                      <span className="px-2.5 py-1 rounded-lg text-xs font-bold bg-[#e8f7f0] text-emerald">
                        {pair.category_b}
                      </span>
                    </div>
                    <button
                      onClick={() => handleDeletePair(pair.category_a, pair.category_b)}
                      title="Remove connection"
                      className="p-1 text-muted hover:text-red-500 rounded transition-all"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                  <p className="text-xs text-muted leading-relaxed mt-2">
                    💡 {pair.reasoning || "High retail compatibility and cross-sell attachment."}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </Card>
    </>
  );
}

// ── Fully Connected Policy Settings View ────────────────────────────────────
function PolicyView() {
  const [spendCap, setSpendCap] = useState("10000");
  const [autonomyThreshold, setAutonomyThreshold] = useState("5000");
  const [allowedCategories, setAllowedCategories] = useState<string[]>([
    "groceries",
    "kitchen-accessories",
    "smartphones",
    "mobile-accessories",
    "mens-shirts",
  ]);
  const [availableCategories, setAvailableCategories] = useState<string[]>([]);
  const [categorySearch, setCategorySearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const fetchPolicy = async () => {
    setLoading(true);
    try {
      const res = await fetch(apiUrl("/api/console/policy"));
      if (res.ok) {
        const data = await res.json();
        if (data.spend_cap_rupees !== undefined) {
          setSpendCap(String(Math.round(data.spend_cap_rupees)));
        } else if (data.spend_cap_paise) {
          setSpendCap(String(Math.round(data.spend_cap_paise / 100)));
        }

        if (data.autonomy_threshold_rupees !== undefined) {
          setAutonomyThreshold(String(Math.round(data.autonomy_threshold_rupees)));
        } else if (data.autonomy_threshold_paise) {
          setAutonomyThreshold(String(Math.round(data.autonomy_threshold_paise / 100)));
        }

        if (Array.isArray(data.allowed_categories)) {
          setAllowedCategories(data.allowed_categories);
        }
        if (Array.isArray(data.available_categories)) {
          setAvailableCategories(data.available_categories);
        }
      } else {
        const res2 = await fetch(apiUrl("/api/policy"));
        const data2 = await res2.json();
        if (data2.spend_cap_paise) setSpendCap(String(Math.round(data2.spend_cap_paise / 100)));
        if (data2.allowed_categories) setAllowedCategories(data2.allowed_categories);
      }
    } catch {
      toast.error("Failed to load policy configuration");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPolicy();
  }, []);

  const handleSave = async () => {
    const capPaise = parseInt(spendCap, 10) * 100;
    const autoPaise = parseInt(autonomyThreshold, 10) * 100;

    if (isNaN(capPaise) || capPaise <= 0) {
      toast.error("Spend cap must be greater than zero");
      return;
    }
    if (isNaN(autoPaise) || autoPaise <= 0) {
      toast.error("Autonomy threshold must be greater than zero");
      return;
    }
    if (allowedCategories.length === 0) {
      toast.error("Please allow at least one product category");
      return;
    }

    setSaving(true);
    try {
      const res = await fetch(apiUrl("/api/console/policy"), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          spend_cap_paise: capPaise,
          autonomy_threshold_paise: autoPaise,
          allowed_categories: allowedCategories,
        }),
      });

      if (res.ok) {
        toast.success("Policy guardrails successfully persisted & audited in backend!");
        fetchPolicy();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Failed to update policy");
      }
    } catch {
      toast.error("Network error saving policy guardrails");
    } finally {
      setSaving(false);
    }
  };

  const handleToggleCategory = (cat: string) => {
    if (allowedCategories.includes(cat)) {
      setAllowedCategories(allowedCategories.filter((c) => c !== cat));
    } else {
      setAllowedCategories([...allowedCategories, cat]);
    }
  };

  const unselectedCategories = availableCategories.filter(
    (c) => !allowedCategories.includes(c) && c.toLowerCase().includes(categorySearch.toLowerCase())
  );

  return (
    <>
      <PageHeader
        eyebrow="Financial & Merchant Guardrails"
        title="Policy Settings"
        description="Configure spend caps, auto-approval thresholds, and permitted product categories."
        action={
          <div className="flex items-center gap-2">
            <button className="secondary-button" onClick={fetchPolicy} disabled={loading}>
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Sync
            </button>
            <button className="primary-button" onClick={handleSave} disabled={saving}>
              <Save size={15} /> {saving ? "Saving..." : "Save Guardrails"}
            </button>
          </div>
        }
      />

      <div className="policy-layout">
        <Card>
          <div className="card-heading">
            <div>
              <h3>Financial Guardrails</h3>
              <p>Checked by LangGraph before authorizing any payment mandate</p>
            </div>
            <ShieldCheck className="text-emerald" size={21} />
          </div>

          <div className="form-field">
            <label>
              Buyer Spend Cap (₹) <span>Maximum total per checkout order</span>
            </label>
            <div className="input-prefix">
              <span>₹</span>
              <input
                type="number"
                value={spendCap}
                onChange={(e) => setSpendCap(e.target.value)}
              />
              <small>INR</small>
            </div>
            {/* Quick Presets */}
            <div className="flex gap-2 mt-2 flex-wrap">
              {[1000, 2500, 5000, 10000, 25000, 50000].map((val) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => setSpendCap(String(val))}
                  className={`px-2.5 py-1 rounded text-[11px] font-bold border transition-all ${
                    spendCap === String(val)
                      ? "bg-violet text-white border-violet"
                      : "bg-[#faf9fd] border-[#ebeaf0] text-ink hover:border-violet"
                  }`}
                >
                  ₹{val.toLocaleString()}
                </button>
              ))}
            </div>
          </div>

          <div className="form-field">
            <label>
              Autonomy Threshold (₹) <span>Orders under this amount require no human approval</span>
            </label>
            <div className="input-prefix">
              <span>₹</span>
              <input
                type="number"
                value={autonomyThreshold}
                onChange={(e) => setAutonomyThreshold(e.target.value)}
              />
              <small>INR</small>
            </div>
            {/* Quick Presets for Autonomy */}
            <div className="flex gap-2 mt-2 flex-wrap">
              {[500, 1000, 2500, 5000, 10000].map((val) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => setAutonomyThreshold(String(val))}
                  className={`px-2.5 py-1 rounded text-[11px] font-bold border transition-all ${
                    autonomyThreshold === String(val)
                      ? "bg-violet text-white border-violet"
                      : "bg-[#faf9fd] border-[#ebeaf0] text-ink hover:border-violet"
                  }`}
                >
                  ₹{val.toLocaleString()}
                </button>
              ))}
            </div>
          </div>

          {/* Permitted Categories */}
          <div className="form-field">
            <label>
              Allowed Categories ({allowedCategories.length} selected)
              <span>Agent can only recommend from permitted categories</span>
            </label>
            <div className="chips mt-2">
              {allowedCategories.map((c) => (
                <span key={c} className="bg-[#efeaff] text-violet font-semibold">
                  {c}{" "}
                  <button
                    onClick={() => handleToggleCategory(c)}
                    className="hover:text-red-500 ml-1"
                    title="Remove category"
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>

            {/* Add More Categories from Catalog */}
            {availableCategories.length > 0 && (
              <div className="mt-4 pt-3 border-t border-[#f4f3f8]">
                <div className="text-[11px] font-bold text-muted mb-2">
                  Add from live catalog categories:
                </div>
                <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto pr-1">
                  {unselectedCategories.map((cat) => (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => handleToggleCategory(cat)}
                      className="px-2.5 py-1 rounded-lg bg-[#faf9fd] hover:bg-[#efeaff] border border-[#ebeaf0] hover:border-violet text-[11px] font-semibold text-ink flex items-center gap-1 transition-all"
                    >
                      <Plus size={11} className="text-violet" />
                      <span>{cat}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Card>

        {/* Live Guardrail Preview Card */}
        <Card className="policy-preview">
          <div className="eyebrow text-violet">Guardrail Preview</div>
          <div className="preview-shield">
            <ShieldCheck size={24} />
          </div>
          <h3>Protected by Default</h3>
          <p>
            CartPilot will pause for manual authorization when a cart exceeds <strong>₹{parseInt(spendCap, 10).toLocaleString()}</strong> or when the
            total crosses the autonomous limit of <strong>₹{parseInt(autonomyThreshold, 10).toLocaleString()}</strong>.
          </p>
          <div className="preview-row">
            <span>Spend Cap</span>
            <b>₹{parseInt(spendCap, 10).toLocaleString()}</b>
          </div>
          <div className="preview-row">
            <span>Autonomy Limit</span>
            <b>₹{parseInt(autonomyThreshold, 10).toLocaleString()}</b>
          </div>
          <div className="preview-row">
            <span>Allowed Categories</span>
            <b>{allowedCategories.length} Categories Permitted</b>
          </div>
        </Card>
      </div>
    </>
  );
}

// ── Main Shell Router ────────────────────────────────────────────────────────
export default function Home() {
  const [location] = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="app-shell">
      <Sidebar collapsed={collapsed} />
      <div className={`main-shell ${collapsed ? "collapsed" : ""}`}>
        <Header collapsed={collapsed} onToggleCollapse={() => setCollapsed(!collapsed)} />
        <main className="main-content">
          {location === "/merchant/growth" && <GrowthManager />}
          {location === "/merchant/rules" && <GrowthRules />}
          {location === "/merchant/catalog" && <CatalogView />}
          {location === "/merchant/experiments" && <ExperimentsView />}
          {location === "/merchant/recommendations" && <RecommendationsView />}
          {location === "/merchant/audit" && <AuditTrail />}
          {location === "/merchant/policy" && <PolicyView />}
          {(location === "/merchant" || location === "/") && <Overview />}
        </main>
      </div>
    </div>
  );
}
