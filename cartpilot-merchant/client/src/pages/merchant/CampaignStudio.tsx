import { useState, useEffect, useRef } from "react";
import {
  Calendar, Sparkles, Plus, RefreshCw, Sliders, Trash2, Search,
  Check, X, ChevronDown, CloudSun, Layers, Tag
} from "lucide-react";
import { toast } from "sonner";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

// ── Searchable Multi-Select Category Dropdown Component ─────────────────────
export function CategoryMultiSelectDropdown({
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
        className="min-h-[42px] p-2 bg-white border border-[#ebeaf0] rounded-xl text-xs flex items-center justify-between cursor-pointer hover:border-violet transition-colors"
      >
        <div className="flex flex-wrap gap-1.5 items-center flex-1 mr-2">
          {selectedCategories.length === 0 ? (
            <span className="text-muted text-xs">{placeholder}</span>
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
          <span className="text-[10px] font-bold bg-[#f4f3f8] px-2 py-0.5 rounded-full">
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
          <div className="max-h-52 overflow-y-auto space-y-1 pr-1">
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

// ── Main Dedicated Campaign Studio Page ──────────────────────────────────────
export default function CampaignStudio() {
  const [festivals, setFestivals] = useState<any[]>([]);
  const [allCategories, setAllCategories] = useState<string[]>([]);
  const [seasonalContext, setSeasonalContext] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [recalculating, setRecalculating] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "upcoming" | "custom">("all");

  // Editing state for inline category customization
  const [editingFestId, setEditingFestId] = useState<number | null>(null);
  const [editingCustomCats, setEditingCustomCats] = useState<string[]>([]);

  // New campaign form state
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
      const [festRes, catRes, seasonRes] = await Promise.all([
        fetch(apiUrl("/api/growth/festivals")),
        fetch(apiUrl("/api/console/catalog?limit=500")),
        fetch(apiUrl("/api/catalog/seasonal-context")),
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

      const sData = seasonRes.ok ? await seasonRes.json() : {};
      setSeasonalContext(sData);
    } catch {
      toast.error("Failed to load campaign studio data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

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
        toast.success("Environmental & seasonal boosts recalculated across store catalog!");
        loadData();
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
      }
    } catch {
      toast.error("Failed to create campaign");
    }
  };

  const handleDelete = async (festId: number) => {
    if (!confirm("Are you sure you want to delete this custom campaign?")) return;
    try {
      const res = await fetch(apiUrl(`/api/growth/festivals/${festId}`), {
        method: "DELETE",
      });
      if (res.ok) {
        toast.success("Campaign deleted");
        loadData();
      }
    } catch {
      toast.error("Failed to delete campaign");
    }
  };

  // Filtered campaigns
  const filteredFestivals = festivals.filter((fest) => {
    const nameMatch = fest.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (Array.isArray(fest.categories) && fest.categories.some((c: string) => c.toLowerCase().includes(searchQuery.toLowerCase())));

    if (!nameMatch) return false;

    if (statusFilter === "active") {
      return fest.status === "ongoing" && fest.is_active !== 0;
    }
    if (statusFilter === "upcoming") {
      return fest.status === "upcoming" && fest.is_active !== 0;
    }
    if (statusFilter === "custom") {
      return fest.id > 11;
    }
    return true;
  });

  const activeCount = festivals.filter((f) => f.status === "ongoing" && f.is_active !== 0).length;
  const upcomingCount = festivals.filter((f) => f.status === "upcoming" && f.is_active !== 0).length;

  return (
    <div className="space-y-4">
      {/* Top Senses & Metrics Grid (3 Balanced Cards) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Active Campaigns */}
        <div className="p-4 rounded-2xl bg-white border border-[#ebeaf0] shadow-sm flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-xl bg-[#efeaff] text-violet flex items-center justify-center shrink-0">
            <Sparkles size={20} />
          </div>
          <div>
            <div className="text-[11px] font-bold text-muted uppercase tracking-wider">Active Campaigns</div>
            <div className="text-xl font-bold font-display text-ink flex items-center gap-2">
              <span>{activeCount} Live</span>
              {activeCount > 0 && <span className="w-2 h-2 rounded-full bg-emerald animate-pulse" />}
            </div>
            <div className="text-[11px] text-muted">{upcomingCount} upcoming on annual calendar</div>
          </div>
        </div>

        {/* Environmental Season */}
        <div className="p-4 rounded-2xl bg-white border border-[#ebeaf0] shadow-sm flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-xl bg-[#e6fbf2] text-emerald flex items-center justify-center shrink-0">
            <CloudSun size={20} />
          </div>
          <div>
            <div className="text-[11px] font-bold text-muted uppercase tracking-wider">Environmental Season</div>
            <div className="text-sm font-bold text-ink truncate max-w-[180px]">
              {seasonalContext.season_label || seasonalContext.season || "Monsoon Season"}
            </div>
            <div className="text-[11px] text-muted">
              {seasonalContext.weather?.temp_celsius || 28}°C · {seasonalContext.weather?.city || "Delhi"}
            </div>
          </div>
        </div>

        {/* Catalog Coverage */}
        <div className="p-4 rounded-2xl bg-white border border-[#ebeaf0] shadow-sm flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-xl bg-[#fff4eb] text-orange flex items-center justify-center shrink-0">
            <Layers size={20} />
          </div>
          <div>
            <div className="text-[11px] font-bold text-muted uppercase tracking-wider">Catalog Coverage</div>
            <div className="text-xl font-bold font-display text-ink">
              {allCategories.length} Categories
            </div>
            <div className="text-[11px] text-muted">Dense MiniLM semantic theme alignments</div>
          </div>
        </div>
      </div>

      {/* Top Action Toolbar (Search & Action Buttons) */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-3 bg-white rounded-2xl border border-[#ebeaf0] shadow-sm">
        <div className="relative flex-1 sm:max-w-md">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            type="text"
            placeholder="Search campaigns or categories..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full h-9 pl-9 pr-3 bg-[#f8f8fb] border border-[#ebeaf0] rounded-xl text-xs outline-none focus:border-violet"
          />
        </div>

        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => setShowAddForm(!showAddForm)}
            className="px-3.5 py-2 rounded-xl bg-violet text-white text-xs font-bold hover:bg-violet/90 flex items-center gap-1.5 shadow-sm transition-all whitespace-nowrap shrink-0"
          >
            <Plus size={14} />
            <span>{showAddForm ? "Close Form" : "New Sale Campaign"}</span>
          </button>

          <button
            type="button"
            disabled={recalculating}
            onClick={handleRecalculate}
            className="px-3.5 py-2 rounded-xl bg-white border border-[#ebeaf0] text-ink text-xs font-bold hover:bg-[#faf9fd] flex items-center gap-1.5 shadow-sm transition-all disabled:opacity-50 whitespace-nowrap shrink-0"
          >
            <RefreshCw size={14} className={recalculating ? "animate-spin text-violet" : ""} />
            <span>{recalculating ? "Recalculating..." : "Recalculate Store Lifts"}</span>
          </button>
        </div>
      </div>

      {/* Inline Create Form */}
      {showAddForm && (
        <form
          onSubmit={handleCreateFestival}
          className="p-6 rounded-2xl bg-white border border-violet/30 shadow-md space-y-4 animate-in fade-in slide-in-from-top-3"
        >
          <div className="flex items-center justify-between pb-3 border-b border-[#f4f3f8]">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#efeaff] text-violet flex items-center justify-center">
                <Plus size={15} />
              </div>
              <div>
                <h3 className="font-display text-sm font-bold text-ink">Create Custom Promotional Campaign</h3>
                <p className="text-xs text-muted">Configure a special sales event, seasonal clearance, or festival window.</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setShowAddForm(false)}
              className="text-muted hover:text-ink text-xs font-bold"
            >
              Cancel
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold text-ink mb-1.5">
                Campaign Name <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                placeholder="e.g. Monsoon Clearance Flash Sale"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="w-full h-10 px-3 border border-[#ebeaf0] rounded-xl text-xs outline-none focus:border-violet bg-white"
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-bold text-ink mb-1.5">Start Month (1-12)</label>
                <input
                  type="number"
                  min="1"
                  max="12"
                  value={newMonth}
                  onChange={(e) => setNewMonth(Number(e.target.value))}
                  className="w-full h-10 px-3 border border-[#ebeaf0] rounded-xl text-xs outline-none focus:border-violet bg-white"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-ink mb-1.5">Start Day (1-31)</label>
                <input
                  type="number"
                  min="1"
                  max="31"
                  value={newDay}
                  onChange={(e) => setNewDay(Number(e.target.value))}
                  className="w-full h-10 px-3 border border-[#ebeaf0] rounded-xl text-xs outline-none focus:border-violet bg-white"
                  required
                />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-bold text-ink mb-1.5">Duration (Days)</label>
                <input
                  type="number"
                  min="1"
                  max="60"
                  value={newDuration}
                  onChange={(e) => setNewDuration(Number(e.target.value))}
                  className="w-full h-10 px-3 border border-[#ebeaf0] rounded-xl text-xs outline-none focus:border-violet bg-white"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-ink mb-1.5">RecSys Lift Multiplier</label>
                <div className="relative">
                  <input
                    type="number"
                    step="0.05"
                    min="1.0"
                    max="2.5"
                    value={newLift}
                    onChange={(e) => setNewLift(Number(e.target.value))}
                    className="w-full h-10 pl-3 pr-7 border border-[#ebeaf0] rounded-xl text-xs font-bold outline-none focus:border-violet bg-white"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted font-bold">×</span>
                </div>
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-ink mb-1.5">
                Commercial Intent Themes (Comma separated)
              </label>
              <input
                type="text"
                placeholder="e.g. rain_gear, tea_snacks, indoor_cooking, waterproof"
                value={newThemesStr}
                onChange={(e) => setNewThemesStr(e.target.value)}
                className="w-full h-10 px-3 border border-[#ebeaf0] rounded-xl text-xs outline-none focus:border-violet bg-white"
              />
            </div>
          </div>

          {/* Searchable Multi-Select Category Dropdown */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-xs font-bold text-ink">
                Direct Target Categories (Multiple Select)
              </label>
              <span className="text-[11px] text-muted">
                {newSelectedCategories.length} selected / {allCategories.length} available
              </span>
            </div>
            <CategoryMultiSelectDropdown
              allCategories={allCategories}
              selectedCategories={newSelectedCategories}
              onChange={setNewSelectedCategories}
              placeholder="Search & select specific categories to target (optional — leave empty for AI auto-match)..."
            />
            <p className="text-[11px] text-muted mt-1.5">
              💡 <strong>Smart Hybrid:</strong> You can select exact categories via the dropdown, or leave it empty to let the dense MiniLM AI match your intent themes automatically across your live inventory.
            </p>
          </div>

          <div className="flex justify-end gap-2.5 pt-2">
            <button
              type="button"
              onClick={() => setShowAddForm(false)}
              className="px-4 py-2 rounded-xl text-xs font-bold text-muted hover:text-ink bg-[#f4f3f8]"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-5 py-2 rounded-xl bg-violet text-white text-xs font-bold hover:bg-violet/90 shadow-sm"
            >
              Save Campaign
            </button>
          </div>
        </form>
      )}

      {/* Campaign Events Section with Filter Tabs Positioned Below */}
      <div className="bg-[#faf9fd]/50 p-3 sm:p-4 rounded-2xl border border-[#ebeaf0] space-y-3">
        {/* Filter Tabs Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-[#ebeaf0]/80">
          <div className="flex items-center gap-1.5 overflow-x-auto py-0.5">
            {[
              { id: "all", label: `All Events (${festivals.length})` },
              { id: "active", label: `Active Now (${activeCount})` },
              { id: "upcoming", label: `Upcoming (${upcomingCount})` },
              { id: "custom", label: "Custom Campaigns" },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setStatusFilter(tab.id as any)}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-bold whitespace-nowrap transition-all ${
                  statusFilter === tab.id
                    ? "bg-violet text-white shadow-sm"
                    : "bg-white text-muted hover:text-ink border border-[#ebeaf0]"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <span className="text-[11px] text-muted shrink-0 hidden sm:inline">
            Showing {filteredFestivals.length} of {festivals.length} events
          </span>
        </div>

        {/* Scrollable Campaigns Box */}
        <div className="max-h-[calc(100vh-360px)] min-h-[400px] overflow-y-auto pr-1.5 space-y-3">
          {loading ? (
            <div className="text-center py-20 text-muted text-xs flex flex-col items-center justify-center gap-2">
              <RefreshCw size={20} className="animate-spin text-violet" />
              <span>Evaluating inventory vectors and festival calendars...</span>
            </div>
          ) : filteredFestivals.length === 0 ? (
            <div className="text-center py-20 bg-white rounded-2xl border border-[#ebeaf0] text-muted text-xs space-y-2">
              <Calendar size={24} className="mx-auto text-muted/50" />
              <div className="font-bold text-ink">No matching campaigns found</div>
              <p>Try adjusting your search query or status filter.</p>
            </div>
          ) : (
            filteredFestivals.map((fest: any) => {
              const isActive = fest.is_active !== 0 && fest.status !== "inactive";
              const isOngoing = fest.status === "ongoing";
              const daysAway = fest.days_away ?? 0;
              const cats = Array.isArray(fest.categories) ? fest.categories : [];
              const isEditingThis = editingFestId === fest.id;

              return (
                <div
                  key={fest.id || fest.name}
                  className={`p-4 sm:p-5 rounded-2xl border transition-all ${
                    isActive
                      ? isOngoing
                        ? "bg-[#fcfaff] border-violet/40 shadow-sm"
                        : "bg-white border-[#ebeaf0] hover:border-violet/30"
                      : "bg-[#fcfbfe] border-[#f0eff4] opacity-60"
                  }`}
                >
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-[#f4f3f8]">
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-3 h-3 rounded-full ${
                          isActive
                            ? isOngoing
                              ? "bg-emerald animate-pulse ring-4 ring-emerald/20"
                              : "bg-violet"
                            : "bg-muted/40"
                        }`}
                      />
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-display text-base font-bold text-ink">
                            {fest.name}
                          </h3>
                          <span
                            className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                              isOngoing
                                ? "bg-emerald/10 text-emerald"
                                : daysAway <= 7
                                ? "bg-amber-500/10 text-amber-600"
                                : "bg-[#f4f3f8] text-muted"
                            }`}
                          >
                            {isOngoing
                              ? `Active Now · ${fest.formatted_date} (${daysAway === 0 ? "Today" : `in ${daysAway}d`})`
                              : `${fest.formatted_date} (in ${daysAway}d)`}
                          </span>
                          {fest.id > 11 && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-violet/10 text-violet">
                              Custom Campaign
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-muted mt-0.5">
                          Peak Date: {fest.formatted_date} · Active Window: {fest.duration_days || 7} days
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 self-end md:self-auto flex-wrap">
                      <div className="flex items-center gap-1.5 bg-[#f8f8fb] px-3 py-1.5 rounded-xl border border-[#ebeaf0]">
                        <span className="text-[11px] text-muted font-medium">Lift:</span>
                        <span className="text-xs font-bold text-violet">
                          {fest.lift_multiplier || 1.35}×
                        </span>
                      </div>

                      <button
                        type="button"
                        onClick={() => handleToggleActive(fest)}
                        className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-colors ${
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
                        className="px-3 py-1.5 rounded-xl bg-[#f4f3f8] hover:bg-[#efeaff] text-muted hover:text-violet text-xs font-bold flex items-center gap-1.5 transition-colors"
                      >
                        <Sliders size={13} />
                        <span>{isEditingThis ? "Close Editor" : "Customize Categories"}</span>
                      </button>

                      {fest.id > 11 && (
                        <button
                          type="button"
                          onClick={() => handleDelete(fest.id)}
                          className="p-2 rounded-xl text-muted hover:text-rose-500 hover:bg-rose-50 transition-colors"
                          title="Delete custom campaign"
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Inline Category Editor */}
                  {isEditingThis ? (
                    <div className="pt-4 space-y-3 bg-[#fbf9ff] p-4 rounded-xl border border-violet/20 mt-3 animate-in fade-in">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-xs font-bold text-ink">
                            Select Categories for {fest.name}:
                          </div>
                          <div className="text-[11px] text-muted">
                            Overrides AI theme auto-matching for this specific festival.
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleSaveCustomCategories(fest.id, [])}
                          className="text-xs text-violet font-bold hover:underline"
                        >
                          Reset to AI Auto-Match
                        </button>
                      </div>

                      <CategoryMultiSelectDropdown
                        allCategories={allCategories}
                        selectedCategories={editingCustomCats}
                        onChange={setEditingCustomCats}
                        placeholder="Select target categories..."
                      />

                      <div className="flex justify-end gap-2 pt-1">
                        <button
                          type="button"
                          onClick={() => setEditingFestId(null)}
                          className="px-3 py-1.5 rounded-lg text-xs text-muted hover:text-ink bg-white border border-[#ebeaf0]"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => handleSaveCustomCategories(fest.id, editingCustomCats)}
                          className="px-4 py-1.5 rounded-lg bg-violet text-white text-xs font-bold hover:bg-violet/90"
                        >
                          Save Categories
                        </button>
                      </div>
                    </div>
                  ) : (
                    /* Matched Inventory Categories View */
                    <div className="pt-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[11px] font-bold uppercase tracking-wider text-muted flex items-center gap-1.5">
                          <Tag size={12} className="text-violet" />
                          {fest.custom_categories ? "Custom Category Overrides:" : "AI Auto-Matched Store Inventory Categories:"}
                        </span>
                        <span className="text-[11px] text-muted">
                          <strong>{cats.length}</strong> categories active in RecSys
                        </span>
                      </div>

                      {cats.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5">
                          {cats.map((c: string) => (
                            <span
                              key={c}
                              className="px-2.5 py-1 rounded-lg text-xs font-medium bg-[#f3f0ff] text-violet border border-violet/15 flex items-center gap-1.5"
                            >
                              <span>{c}</span>
                              <span className="text-[10px] text-emerald font-bold bg-emerald/10 px-1 py-0.2 rounded">
                                +{Math.round(((fest.lift_multiplier || 1.35) - 1) * 100)}%
                              </span>
                            </span>
                          ))}
                        </div>
                      ) : (
                        <div className="text-xs text-muted italic">
                          No direct category affinity in current inventory — items will receive standard baseline weight (1.0x).
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
