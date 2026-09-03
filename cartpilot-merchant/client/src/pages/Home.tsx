import { useEffect, useState, useRef, useMemo } from "react";
import { Link, useLocation } from "wouter";
import { useAuth } from "../contexts/AuthContext";
import {
  Activity, ArrowUpRight, BarChart3, Bell, Bot, Boxes, ChevronRight, CircleHelp,
  CloudSun, Command, Compass, CreditCard, FlaskConical, Gauge, LayoutDashboard,
  Network, Plus, Save, Search, Settings2, ShieldCheck,
  ShoppingCart, Store, Sun, TrendingUp, Users, X, Zap, LogOut, CheckCircle, Trash2,
  Lock, RefreshCw, Play, Sliders, FileText, Download, ChevronDown, Check, AlertCircle,
  PanelLeftClose, PanelLeftOpen, Clock, ArrowRight, CloudRain, Cloud, Calendar, Sparkles
} from "lucide-react";
import { toast } from "sonner";
import GrowthManager from "./merchant/GrowthManager";
import GrowthRules from "./merchant/GrowthRules";
import AuditTrail from "./merchant/AuditTrail";
import CampaignStudio from "./merchant/CampaignStudio";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface NavItem {
  label: string;
  path: string;
  icon: any;
  group: string;
  badge?: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Overview", path: "/merchant", icon: LayoutDashboard, group: "Command Center" },
  { label: "Manager", path: "/merchant/growth", icon: TrendingUp, group: "Autonomous Growth" },
  { label: "Campaign Studio", path: "/merchant/campaigns", icon: Calendar, group: "Autonomous Growth" },
  { label: "Cross-Sell Rules", path: "/merchant/rules", icon: SparklesIcon, group: "Autonomous Growth" },
  { label: "Promotions", path: "/merchant/experiments", icon: FlaskConical, group: "Autonomous Growth" },
  { label: "Product Catalog", path: "/merchant/catalog", icon: Boxes, group: "Store Management" },
  { label: "Category Management", path: "/merchant/categories", icon: Network, group: "Store Management" },
  { label: "Order Ledger", path: "/merchant/audit", icon: ShieldCheck, group: "Store Management" },
  { label: "Safety Guardrails", path: "/merchant/policy", icon: Sliders, group: "Store Management" },
];

function SparklesIcon(props: any) {
  return <Zap {...props} />;
}

function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

function useApi<T>(path: string, fallback: T, key?: number) {
  const [data, setData] = useState<T>(fallback);
  useEffect(() => {
    fetch(apiUrl(path))
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setData)
      .catch(() => setData(fallback));
  }, [path, key]);
  return data;
}

// ── Sidebar with Integrated Morphing Collapse / Expand Button ──────────────
function Sidebar({ collapsed, onToggleCollapse }: { collapsed: boolean; onToggleCollapse: () => void }) {
  const [location] = useLocation();
  const { user } = useAuth();
  const [showHelpModal, setShowHelpModal] = useState(false);

  return (
    <>
      <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
        {/* Brand Header with Integrated Smooth Collapse / Expand Button */}
        <div
          className={`h-[72px] flex items-center border-b border-[#f4f3f8] transition-all duration-300 select-none ${
            collapsed ? "justify-center px-0" : "justify-between px-4"
          }`}
        >
          {!collapsed ? (
            <>
              <div className="flex items-center gap-2.5 min-w-0">
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center shadow-xs shrink-0 transition-transform duration-300"
                  style={{ background: "#115e59", color: "#ffffff" }}
                >
                  <ShoppingCart size={16} strokeWidth={2.4} color="#ffffff" />
                </div>
                <span className="font-display text-[18px] font-bold tracking-tight text-ink whitespace-nowrap overflow-hidden transition-opacity duration-200">
                  CartPilot
                </span>
              </div>
              <button
                onClick={onToggleCollapse}
                className="w-8 h-8 rounded-lg text-muted hover:text-ink hover:bg-[#f4f3f8] flex items-center justify-center transition-all cursor-pointer"
                title="Collapse sidebar"
              >
                <PanelLeftClose size={17} />
              </button>
            </>
          ) : (
            <button
              onClick={onToggleCollapse}
              className="group relative w-10 h-10 rounded-xl bg-[#faf9fd] hover:bg-[#efeaff] border border-[#efedf5] hover:border-violet/40 flex items-center justify-center transition-all duration-300 shadow-2xs cursor-pointer"
              title="Expand sidebar"
            >
              {/* Smooth cross-fade & scale morph between Cart and Expand Panel icons */}
              <div className="relative w-5 h-5 flex items-center justify-center">
                <ShoppingCart
                  size={17}
                  strokeWidth={2.4}
                  className="text-[#115e59] absolute transition-all duration-300 ease-out group-hover:opacity-0 group-hover:scale-75 group-hover:rotate-[-12deg]"
                />
                <PanelLeftOpen
                  size={18}
                  className="text-violet absolute transition-all duration-300 ease-out opacity-0 scale-75 group-hover:opacity-100 group-hover:scale-100 group-hover:rotate-0"
                />
              </div>
            </button>
          )}
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
              className="w-10 h-10 mx-auto rounded-xl bg-[#faf9fd] hover:bg-[#efeaff] border border-[#efedf5] hover:border-violet/30 text-violet flex items-center justify-center transition-all shadow-sm cursor-pointer"
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
function Header() {
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

      <div className="ml-auto flex items-center gap-3">
        {/* Robot Agent Autonomy Dropdown Button */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 px-3 py-1.5 bg-white hover:bg-[#faf9fd] border border-[#ebeaf0] rounded-xl text-xs font-bold text-ink shadow-sm transition-all cursor-pointer"
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
                  className="w-full py-2 bg-violet text-white text-xs font-bold rounded-lg shadow-sm hover:bg-[#6849d8] flex items-center justify-center gap-1.5 transition-all cursor-pointer"
                >
                  <RefreshCw size={13} className={runningWorker ? "animate-spin" : ""} />
                  <span>{runningWorker ? "Optimizing..." : "Run Optimization Cycle Now"}</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Profile Avatar & Logout */}
        <div className="profile pl-2 border-l border-[#ebeaf0]">
          <div className="profile-avatar">
            {((!user?.name?.trim() || user.name.trim() === "Store Manager") ? "SO" : user.name.trim().split(" ").filter(Boolean).map(w => w[0]).join("").slice(0, 2).toUpperCase()) || "SO"}
          </div>
          <span className="hidden sm:inline text-xs font-semibold text-ink">
            {(!user?.name?.trim() || user.name.trim() === "Store Manager") ? "Store Owner" : user.name.trim()}
          </span>
          <button
            onClick={() => {
              logout();
              setLocation("/auth");
            }}
            title="Sign Out"
            className="p-1.5 text-muted hover:text-ink hover:bg-[#f4f3f8] rounded-lg transition-all ml-1 cursor-pointer"
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
  eyebrow?: string;
  title?: string;
  description?: string;
  action?: React.ReactNode;
}) {
  if (!title && !eyebrow && !description && !action) return null;
  return (
    <div className={`page-header ${!title ? "justify-end mb-4" : ""}`}>
      {title && (
        <div>
          {eyebrow && <div className="eyebrow text-violet mb-2">{eyebrow}</div>}
          <h1>{title}</h1>
          {description && <p>{description}</p>}
        </div>
      )}
      {action && <div className="flex items-center gap-2">{action}</div>}
    </div>
  );
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`card ${className}`}>{children}</div>;
}

// ── Modern KPI Stat Card (Clean, Minimal Without Icons) ─────────────────────
function Stat({ label, value, delta }: { label: string; value: React.ReactNode; delta?: string; [key: string]: any }) {
  return (
    <Card className="stat-card">
      <div>
        <div className="text-[12px] font-bold text-muted uppercase tracking-wider">{label}</div>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="font-display text-[27px] font-bold tracking-tight text-ink">{value}</span>
          {delta && <span className="text-[11px] font-bold text-emerald">{delta}</span>}
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

type TimeframeOption = "3M" | "6M" | "1Y" | "ALL";

const DATA_3M: ChartPoint[] = [
  { date: "Jun 15", orders: 185, crossSells: 68, revenueRupees: 14200 },
  { date: "Jul 01", orders: 240, crossSells: 95, revenueRupees: 19800 },
  { date: "Jul 15", orders: 310, crossSells: 124, revenueRupees: 24600 },
  { date: "Aug 01", orders: 395, crossSells: 162, revenueRupees: 31500 },
  { date: "Aug 15", orders: 490, crossSells: 205, revenueRupees: 39800 },
  { date: "Aug 25", orders: 570, crossSells: 245, revenueRupees: 46500 },
  { date: "Sep 03", orders: 642, crossSells: 289, revenueRupees: 52800 },
];

const DATA_6M: ChartPoint[] = [
  { date: "Apr '26", orders: 95, crossSells: 32, revenueRupees: 7400 },
  { date: "May '26", orders: 155, crossSells: 54, revenueRupees: 11900 },
  { date: "Jun '26", orders: 230, crossSells: 86, revenueRupees: 17800 },
  { date: "Jul '26", orders: 345, crossSells: 138, revenueRupees: 27500 },
  { date: "Aug '26", orders: 510, crossSells: 218, revenueRupees: 41200 },
  { date: "Sep '26", orders: 642, crossSells: 289, revenueRupees: 52800 },
];

const DATA_1Y: ChartPoint[] = [
  { date: "Oct '25", orders: 42, crossSells: 14, revenueRupees: 3200 },
  { date: "Dec '25", orders: 110, crossSells: 41, revenueRupees: 8900 },
  { date: "Feb '26", orders: 180, crossSells: 65, revenueRupees: 14100 },
  { date: "Apr '26", orders: 275, crossSells: 104, revenueRupees: 21900 },
  { date: "Jun '26", orders: 410, crossSells: 168, revenueRupees: 33400 },
  { date: "Aug '26", orders: 580, crossSells: 252, revenueRupees: 47600 },
  { date: "Sep '26", orders: 642, crossSells: 289, revenueRupees: 52800 },
];

const DATA_ALL: ChartPoint[] = [
  { date: "Q1 '25", orders: 28, crossSells: 8, revenueRupees: 2100 },
  { date: "Q2 '25", orders: 75, crossSells: 24, revenueRupees: 5900 },
  { date: "Q3 '25", orders: 160, crossSells: 58, revenueRupees: 12800 },
  { date: "Q4 '25", orders: 290, crossSells: 112, revenueRupees: 23500 },
  { date: "Q1 '26", orders: 430, crossSells: 176, revenueRupees: 34900 },
  { date: "Q2 '26", orders: 570, crossSells: 245, revenueRupees: 46200 },
  { date: "Whole", orders: 642, crossSells: 289, revenueRupees: 52800 },
];

function InteractiveCommerceChart() {
  const [timeframe, setTimeframe] = useState<TimeframeOption>("3M");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [showOrders, setShowOrders] = useState(true);
  const [showCrossSells, setShowCrossSells] = useState(true);
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const dropdownRef = useRef<HTMLDivElement>(null);
  const data =
    timeframe === "3M"
      ? DATA_3M
      : timeframe === "6M"
      ? DATA_6M
      : timeframe === "1Y"
      ? DATA_1Y
      : DATA_ALL;

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

  const timeframeLabel =
    timeframe === "3M"
      ? "Last 3 Months"
      : timeframe === "6M"
      ? "Last 6 Months"
      : timeframe === "1Y"
      ? "Last 1 Year"
      : "Whole (All Time)";

  return (
    <Card className="chart-card">
      <div className="card-heading flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3>AI Commerce Activity</h3>
        </div>

        {/* Timeframe Dropdown Menu */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 px-3 py-1.5 bg-[#f4f3f8] hover:bg-[#eae8f2] border border-[#ebeaf0] rounded-xl text-xs font-bold text-ink transition-all shadow-sm"
          >
            <span>{timeframeLabel}</span>
            <ChevronDown size={14} className={`text-muted transition-transform ${dropdownOpen ? "rotate-180" : ""}`} />
          </button>

          {dropdownOpen && (
            <div className="absolute right-0 mt-1.5 w-44 bg-white border border-[#ebeaf0] rounded-xl shadow-lg p-1 z-30">
              {[
                { id: "3M", label: "3 Months" },
                { id: "6M", label: "6 Months" },
                { id: "1Y", label: "1 Year" },
                { id: "ALL", label: "Whole (All Time)" },
              ].map((t) => (
                <button
                  key={t.id}
                  onClick={() => {
                    setTimeframe(t.id as TimeframeOption);
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

function WeatherIcon({ condition, className = "" }: { condition?: string; className?: string }) {
  const cond = (condition || "").toLowerCase();
  if (cond.includes("rain") || cond.includes("drizzle") || cond.includes("shower") || cond.includes("thunder")) {
    return <CloudRain className={className} size={30} />;
  }
  if (cond.includes("cloud") || cond.includes("overcast")) {
    return <Cloud className={className} size={30} />;
  }
  if (cond.includes("clear") || cond.includes("sun") || cond.includes("hot")) {
    return <Sun className={className} size={30} />;
  }
  return <CloudSun className={className} size={30} />;
}

// ── Searchable Multi-Select Category Dropdown ────────────────────────────────
function CategoryMultiSelectDropdown({
  allCategories,
  selectedCategories,
  onChange,
  placeholder = "Select categories (or leave empty for AI auto-match)...",
}: {
  allCategories: string[];
  selectedCategories: string[];
  onChange: (cats: string[]) => void;
  placeholder?: string;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  const filtered = allCategories.filter((c) =>
    c.toLowerCase().includes(search.toLowerCase())
  );

  const toggleCategory = (cat: string) => {
    if (selectedCategories.includes(cat)) {
      onChange(selectedCategories.filter((c) => c !== cat));
    } else {
      onChange([...selectedCategories, cat]);
    }
  };

  const handleSelectAll = () => {
    onChange([...allCategories]);
  };

  const handleClearAll = () => {
    onChange([]);
  };

  return (
    <div className="relative" ref={containerRef}>
      {/* Trigger Button */}
      <div
        onClick={() => setIsOpen(!isOpen)}
        className="min-h-[38px] p-2 bg-white border border-[#ebeaf0] rounded-xl text-xs flex items-center justify-between cursor-pointer hover:border-violet transition-colors"
      >
        <div className="flex flex-wrap gap-1 items-center flex-1 mr-2">
          {selectedCategories.length === 0 ? (
            <span className="text-muted text-[11px]">{placeholder}</span>
          ) : (
            selectedCategories.map((cat) => (
              <span
                key={cat}
                className="px-2 py-0.5 rounded-md bg-[#efeaff] text-violet text-[11px] font-medium flex items-center gap-1 border border-violet/20"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleCategory(cat);
                }}
              >
                <span>{cat}</span>
                <X size={11} className="hover:text-rose-600" />
              </span>
            ))
          )}
        </div>
        <div className="flex items-center gap-1.5 text-muted shrink-0">
          <span className="text-[10px] font-bold bg-[#f4f3f8] px-1.5 py-0.5 rounded">
            {selectedCategories.length} selected
          </span>
          <ChevronDown size={14} className={`transition-transform ${isOpen ? "rotate-180" : ""}`} />
        </div>
      </div>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute top-full left-0 right-0 mt-1.5 bg-white rounded-xl shadow-xl border border-[#ebeaf0] p-3 z-30 space-y-2 animate-in fade-in zoom-in-95 duration-150">
          {/* Search Input */}
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder="Filter categories (e.g. shoes, groceries, dresses)..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full h-8 pl-8 pr-2.5 bg-[#f8f8fb] border border-[#ebeaf0] rounded-lg text-xs outline-none focus:border-violet"
              onClick={(e) => e.stopPropagation()}
            />
          </div>

          {/* Quick Actions */}
          <div className="flex items-center justify-between px-1 text-[11px] text-muted border-b border-[#f4f3f8] pb-1.5">
            <span>{filtered.length} categories available</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleSelectAll();
                }}
                className="text-violet font-bold hover:underline"
              >
                Select All
              </button>
              <span>·</span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleClearAll();
                }}
                className="text-rose-500 font-bold hover:underline"
              >
                Clear
              </button>
            </div>
          </div>

          {/* Categories Checkboxes List */}
          <div className="max-h-48 overflow-y-auto space-y-1 pr-1">
            {filtered.length === 0 ? (
              <div className="text-center py-4 text-xs text-muted">No categories matching "{search}"</div>
            ) : (
              filtered.map((cat) => {
                const isChecked = selectedCategories.includes(cat);
                return (
                  <label
                    key={cat}
                    onClick={(e) => e.stopPropagation()}
                    className={`flex items-center justify-between p-1.5 rounded-lg text-xs cursor-pointer transition-colors ${
                      isChecked ? "bg-[#f4f0ff] text-violet font-semibold" : "hover:bg-[#faf9fd] text-ink"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleCategory(cat)}
                        className="rounded border-[#ebeaf0] text-violet focus:ring-violet"
                      />
                      <span>{cat}</span>
                    </div>
                    {isChecked && <Check size={12} className="text-violet" />}
                  </label>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Festive & Seasonal Merchandising Studio Modal ────────────────────────────
function MerchandisingStudioModal({
  isOpen,
  onClose,
  onUpdated,
}: {
  isOpen: boolean;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const [festivals, setFestivals] = useState<any[]>([]);
  const [allCategories, setAllCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [recalculating, setRecalculating] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingFestId, setEditingFestId] = useState<number | null>(null);
  const [editingCustomCats, setEditingCustomCats] = useState<string[]>([]);

  // New festival form state
  const [newName, setNewName] = useState("");
  const [newMonth, setNewMonth] = useState(new Date().getMonth() + 1);
  const [newDay, setNewDay] = useState(new Date().getDate());
  const [newDuration, setNewDuration] = useState(7);
  const [newLift, setNewLift] = useState(1.35);
  const [newThemesStr, setNewThemesStr] = useState("mega_sale, seasonal_promotions, trending");
  const [newSelectedCategories, setNewSelectedCategories] = useState<string[]>([]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [festRes, catRes] = await Promise.all([
        fetch(apiUrl("/api/growth/festivals")),
        fetch(apiUrl("/api/console/catalog?limit=500")),
      ]);

      const festData = festRes.ok ? await festRes.json() : { festivals: [] };
      setFestivals(festData.festivals || []);

      const catData = catRes.ok ? await catRes.json() : {};
      const items = Array.isArray(catData) ? catData : (Array.isArray(catData?.items) ? catData.items : []);
      const distinctCats = Array.from(new Set(items.map((i: any) => i.category).filter(Boolean))).sort() as string[];
      setAllCategories(distinctCats.length > 0 ? distinctCats : [
        "beauty", "clearance", "education", "electronics", "fragrances", "furniture", "gift-cards",
        "groceries", "home-decoration", "kitchen-accessories", "laptops", "mens-shirts", "mens-shoes",
        "mens-watches", "mobile-accessories", "motorcycle", "skin-care", "smartphones", "sports-accessories",
        "sunglasses", "tablets", "tops", "vehicle", "womens-bags", "womens-dresses", "womens-jewellery",
        "womens-shoes", "womens-watches"
      ]);
    } catch {
      toast.error("Failed to load festival calendar and categories");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen]);

  const handleToggleActive = async (fest: any) => {
    const isCurrentlyActive = fest.is_active !== 0 && fest.status !== "inactive";
    const nextActive = isCurrentlyActive ? 0 : 1;
    try {
      const res = await fetch(apiUrl(`/api/growth/festivals/${fest.id}`), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: nextActive }),
      });
      if (res.ok) {
        toast.success(`Updated ${fest.name} status`);
        loadData();
        onUpdated();
      }
    } catch {
      toast.error("Failed to update festival status");
    }
  };

  const handleSaveCustomCategories = async (festId: number, cats: string[]) => {
    try {
      const res = await fetch(apiUrl(`/api/growth/festivals/${festId}`), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ custom_categories: cats.length > 0 ? cats : null }),
      });
      if (res.ok) {
        toast.success(cats.length > 0 ? `Saved ${cats.length} custom categories` : "Reset to AI auto-match");
        setEditingFestId(null);
        loadData();
        onUpdated();
      }
    } catch {
      toast.error("Failed to update categories");
    }
  };

  const handleRecalculate = async () => {
    try {
      setRecalculating(true);
      const res = await fetch(apiUrl("/api/growth/festivals/recalculate"), {
        method: "POST",
      });
      if (res.ok) {
        toast.success("Environmental & seasonal boosts recalculated across catalog!");
        loadData();
        onUpdated();
      }
    } catch {
      toast.error("Failed to recalculate merchandising boosts");
    } finally {
      setRecalculating(false);
    }
  };

  const handleCreateFestival = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) {
      toast.error("Please enter a campaign name");
      return;
    }
    try {
      const themes = newThemesStr
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      const res = await fetch(apiUrl("/api/growth/festivals"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName.trim(),
          month: Number(newMonth),
          day: Number(newDay),
          duration_days: Number(newDuration),
          lift_multiplier: Number(newLift),
          themes,
          custom_categories: newSelectedCategories.length > 0 ? newSelectedCategories : null,
          is_active: 1,
        }),
      });
      if (res.ok) {
        toast.success(`Created campaign "${newName}"`);
        setShowAddForm(false);
        setNewName("");
        setNewSelectedCategories([]);
        loadData();
        onUpdated();
      }
    } catch {
      toast.error("Failed to create campaign");
    }
  };

  const handleDelete = async (festId: number) => {
    if (!confirm("Are you sure you want to remove this campaign?")) return;
    try {
      const res = await fetch(apiUrl(`/api/growth/festivals/${festId}`), {
        method: "DELETE",
      });
      if (res.ok) {
        toast.success("Campaign deleted");
        loadData();
        onUpdated();
      }
    } catch {
      toast.error("Failed to delete campaign");
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl max-w-3xl w-full shadow-2xl border border-[#ebeaf0] flex flex-col max-h-[90vh] overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Modal Header */}
        <div className="p-5 border-b border-[#f4f3f8] flex items-center justify-between bg-[#faf9fd]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#efeaff] text-violet flex items-center justify-center shadow-sm">
              <Sparkles size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-display text-base font-bold text-ink">
                  Merchandising & Campaign Studio
                </h3>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-violet/10 text-violet">
                  Universal Dense MiniLM Engine
                </span>
              </div>
              <p className="text-xs text-muted">
                Control active cultural festivals, custom sale events, and AI inventory theme affinities.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-xl bg-white border border-[#ebeaf0] text-muted hover:text-ink flex items-center justify-center transition-colors"
          >
            <X size={15} />
          </button>
        </div>

        {/* Modal Actions Bar */}
        <div className="p-4 border-b border-[#f4f3f8] flex flex-wrap items-center justify-between gap-3 bg-white">
          <div className="flex items-center gap-2 text-xs text-muted">
            <Calendar size={14} className="text-violet" />
            <span>
              <strong>{festivals.length}</strong> Configured Annual Demand Events · <strong>{allCategories.length}</strong> Store Categories
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowAddForm(!showAddForm)}
              className="px-3 py-1.5 rounded-xl border border-violet/30 bg-[#f8f6ff] text-violet text-xs font-bold hover:bg-violet/10 flex items-center gap-1.5 transition-colors"
            >
              <Plus size={13} />
              <span>{showAddForm ? "Close Form" : "New Sale Campaign"}</span>
            </button>
            <button
              type="button"
              disabled={recalculating}
              onClick={handleRecalculate}
              className="px-3 py-1.5 rounded-xl bg-violet text-white text-xs font-bold hover:bg-violet/90 flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              <RefreshCw size={13} className={recalculating ? "animate-spin" : ""} />
              <span>{recalculating ? "Recalculating..." : "Recalculate Store Lifts"}</span>
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-5 overflow-y-auto space-y-4 flex-1">
          {/* Inline Add Form */}
          {showAddForm && (
            <form
              onSubmit={handleCreateFestival}
              className="p-4 rounded-xl bg-[#faf9fd] border border-violet/20 space-y-3.5 animate-in fade-in slide-in-from-top-2"
            >
              <div className="flex items-center justify-between pb-2 border-b border-[#ebeaf0]">
                <h4 className="font-display text-xs font-bold text-ink flex items-center gap-1.5">
                  <Plus size={13} className="text-violet" />
                  Create Custom Store Promotion / Campaign
                </h4>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-bold text-ink mb-1">
                    Campaign Name <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Monsoon Clearance Sale"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    className="w-full h-8 px-2.5 border border-[#ebeaf0] rounded-lg text-xs outline-none focus:border-violet bg-white"
                    required
                  />
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-[11px] font-bold text-ink mb-1">Month (1-12)</label>
                    <input
                      type="number"
                      min="1"
                      max="12"
                      value={newMonth}
                      onChange={(e) => setNewMonth(Number(e.target.value))}
                      className="w-full h-8 px-2.5 border border-[#ebeaf0] rounded-lg text-xs outline-none focus:border-violet bg-white"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold text-ink mb-1">Day (1-31)</label>
                    <input
                      type="number"
                      min="1"
                      max="31"
                      value={newDay}
                      onChange={(e) => setNewDay(Number(e.target.value))}
                      className="w-full h-8 px-2.5 border border-[#ebeaf0] rounded-lg text-xs outline-none focus:border-violet bg-white"
                      required
                    />
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-bold text-ink mb-1">
                    Duration (Days) & Lift Multiplier
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      type="number"
                      min="1"
                      max="60"
                      value={newDuration}
                      onChange={(e) => setNewDuration(Number(e.target.value))}
                      className="w-full h-8 px-2.5 border border-[#ebeaf0] rounded-lg text-xs outline-none focus:border-violet bg-white"
                      title="Duration Days"
                    />
                    <div className="relative">
                      <input
                        type="number"
                        step="0.05"
                        min="1.0"
                        max="2.5"
                        value={newLift}
                        onChange={(e) => setNewLift(Number(e.target.value))}
                        className="w-full h-8 pl-2.5 pr-6 border border-[#ebeaf0] rounded-lg text-xs font-bold outline-none focus:border-violet bg-white"
                        title="Lift Multiplier"
                      />
                      <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-muted font-bold">×</span>
                    </div>
                  </div>
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-ink mb-1">
                    Commercial Intent Themes (Comma separated)
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. rain_gear, tea_snacks, indoor_cooking"
                    value={newThemesStr}
                    onChange={(e) => setNewThemesStr(e.target.value)}
                    className="w-full h-8 px-2.5 border border-[#ebeaf0] rounded-lg text-xs outline-none focus:border-violet bg-white"
                  />
                </div>
              </div>

              {/* Multi-Select Category Dropdown */}
              <div>
                <label className="block text-[11px] font-bold text-ink mb-1">
                  Direct Target Categories (Multiple Select)
                </label>
                <CategoryMultiSelectDropdown
                  allCategories={allCategories}
                  selectedCategories={newSelectedCategories}
                  onChange={setNewSelectedCategories}
                  placeholder="Select specific categories (optional - leave empty for AI auto-match)..."
                />
                <p className="text-[10px] text-muted mt-1">
                  Tip: You can manually pick exact categories, or leave empty to let the AI MiniLM model match your intent themes automatically.
                </p>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddForm(false)}
                  className="px-3 py-1 rounded-lg text-xs text-muted hover:text-ink"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-3 py-1 rounded-lg bg-violet text-white text-xs font-bold hover:bg-violet/90"
                >
                  Save Campaign
                </button>
              </div>
            </form>
          )}

          {/* Festival Events List */}
          {loading ? (
            <div className="text-center py-10 text-muted text-xs flex items-center justify-center gap-2">
              <RefreshCw size={14} className="animate-spin text-violet" />
              <span>Loading festival merchandising models...</span>
            </div>
          ) : festivals.length === 0 ? (
            <div className="text-center py-10 text-muted text-xs">
              No festival campaigns found.
            </div>
          ) : (
            <div className="space-y-3">
              {festivals.map((fest: any) => {
                const isActive = fest.is_active !== 0 && fest.status !== "inactive";
                const isOngoing = fest.status === "ongoing";
                const daysAway = fest.days_away ?? 0;
                const cats = Array.isArray(fest.categories) ? fest.categories : [];
                const isEditingThis = editingFestId === fest.id;

                return (
                  <div
                    key={fest.id || fest.name}
                    className={`p-4 rounded-xl border transition-all ${
                      isActive
                        ? isOngoing
                          ? "bg-[#faf7ff] border-violet/30 shadow-sm"
                          : "bg-white border-[#ebeaf0] hover:border-violet/30"
                        : "bg-[#fcfbfe] border-[#f0eff4] opacity-60"
                    }`}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2.5 border-b border-[#f4f3f8]">
                      <div className="flex items-center gap-2.5">
                        <div
                          className={`w-2.5 h-2.5 rounded-full ${
                            isActive
                              ? isOngoing
                                ? "bg-emerald animate-pulse"
                                : "bg-violet"
                              : "bg-muted/40"
                          }`}
                        />
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="font-display text-sm font-bold text-ink">
                              {fest.name}
                            </h4>
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                isOngoing
                                  ? "bg-emerald/10 text-emerald"
                                  : daysAway <= 7
                                  ? "bg-amber-500/10 text-amber-600"
                                  : "bg-[#f4f3f8] text-muted"
                              }`}
                            >
                              {isOngoing
                                ? "Active Now"
                                : daysAway === 0
                                ? "Today"
                                : `${fest.formatted_date} (in ${daysAway}d)`}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-3 self-end sm:self-auto">
                        <div className="flex items-center gap-1.5 bg-[#f8f8fb] px-2.5 py-1 rounded-lg border border-[#ebeaf0]">
                          <span className="text-[11px] text-muted font-medium">Lift:</span>
                          <span className="text-xs font-bold text-violet">
                            {fest.lift_multiplier || 1.35}×
                          </span>
                        </div>

                        <button
                          type="button"
                          onClick={() => handleToggleActive(fest)}
                          className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-colors ${
                            isActive
                              ? "bg-emerald/10 text-emerald hover:bg-rose-50 hover:text-rose-600"
                              : "bg-[#f4f3f8] text-muted hover:bg-emerald/10 hover:text-emerald"
                          }`}
                        >
                          {isActive ? "Enabled" : "Disabled"}
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            if (isEditingThis) {
                              setEditingFestId(null);
                            } else {
                              setEditingFestId(fest.id);
                              setEditingCustomCats(fest.custom_categories ? (typeof fest.custom_categories === "string" ? JSON.parse(fest.custom_categories) : fest.custom_categories) : (Array.isArray(fest.categories) ? fest.categories : []));
                            }
                          }}
                          className="px-2 py-1 rounded-lg bg-[#f4f3f8] hover:bg-[#efeaff] text-muted hover:text-violet text-xs font-bold flex items-center gap-1 transition-colors"
                          title="Customize categories"
                        >
                          <Sliders size={12} />
                          <span>{isEditingThis ? "Cancel" : "Edit Categories"}</span>
                        </button>

                        {fest.id > 11 && (
                          <button
                            type="button"
                            onClick={() => handleDelete(fest.id)}
                            className="p-1 rounded-lg text-muted hover:text-rose-500 hover:bg-rose-50"
                            title="Delete custom campaign"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Inline Category Editor */}
                    {isEditingThis ? (
                      <div className="pt-3 space-y-2.5 bg-[#fdfcff] p-3 rounded-xl border border-violet/20 mt-2 animate-in fade-in">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-ink">
                            Customize Target Categories for {fest.name}:
                          </span>
                          <button
                            type="button"
                            onClick={() => handleSaveCustomCategories(fest.id, [])}
                            className="text-[11px] text-violet font-bold hover:underline"
                          >
                            Reset to AI Auto-Match
                          </button>
                        </div>
                        <CategoryMultiSelectDropdown
                          allCategories={allCategories}
                          selectedCategories={editingCustomCats}
                          onChange={setEditingCustomCats}
                          placeholder="Select custom categories to override..."
                        />
                        <div className="flex justify-end gap-2 pt-1">
                          <button
                            type="button"
                            onClick={() => setEditingFestId(null)}
                            className="px-2.5 py-1 rounded-lg text-xs text-muted hover:text-ink"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={() => handleSaveCustomCategories(fest.id, editingCustomCats)}
                            className="px-3 py-1 rounded-lg bg-violet text-white text-xs font-bold hover:bg-violet/90"
                          >
                            Save Categories
                          </button>
                        </div>
                      </div>
                    ) : (
                      /* Matched Inventory Categories View */
                      <div className="pt-2.5">
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-muted">
                            {fest.custom_categories ? "Custom Category Overrides:" : "AI Auto-Matched Store Categories:"}
                          </span>
                          <span className="text-[10px] text-muted">
                            {cats.length} target categories / {cats.length > 0 ? "Active in RecSys" : "No overlap in catalog"}
                          </span>
                        </div>

                        {cats.length > 0 ? (
                          <div className="flex flex-wrap gap-1.5">
                            {cats.map((c: string) => (
                              <span
                                key={c}
                                className="px-2 py-0.5 rounded-lg text-[11px] font-medium bg-[#f3f0ff] text-violet border border-violet/15 flex items-center gap-1"
                              >
                                <span>{c}</span>
                                <span className="text-[9px] text-emerald font-bold">+{Math.round(((fest.lift_multiplier || 1.35) - 1) * 100)}%</span>
                              </span>
                            ))}
                          </div>
                        ) : (
                          <div className="text-[11px] text-muted italic">
                            No direct category affinity in current inventory — items will receive standard baseline weight.
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-[#f4f3f8] flex items-center justify-between bg-[#faf9fd]">
          <span className="text-xs text-muted">
            Learned vectors & theme affinities are evaluated dynamically against your live inventory.
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-ink text-white text-xs font-bold hover:bg-ink/90 transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Overview Component with Working Report Export ────────────────────────────
function Overview() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [showMerchandisingModal, setShowMerchandisingModal] = useState(false);

  const metrics: any = useApi("/api/growth/metrics", {
    observed_ai_attributed_revenue_rupees: 24891,
    total_orders_count: 642,
    aov_rupees: 86.4,
    guardrail_pass_rate_pct: 98.7,
  }, refreshKey);

  const seasonal: any = useApi("/api/catalog/seasonal-context", {
    season: "Monsoon",
    weather: { description: "Partly cloudy", temp_celsius: 26.6, city: "Delhi", is_live_api: true },
    boost_weight: 1.15,
    upcoming_festivals: [{ name: "Onam Festive Season", formatted_date: "Sep 05", days_away: 2 }],
  }, refreshKey);

  const timelineData: any = useApi("/api/growth/timeline?limit=10", { timeline: [] }, refreshKey);
  const auditData: any = useApi("/api/growth/audit-log?limit=10", { logs: [] }, refreshKey);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      setRefreshKey((k) => k + 1);
      toast.success("Dashboard data refreshed from database!");
    } catch {
      toast.error("Failed to refresh data");
    } finally {
      setTimeout(() => setRefreshing(false), 300);
    }
  };

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
  const weatherDesc = weatherObj?.description || weatherObj?.condition || "Partly cloudy";
  const weatherCond = weatherObj?.condition || "clouds";
  const isLiveWeather = Boolean(weatherObj?.is_live_api);
  const temperature = weatherObj?.temp_celsius ?? 26.6;
  const cityName = weatherObj?.city || "Delhi";
  const seasonName = seasonal?.season_label || seasonal?.season || "Late Monsoon / Festive Transition";
  const boostMultiplier = seasonal?.boost_weight || 1.15;
  const liveDateStr = seasonal?.formatted_date || new Date().toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" });
  const festivalsRaw = seasonal?.upcoming_festivals || [];
  const festivalsStr = Array.isArray(festivalsRaw) && festivalsRaw.length > 0
    ? festivalsRaw
        .map((f: any) =>
          typeof f === "object" && f !== null
            ? `${f.name} (${f.formatted_date || (f.days_away === 0 ? "Today" : `in ${f.days_away}d`)})`
            : String(f)
        )
        .join(" · ")
    : "Standard Season (No immediate festival window)";

  // ── Multi-Report Export Functions ──────────────────────────────────────────
  const [exportDropdownOpen, setExportDropdownOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target as Node)) {
        setExportDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  const getTodayDate = () => new Date().toISOString().slice(0, 10);

  const downloadCsv = (filename: string, headers: string[], rows: (string | number)[][]) => {
    const csvContent = [
      headers.map((h) => `"${String(h).replace(/"/g, '""')}"`).join(","),
      ...rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))
    ].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const exportExecutiveSummary = () => {
    const headers = ["Metric", "Value", "Notes"];
    const rows = [
      ["Report Date", getTodayDate(), "Executive Commerce Summary"],
      ["Total Revenue (INR)", String(metrics.realized_gross_revenue_rupees || metrics.gross_merchandise_volume_rupees || 59002), "Total Store GMV"],
      ["AI-Attributed Revenue (INR)", String(metrics.observed_ai_attributed_revenue_rupees || 24891), "Direct lift from RecSys"],
      ["Autonomous Orders Count", String(metrics.total_orders_count || 642), "Orders handled autonomously"],
      ["Average Order Value (INR)", String(metrics.aov_rupees || 86.4), "AOV across catalog"],
      ["Current Season", seasonName, cityName],
      ["Seasonal Boost Multiplier", `${boostMultiplier}x`, "Dynamic environmental weight"],
      ["Active Festivals", festivalsStr, "Festival merchandising context"],
      ["Guardrail Pass Rate", `${metrics.guardrail_pass_rate_pct || 98.7}%`, "Mandates approved without block"]
    ];

    downloadCsv(`cartpilot_executive_summary_${getTodayDate()}.csv`, headers, rows);
    toast.success("Downloaded Executive Summary CSV!");
    setExportDropdownOpen(false);
  };

  const exportOrdersLedger = async () => {
    setExporting(true);
    try {
      const res = await fetch(apiUrl("/api/audit/orders"));
      const data = res.ok ? await res.json() : { orders: [] };
      const orders = Array.isArray(data?.orders) ? data.orders : [];

      const headers = [
        "Order ID",
        "Timestamp",
        "Items Count",
        "Items Purchased",
        "Total (INR)",
        "Guardrail Status",
        "Order Status",
        "Attribution Channel",
        "Audit SHA-256 Hash"
      ];

      const rows = orders.map((o: any) => [
        o.order_id || o.id || "N/A",
        o.created_at ? new Date(o.created_at).toISOString() : new Date().toISOString(),
        String(o.item_count || (Array.isArray(o.items) ? o.items.length : 1)),
        Array.isArray(o.items)
          ? o.items.map((i: any) => `${i.qty || 1}x ${i.name || i.sku} (₹${i.price_rupees || (i.price_paise ? (i.price_paise / 100).toFixed(2) : 0)})`).join("; ")
          : "N/A",
        String(o.total_amount_rupees || (o.total_amount_paise ? (o.total_amount_paise / 100).toFixed(2) : (o.total_paise ? (o.total_paise / 100).toFixed(2) : 0))),
        o.guardrail_status || "APPROVED",
        o.status?.toUpperCase() || "SETTLED",
        o.attribution || "Autonomous Agent",
        o.sha256_hash || o.hash || "verified_chain"
      ]);

      downloadCsv(`cartpilot_financial_orders_ledger_${getTodayDate()}.csv`, headers, rows);
      toast.success(`Downloaded ${orders.length} orders in Financial Ledger CSV!`);
    } catch {
      toast.error("Failed to export order ledger");
    } finally {
      setExporting(false);
      setExportDropdownOpen(false);
    }
  };

  const exportInventorySheet = async () => {
    setExporting(true);
    try {
      const res = await fetch(apiUrl("/api/console/catalog?limit=500"));
      const data = res.ok ? await res.json() : {};
      const items = Array.isArray(data) ? data : Array.isArray(data?.items) ? data.items : [];

      const headers = [
        "SKU",
        "Product Name",
        "Category",
        "Unit Price (INR)",
        "Stock Quantity",
        "Stock Status",
        "Total Stock Valuation (INR)",
        "AI Boosted",
        "Merchant / Vendor",
        "Description"
      ];

      const rows = items.map((p: any) => {
        const unitPrice = Number(p.price_rupees || (p.price_paise ? p.price_paise / 100 : 0));
        const stock = Number(p.stock || 0);
        const valuation = (unitPrice * stock).toFixed(2);
        const stockStatus = stock <= 0 ? "Out of Stock" : stock < 5 ? "Low Stock (<5)" : "In Stock";

        return [
          p.sku || "N/A",
          p.name || p.title || "Product",
          p.category || "general",
          unitPrice.toFixed(2),
          String(stock),
          stockStatus,
          valuation,
          p.boosted ? "YES (+35% AI Weight)" : "Standard (1.0x)",
          p.merchant || "Store Direct",
          (p.description || "").replace(/"/g, '""')
        ];
      });

      downloadCsv(`cartpilot_inventory_stock_valuation_${getTodayDate()}.csv`, headers, rows);
      toast.success(`Downloaded ${items.length} items in Inventory Valuation CSV!`);
    } catch {
      toast.error("Failed to export inventory valuation sheet");
    } finally {
      setExporting(false);
      setExportDropdownOpen(false);
    }
  };

  const { user } = useAuth();
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour >= 5 && hour < 12) return "Good morning";
    if (hour >= 12 && hour < 17) return "Good afternoon";
    return "Good evening";
  };

  const displayName = user?.name && user.name !== "Store Owner" && user.name !== "Shopper"
    ? `, ${user.name.split(" ")[0]}`
    : "";
  const greetingTitle = `${getGreeting()}${displayName}`;

  return (
    <>
      <PageHeader
        title={greetingTitle}
        action={
          <div className="flex items-center gap-2">
            <button
              className="secondary-button flex items-center gap-1.5 text-xs font-bold"
              onClick={handleRefresh}
              disabled={refreshing}
            >
              <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
              <span>{refreshing ? "Refreshing..." : "Refresh"}</span>
            </button>

            {/* Multi-Report Export Dropdown */}
            <div className="relative" ref={exportMenuRef}>
              <button
                className="primary-button flex items-center gap-1.5 text-xs font-bold"
                onClick={() => setExportDropdownOpen(!exportDropdownOpen)}
                disabled={exporting}
              >
                {exporting ? (
                  <>
                    <RefreshCw size={13} className="animate-spin" />
                    <span>Preparing...</span>
                  </>
                ) : (
                  <>
                    <Download size={14} />
                    <span>Export Report</span>
                    <ChevronDown size={13} className={`transition-transform ${exportDropdownOpen ? "rotate-180" : ""}`} />
                  </>
                )}
              </button>

              {exportDropdownOpen && (
                <div className="absolute right-0 mt-2 w-72 bg-white border border-[#ebeaf0] rounded-2xl shadow-xl p-2 z-40 animate-in fade-in slide-in-from-top-2 duration-150">
                  <div className="px-3 py-2 border-b border-[#f4f3f8] mb-1">
                    <div className="text-[11px] font-bold uppercase tracking-wider text-muted">Merchant Export Center</div>
                    <div className="text-xs text-ink font-medium">Select report to download as CSV</div>
                  </div>

                  <div className="space-y-1">
                    <button
                      onClick={exportExecutiveSummary}
                      className="w-full text-left p-2.5 rounded-xl hover:bg-[#faf9fd] transition-colors flex items-start gap-2.5 group"
                    >
                      <div className="w-8 h-8 rounded-lg bg-[#efeaff] text-violet flex items-center justify-center shrink-0 mt-0.5 group-hover:bg-violet group-hover:text-white transition-colors">
                        <BarChart3 size={15} />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-ink">Executive Summary & AI ROI</div>
                        <div className="text-[11px] text-muted leading-tight">
                          GMV, AI-attributed lift, AOV, and seasonal context.
                        </div>
                      </div>
                    </button>

                    <button
                      onClick={exportOrdersLedger}
                      className="w-full text-left p-2.5 rounded-xl hover:bg-[#faf9fd] transition-colors flex items-start gap-2.5 group"
                    >
                      <div className="w-8 h-8 rounded-lg bg-[#e8f7f0] text-emerald flex items-center justify-center shrink-0 mt-0.5 group-hover:bg-emerald group-hover:text-white transition-colors">
                        <CreditCard size={15} />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-ink">Financial Order Ledger</div>
                        <div className="text-[11px] text-muted leading-tight">
                          Accounting & tax sheet with all orders and audit hashes.
                        </div>
                      </div>
                    </button>

                    <button
                      onClick={exportInventorySheet}
                      className="w-full text-left p-2.5 rounded-xl hover:bg-[#faf9fd] transition-colors flex items-start gap-2.5 group"
                    >
                      <div className="w-8 h-8 rounded-lg bg-[#fff0e4] text-orange flex items-center justify-center shrink-0 mt-0.5 group-hover:bg-orange group-hover:text-white transition-colors">
                        <Boxes size={15} />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-ink">Inventory & Stock Valuation</div>
                        <div className="text-[11px] text-muted leading-tight">
                          Full catalog, stock quantities, and inventory valuation.
                        </div>
                      </div>
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        }
      />

      <div className="stat-grid">
        <Stat
          label="Total Revenue"
          value={`₹${(metrics.realized_gross_revenue_rupees || metrics.gross_merchandise_volume_rupees || 59002).toLocaleString()}`}
          delta="+14.2%"
        />
        <Stat
          label="AI-Attributed Revenue"
          value={`₹${(metrics.observed_ai_attributed_revenue_rupees || 24891).toLocaleString()}`}
          delta="+18.4%"
        />
        <Stat
          label="Autonomous Orders"
          value={metrics.total_orders_count || 642}
          delta="+12.8%"
        />
        <Stat
          label="Avg. Order Value"
          value={`₹${Math.round(metrics.aov_rupees || 86)}`}
          delta="+6.2%"
        />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.45fr_0.9fr] mt-5">
        {/* Interactive Chart with Dropdown Timeframe */}
        <InteractiveCommerceChart />

        {/* Live Environmental Context Card */}
        <Card>
          <div className="card-heading">
            <div>
              <div className="flex items-center gap-2">
                <h3>Live Environmental Senses</h3>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald/10 text-emerald">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald animate-pulse" />
                  {isLiveWeather ? "Live Weather API" : "Live Senses"}
                </span>
              </div>
              <p>Dynamic context shaping RecSys weights · {liveDateStr}</p>
            </div>
            <CloudSun size={20} className="text-violet" />
          </div>
          <div className="weather-block">
            <WeatherIcon condition={weatherCond} />
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
            <strong className="text-right max-w-[280px] truncate" title={festivalsStr}>{festivalsStr}</strong>
          </div>
          <div className="sense-row">
            <span>Category Multiplier</span>
            <strong className="text-emerald font-bold">
              {boostMultiplier}× Visibility Boost
            </strong>
          </div>
          <div className="mt-4 pt-3 border-t border-[#f4f3f8] flex items-center justify-between">
            <span className="text-[11px] text-muted">Universal Seasonal Merchandising</span>
            <Link
              href="/merchant/campaigns"
              className="text-xs font-bold text-violet hover:underline flex items-center gap-1 group"
            >
              <span>Open Campaign Studio →</span>
              <ChevronRight size={13} className="group-hover:translate-x-0.5 transition-transform" />
            </Link>
          </div>
        </Card>
      </div>

      <MerchandisingStudioModal
        isOpen={showMerchandisingModal}
        onClose={() => setShowMerchandisingModal(false)}
        onUpdated={() => setRefreshKey((k) => k + 1)}
      />

      {/* Top 10 Autonomous Agent Decisions & Activity Table */}
      <Card className="p-0 overflow-hidden shadow-sm mt-6">
        <div className="p-4 bg-[#fbfafc] border-b border-[#ebeaf0] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-[#efeaff] text-violet flex items-center justify-center">
              <Bot size={14} />
            </div>
            <h3 className="font-display text-sm font-bold text-ink">Recent Autonomous Agent Activity (Top 10)</h3>
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

  // Add Product Modal State
  const [showAddModal, setShowAddModal] = useState(false);
  const [submittingProduct, setSubmittingProduct] = useState(false);
  const [newProdName, setNewProdName] = useState("");
  const [newProdCategory, setNewProdCategory] = useState("groceries");
  const [newProdCustomCat, setNewProdCustomCat] = useState("");
  const [newProdPrice, setNewProdPrice] = useState("");
  const [newProdStock, setNewProdStock] = useState("20");
  const [newProdSku, setNewProdSku] = useState("");
  const [newProdDesc, setNewProdDesc] = useState("");
  const [newProdImage, setNewProdImage] = useState("");

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

  const handleCreateProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProdName.trim()) {
      toast.error("Please enter a product name");
      return;
    }
    const priceNum = parseFloat(newProdPrice);
    if (isNaN(priceNum) || priceNum <= 0) {
      toast.error("Please enter a valid price per unit (₹)");
      return;
    }
    const stockNum = parseInt(newProdStock, 10);
    if (isNaN(stockNum) || stockNum < 0) {
      toast.error("Please enter a valid stock quantity");
      return;
    }

    const finalCategory = (newProdCategory === "custom" ? newProdCustomCat : newProdCategory).trim().toLowerCase() || "general";

    setSubmittingProduct(true);
    try {
      const res = await fetch(apiUrl("/api/catalog/products"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newProdName.trim(),
          category: finalCategory,
          price_rupees: priceNum,
          stock: stockNum,
          sku: newProdSku.trim() || undefined,
          description: newProdDesc.trim() || undefined,
          image_url: newProdImage.trim() || undefined,
        }),
      });

      if (res.ok) {
        toast.success(`Added "${newProdName.trim()}" to catalog!`);
        setShowAddModal(false);
        setNewProdName("");
        setNewProdPrice("");
        setNewProdStock("20");
        setNewProdSku("");
        setNewProdDesc("");
        setNewProdImage("");
        fetchCatalog();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Failed to add product");
      }
    } catch {
      toast.error("Network error adding product");
    } finally {
      setSubmittingProduct(false);
    }
  };

  // Derive unique categories for dropdown
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
      {/* ── Search & Filter Bar with Add Item Button ──────────────────────── */}
      <div className="card p-4 mb-4 shadow-sm">
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
          {/* Search Box & Category Dropdown */}
          <div className="flex flex-1 items-center gap-3 flex-wrap sm:flex-nowrap">
            {/* Search Input */}
            <div className="relative flex-1 min-w-[200px]">
              <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
              <input
                type="text"
                placeholder="Search product name, SKU, or category..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full h-10 pl-9 pr-8 bg-[#fbfafc] border border-[#ebeaf0] rounded-xl text-xs text-ink outline-none focus:border-violet font-medium"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
                >
                  <X size={13} />
                </button>
              )}
            </div>

            {/* Category Dropdown */}
            <div className="relative min-w-[180px] w-full sm:w-auto">
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                className="w-full h-10 pl-3 pr-8 bg-[#fbfafc] border border-[#ebeaf0] rounded-xl text-xs font-bold text-ink outline-none focus:border-violet cursor-pointer capitalize"
              >
                <option value="all">All Categories ({catalog.length})</option>
                {categories.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat.replace(/-/g, " ")}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Right Action Controls: Boost Toggle & Add Product */}
          <div className="flex items-center gap-2 self-end md:self-auto shrink-0">
            <button
              onClick={() => setFilterBoostedOnly(!filterBoostedOnly)}
              className={`text-xs font-bold px-3 py-2 rounded-xl border transition-all flex items-center gap-1.5 h-10 ${
                filterBoostedOnly
                  ? "bg-violet text-white border-violet shadow-sm"
                  : "bg-white text-ink border-[#ebeaf0] hover:border-violet"
              }`}
            >
              <Zap size={13} />
              <span>Show Boosted ({boostedCount})</span>
            </button>

            <button
              onClick={() => setShowAddModal(true)}
              className="primary-button text-xs font-bold flex items-center gap-1.5 h-10 px-3.5"
            >
              <Plus size={14} />
              <span>Add Item</span>
            </button>
          </div>
        </div>
      </div>

      {/* ── Add Product Modal ────────────────────────────────────────────── */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <form
            onSubmit={handleCreateProduct}
            className="bg-white rounded-2xl p-6 max-w-lg w-full shadow-2xl border border-[#ebeaf0] space-y-4 max-h-[90vh] overflow-y-auto"
          >
            <div className="flex items-center justify-between pb-3 border-b border-[#f4f3f8]">
              <div>
                <h3 className="font-display text-base font-bold text-ink">Add New Catalog Item</h3>
                <p className="text-xs text-muted">Register a new product with unit price and available stock quantity.</p>
              </div>
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="w-8 h-8 rounded-xl bg-[#f4f3f8] text-muted hover:text-ink flex items-center justify-center"
              >
                <X size={15} />
              </button>
            </div>

            <div className="space-y-3.5">
              <div>
                <label className="block text-xs font-bold text-ink mb-1">
                  Product Name <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Organic Arabica Whole Bean Coffee"
                  value={newProdName}
                  onChange={(e) => setNewProdName(e.target.value)}
                  className="w-full h-10 px-3 border border-[#ebeaf0] rounded-xl text-xs outline-none focus:border-violet"
                  required
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-ink mb-1">
                    Price per Unit (₹) <span className="text-rose-500">*</span>
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted text-xs font-bold">₹</span>
                    <input
                      type="number"
                      step="0.01"
                      placeholder="499.00"
                      value={newProdPrice}
                      onChange={(e) => setNewProdPrice(e.target.value)}
                      className="w-full h-10 pl-7 pr-3 border border-[#ebeaf0] rounded-xl text-xs font-bold outline-none focus:border-violet"
                      required
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-ink mb-1">
                    Stock Quantity <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="number"
                    min="0"
                    placeholder="25"
                    value={newProdStock}
                    onChange={(e) => setNewProdStock(e.target.value)}
                    className="w-full h-10 px-3 border border-[#ebeaf0] rounded-xl text-xs font-bold outline-none focus:border-violet"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-ink mb-1">
                    Category <span className="text-rose-500">*</span>
                  </label>
                  <select
                    value={newProdCategory}
                    onChange={(e) => setNewProdCategory(e.target.value)}
                    className="w-full h-10 px-3 border border-[#ebeaf0] rounded-xl text-xs font-bold text-ink outline-none focus:border-violet capitalize cursor-pointer"
                  >
                    {categories.length > 0 ? (
                      categories.map((cat) => (
                        <option key={cat} value={cat}>
                          {cat.replace(/-/g, " ")}
                        </option>
                      ))
                    ) : (
                      <option value="groceries">Groceries</option>
                    )}
                    <option value="custom">+ New Category...</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-bold text-ink mb-1">
                    SKU (Optional)
                  </label>
                  <input
                    type="text"
                    placeholder="Auto-generated if blank"
                    value={newProdSku}
                    onChange={(e) => setNewProdSku(e.target.value)}
                    className="w-full h-10 px-3 border border-[#ebeaf0] rounded-xl text-xs uppercase outline-none focus:border-violet font-mono"
                  />
                </div>
              </div>

              {newProdCategory === "custom" && (
                <div>
                  <label className="block text-xs font-bold text-ink mb-1">
                    Custom Category Name <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. artisan-bakery"
                    value={newProdCustomCat}
                    onChange={(e) => setNewProdCustomCat(e.target.value)}
                    className="w-full h-10 px-3 border border-[#ebeaf0] rounded-xl text-xs outline-none focus:border-violet"
                    required
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-bold text-ink mb-1">Image URL (Optional)</label>
                <input
                  type="url"
                  placeholder="https://images.unsplash.com/..."
                  value={newProdImage}
                  onChange={(e) => setNewProdImage(e.target.value)}
                  className="w-full h-10 px-3 border border-[#ebeaf0] rounded-xl text-xs outline-none focus:border-violet"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-ink mb-1">Description (Optional)</label>
                <textarea
                  rows={2}
                  placeholder="Brief description for AI semantic search and recommendations..."
                  value={newProdDesc}
                  onChange={(e) => setNewProdDesc(e.target.value)}
                  className="w-full p-3 border border-[#ebeaf0] rounded-xl text-xs outline-none focus:border-violet resize-none"
                />
              </div>
            </div>

            <div className="flex items-center gap-3 pt-3 border-t border-[#f4f3f8]">
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="flex-1 py-2.5 rounded-xl border border-[#ebeaf0] text-xs font-semibold text-muted hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submittingProduct}
                className="flex-1 py-2.5 rounded-xl bg-violet text-white text-xs font-bold shadow-md hover:bg-[#6849d8] flex items-center justify-center gap-1.5"
              >
                {submittingProduct ? (
                  <>
                    <RefreshCw size={13} className="animate-spin" />
                    <span>Adding Product...</span>
                  </>
                ) : (
                  <>
                    <Plus size={14} />
                    <span>Add to Catalog</span>
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      )}

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

      {/* Filter Tabs & New Experiment Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-2 flex-wrap">
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

        <button
          className="primary-button flex items-center gap-1.5 text-xs font-bold self-end sm:self-auto"
          onClick={() => toast.success("Draft experiment created")}
        >
          <Plus size={15} />
          <span>New Experiment</span>
        </button>
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

// ── Unified Category Management View (Allowed Categories + Category Pairings Graph) ───
function CategoryManagementView() {
  const [activeTab, setActiveTab] = useState<"permitted" | "pairings">("permitted");
  const [allowedCategories, setAllowedCategories] = useState<string[]>([
    "groceries",
    "kitchen-accessories",
    "smartphones",
    "mobile-accessories",
    "mens-shirts",
    "motorcycle",
    "vehicle",
  ]);
  const [availableCategories, setAvailableCategories] = useState<string[]>([]);
  const [categorySearch, setCategorySearch] = useState("");
  const [spendCapPaise, setSpendCapPaise] = useState<number>(1000000);
  const [autonomyThresholdPaise, setAutonomyThresholdPaise] = useState<number>(500000);
  const [saving, setSaving] = useState(false);

  // Pairings state
  const [pairs, setPairs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [newCatA, setNewCatA] = useState("");
  const [newCatB, setNewCatB] = useState("");
  const [reasoning, setReasoning] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);

  // Dual search state for pairings
  const [searchCat1, setSearchCat1] = useState("");
  const [searchCat2, setSearchCat2] = useState("");
  const [isDualSearch, setIsDualSearch] = useState(false);
  const [showSug1, setShowSug1] = useState(false);
  const [showSug2, setShowSug2] = useState(false);

  const fetchAllData = async () => {
    setLoading(true);
    try {
      const [polRes, compatRes] = await Promise.all([
        fetch(apiUrl("/api/console/policy")),
        fetch(apiUrl("/api/console/category-compat")),
      ]);

      if (polRes.ok) {
        const polData = await polRes.json();
        if (Array.isArray(polData.allowed_categories)) {
          setAllowedCategories(polData.allowed_categories);
        }
        if (Array.isArray(polData.available_categories)) {
          setAvailableCategories(polData.available_categories);
        }
        if (polData.spend_cap_paise) setSpendCapPaise(polData.spend_cap_paise);
        if (polData.autonomy_threshold_paise) setAutonomyThresholdPaise(polData.autonomy_threshold_paise);
      }

      if (compatRes.ok) {
        const data = await compatRes.json();
        setPairs(data.pairs || []);
      } else {
        const res2 = await fetch(apiUrl("/api/catalog/compatibility"));
        if (res2.ok) {
          const data2 = await res2.json();
          setPairs(Array.isArray(data2) ? data2 : data2.pairs || []);
        }
      }
    } catch {
      toast.error("Failed to load category data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAllData();
  }, []);

  const handleToggleCategory = (cat: string) => {
    if (allowedCategories.includes(cat)) {
      if (allowedCategories.length <= 1) {
        toast.error("At least one product category must remain permitted");
        return;
      }
      setAllowedCategories(allowedCategories.filter((c) => c !== cat));
    } else {
      setAllowedCategories([...allowedCategories, cat]);
    }
  };

  const handleSelectAll = () => {
    if (availableCategories.length > 0) {
      setAllowedCategories([...availableCategories]);
      toast.info("All catalog categories selected");
    }
  };

  const handleResetDefaults = () => {
    const defaults = [
      "groceries",
      "kitchen-accessories",
      "smartphones",
      "mobile-accessories",
      "mens-shirts",
      "motorcycle",
      "vehicle",
    ];
    setAllowedCategories(defaults);
    toast.info("Reset to 7 standard retail categories");
  };

  const handleSaveCategories = async () => {
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
          spend_cap_paise: spendCapPaise || 1000000,
          autonomy_threshold_paise: autonomyThresholdPaise || 500000,
          allowed_categories: allowedCategories,
        }),
      });

      if (res.ok) {
        toast.success(`Saved ${allowedCategories.length} permitted categories`);
        fetchAllData();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Failed to update category permissions");
      }
    } catch {
      toast.error("Network error saving category permissions");
    } finally {
      setSaving(false);
    }
  };

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
        fetchAllData();
      }
    } catch {
      toast.error("Failed to add compatibility pair");
    }
  };

  const handleDeletePair = async (catA: string, catB: string) => {
    try {
      const res = await fetch(
        apiUrl(`/api/console/category-compat/${encodeURIComponent(catA)}/${encodeURIComponent(catB)}`),
        { method: "DELETE" }
      );
      if (res.ok) {
        toast.success(`Removed link: ${catA} ↔ ${catB}`);
        fetchAllData();
      }
    } catch {
      toast.error("Failed to delete pair");
    }
  };

  const filteredCategories = availableCategories.filter((c) =>
    c.toLowerCase().includes(categorySearch.toLowerCase().trim())
  );

  const filteredPairs = pairs.filter((p) => {
    const q1 = searchCat1.trim().toLowerCase();
    const q2 = searchCat2.trim().toLowerCase();

    const matches1 =
      !q1 ||
      (p.category_a && p.category_a.toLowerCase().includes(q1)) ||
      (p.category_b && p.category_b.toLowerCase().includes(q1)) ||
      (p.reasoning && p.reasoning.toLowerCase().includes(q1));

    if (isDualSearch && q2) {
      return (
        ((p.category_a && p.category_a.toLowerCase().includes(q1)) &&
          (p.category_b && p.category_b.toLowerCase().includes(q2))) ||
        ((p.category_a && p.category_a.toLowerCase().includes(q2)) &&
          (p.category_b && p.category_b.toLowerCase().includes(q1)))
      );
    }

    return matches1;
  });

  const categoryOptions =
    availableCategories.length > 0
      ? availableCategories
      : [
          "groceries",
          "kitchen-accessories",
          "smartphones",
          "mobile-accessories",
          "mens-shirts",
          "mens-shoes",
          "beauty",
          "sports-accessories",
          "sunglasses",
          "womens-shoes",
        ];

  return (
    <>
      <div className="stat-grid mb-6">
        <Stat
          label="Permitted Categories"
          value={allowedCategories.length}
          delta="100% Coverage"
        />
        <Stat
          label="Excluded Categories"
          value={Math.max(0, availableCategories.length - allowedCategories.length)}
          delta="Policy Protected"
        />
        <Stat
          label="Category Pairings"
          value={pairs.length}
          delta="Semantic Graph"
        />
        <Stat
          label="Available in Catalog"
          value={availableCategories.length}
          delta="Live Synced"
        />
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#ebeaf0] mb-6">
        <div className="flex gap-6 text-xs font-bold overflow-x-auto">
          {[
            { id: "permitted", label: "Permitted Store Categories", count: allowedCategories.length },
            { id: "pairings", label: "Category Pairings Graph", count: pairs.length },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`pb-3 relative transition-all flex items-center gap-2 whitespace-nowrap ${
                activeTab === tab.id
                  ? "text-violet border-b-2 border-violet"
                  : "text-muted hover:text-ink"
              }`}
            >
              <span>{tab.label}</span>
              <span
                className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                  activeTab === tab.id ? "bg-[#efeaff] text-violet" : "bg-[#f4f3f8] text-muted"
                }`}
              >
                {tab.count}
              </span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 pb-2 sm:pb-3 self-end sm:self-auto">
          <button className="secondary-button text-xs font-bold flex items-center gap-1.5" onClick={fetchAllData} disabled={loading}>
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            <span>Sync</span>
          </button>
          {activeTab === "permitted" ? (
            <button className="primary-button text-xs font-bold flex items-center gap-1.5" onClick={handleSaveCategories} disabled={saving}>
              <Save size={14} />
              <span>{saving ? "Saving..." : "Save Permissions"}</span>
            </button>
          ) : (
            <button className="primary-button text-xs font-bold flex items-center gap-1.5" onClick={() => setShowAddModal(true)}>
              <Plus size={14} />
              <span>Add Pair</span>
            </button>
          )}
        </div>
      </div>

      {activeTab === "permitted" && (
        <div className="space-y-6">
          <Card className="p-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 pb-3 border-b border-[#f4f3f8]">
              <div>
                <h3 className="font-display text-sm font-bold text-ink">Permitted Product Categories</h3>
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                <button
                  type="button"
                  onClick={handleSelectAll}
                  className="px-2.5 py-1 text-xs font-bold rounded-lg border border-[#ebeaf0] bg-[#faf9fd] text-ink hover:bg-[#efeaff] hover:text-violet transition-all"
                >
                  Allow All ({availableCategories.length})
                </button>
                <button
                  type="button"
                  onClick={handleResetDefaults}
                  className="px-2.5 py-1 text-xs font-bold rounded-lg border border-[#ebeaf0] bg-[#faf9fd] text-ink hover:bg-[#efeaff] hover:text-violet transition-all"
                >
                  Reset Defaults (7)
                </button>
              </div>
            </div>

            <div className="relative mb-4">
              <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
              <input
                type="text"
                placeholder="Filter categories (e.g. groceries, smartphones, fashion)..."
                value={categorySearch}
                onChange={(e) => setCategorySearch(e.target.value)}
                className="w-full h-10 pl-9 pr-8 bg-[#fbfafc] border border-[#ebeaf0] rounded-xl text-xs text-ink outline-none focus:border-violet"
              />
              {categorySearch && (
                <button
                  onClick={() => setCategorySearch("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
                >
                  <X size={13} />
                </button>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
              {filteredCategories.map((cat) => {
                const isAllowed = allowedCategories.includes(cat);
                return (
                  <div
                    key={cat}
                    onClick={() => handleToggleCategory(cat)}
                    className={`p-3.5 rounded-xl border cursor-pointer transition-all flex items-center justify-between select-none ${
                      isAllowed
                        ? "bg-white border-violet/30 shadow-xs hover:border-violet"
                        : "bg-[#faf9fd] border-[#ebeaf0] opacity-60 hover:opacity-100"
                    }`}
                  >
                    <div className="space-y-0.5">
                      <div className="text-xs font-bold text-ink flex items-center gap-1.5 capitalize">
                        <span>{cat.replace(/-/g, " ")}</span>
                      </div>
                      <div className="text-[10px] font-semibold">
                        {isAllowed ? (
                          <span className="text-emerald flex items-center gap-1">
                            <CheckCircle size={10} /> Permitted for AI
                          </span>
                        ) : (
                          <span className="text-muted">Excluded from Store</span>
                        )}
                      </div>
                    </div>

                    <div
                      className={`w-9 h-5 rounded-full transition-colors relative flex items-center p-0.5 shrink-0 ${
                        isAllowed ? "bg-violet" : "bg-[#dcd9e8]"
                      }`}
                    >
                      <div
                        className={`w-4 h-4 rounded-full bg-white shadow-sm transition-transform ${
                          isAllowed ? "translate-x-4" : "translate-x-0"
                        }`}
                      />
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-6 pt-4 border-t border-[#ebeaf0] flex items-center justify-between">
              <div className="text-xs text-muted">
                <strong className="text-ink">{allowedCategories.length}</strong> of{" "}
                <strong className="text-ink">{availableCategories.length}</strong> categories permitted.
              </div>
              <button
                className="primary-button flex items-center gap-1.5"
                onClick={handleSaveCategories}
                disabled={saving}
              >
                <Save size={14} />
                <span>{saving ? "Saving..." : "Save Category Permissions"}</span>
              </button>
            </div>
          </Card>
        </div>
      )}

      {/* ── SUB-TAB 2: CATEGORY PAIRINGS GRAPH ── */}
      {activeTab === "pairings" && (
        <div className="space-y-6">
          <div className="card p-4 space-y-3 relative z-40 overflow-visible shadow-sm">
            <div className="flex flex-col md:flex-row items-stretch md:items-center gap-3 relative">
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
                      setSearchCat2("");
                      setIsDualSearch(false);
                    }}
                    className="p-2.5 text-muted hover:text-red-500 rounded-lg border border-[#ebeaf0] hover:bg-red-50 transition-all"
                    title="Remove 2nd category filter"
                  >
                    <X size={16} />
                  </button>
                </div>
              )}
            </div>

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

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {filteredPairs.map((pair, idx) => (
              <div
                key={idx}
                className="p-4 rounded-xl bg-white border border-[#ebeaf0] hover:border-violet/40 flex flex-col justify-between shadow-xs transition-all"
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
                    {pair.reasoning || "High retail compatibility and cross-sell attachment."}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

// ── Financial Safety Guardrails View ─────────────────────────────────────────
function PolicyView() {
  const [, setLocation] = useLocation();
  const [spendCap, setSpendCap] = useState("10000");
  const [autonomyThreshold, setAutonomyThreshold] = useState("5000");
  const [allowedCategories, setAllowedCategories] = useState<string[]>([
    "groceries",
    "kitchen-accessories",
    "smartphones",
    "mobile-accessories",
    "mens-shirts",
  ]);
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
        toast.success("Financial guardrails successfully saved and audited!");
        fetchPolicy();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Failed to update guardrails");
      }
    } catch {
      toast.error("Network error saving policy guardrails");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="policy-layout">
        <Card>
          <div className="card-heading">
            <div>
              <h3>Financial Guardrails</h3>
              <p>Checked deterministically by LangGraph before authorizing any payment mandate</p>
            </div>
            <ShieldCheck className="text-emerald" size={21} />
          </div>

          <div className="form-field">
            <label>
              Buyer Spend Cap (₹) <span>Maximum allowed cart total per shopping session</span>
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
              Autonomy Threshold (₹) <span>Orders under this threshold execute autonomously without manual prompt</span>
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

          {/* Clean Reference Box to Category Controls */}
          <div className="p-4 bg-[#fbfafc] rounded-xl border border-[#ebeaf0] flex items-center justify-between gap-3 mt-4">
            <div>
              <div className="text-xs font-bold text-ink">Permitted Product Categories ({allowedCategories.length} active)</div>
              <div className="text-[11px] text-muted mt-0.5">
                Manage which product categories the AI is permitted to curate and sell.
              </div>
            </div>
            <button
              type="button"
              onClick={() => setLocation("/merchant/categories")}
              className="px-3 py-1.5 rounded-lg bg-white border border-[#ebeaf0] text-xs font-bold text-violet hover:bg-[#efeaff] transition-all shrink-0"
            >
              Open Category Management →
            </button>
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
            CartPilot will pause for manual authorization when a cart exceeds <strong>₹{parseInt(spendCap || '10000', 10).toLocaleString()}</strong> or when the
            total crosses the autonomous limit of <strong>₹{parseInt(autonomyThreshold || '5000', 10).toLocaleString()}</strong>.
          </p>
          <div className="preview-row">
            <span>Spend Cap</span>
            <b>₹{parseInt(spendCap || '10000', 10).toLocaleString()}</b>
          </div>
          <div className="preview-row">
            <span>Autonomy Limit</span>
            <b>₹{parseInt(autonomyThreshold || '5000', 10).toLocaleString()}</b>
          </div>
          <div className="preview-row">
            <span>Permitted Categories</span>
            <b>{allowedCategories.length} Categories Permitted</b>
          </div>
        </Card>
      </div>

      {/* Action Buttons Below Cards */}
      <div className="flex justify-end items-center gap-2 mt-6">
        <button className="secondary-button text-xs font-bold flex items-center gap-1.5" onClick={fetchPolicy} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          <span>Sync</span>
        </button>
        <button className="primary-button text-xs font-bold flex items-center gap-1.5" onClick={handleSave} disabled={saving}>
          <Save size={14} />
          <span>{saving ? "Saving..." : "Save Guardrails"}</span>
        </button>
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
      <Sidebar collapsed={collapsed} onToggleCollapse={() => setCollapsed(!collapsed)} />
      <div className={`main-shell ${collapsed ? "collapsed" : ""}`}>
        <Header />
        <main className="main-content">
          {location === "/merchant/growth" && <GrowthManager />}
          {location === "/merchant/campaigns" && <CampaignStudio />}
          {location === "/merchant/rules" && <GrowthRules />}
          {location === "/merchant/catalog" && <CatalogView />}
          {location === "/merchant/experiments" && <ExperimentsView />}
          {(location === "/merchant/categories" || location === "/merchant/recommendations") && <CategoryManagementView />}
          {location === "/merchant/audit" && <AuditTrail />}
          {location === "/merchant/policy" && <PolicyView />}
          {(location === "/merchant" || location === "/") && <Overview />}
        </main>
      </div>
    </div>
  );
}
