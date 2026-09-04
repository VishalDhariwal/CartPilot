import { useState, useEffect, useRef } from "react";
import {
  Database, Key, Upload, FileSpreadsheet, CheckCircle2, AlertCircle,
  RefreshCw, Download, Sparkles, X, Eye, EyeOff, Layers, ExternalLink,
  ShieldCheck, Server, ArrowRight
} from "lucide-react";
import { toast } from "sonner";

interface CatalogIngestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onIngestSuccess?: () => void;
  initialTab?: "api" | "csv" | "demo";
}

interface IngestStatus {
  database_engine: string;
  database_display: string;
  connected: boolean;
  product_count: number;
  category_count: number;
  categories: string[];
  embedded_count: number;
  is_empty: boolean;
  requires_ingestion: boolean;
}

export default function CatalogIngestModal({
  isOpen,
  onClose,
  onIngestSuccess,
  initialTab = "api"
}: CatalogIngestModalProps) {
  const [activeTab, setActiveTab] = useState<"api" | "csv" | "demo">(initialTab);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [status, setStatus] = useState<IngestStatus | null>(null);

  // API Key Form State
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [provider, setProvider] = useState("dummyjson");
  const [customEndpoint, setCustomEndpoint] = useState("");
  const [limit, setLimit] = useState(200);
  const [clearExistingApi, setClearExistingApi] = useState(false);
  const [submittingApi, setSubmittingApi] = useState(false);

  // CSV Upload State
  const [file, setFile] = useState<File | null>(null);
  const [csvPreview, setCsvPreview] = useState<string[][]>([]);
  const [csvHeaders, setCsvHeaders] = useState<string[]>([]);
  const [clearExistingCsv, setClearExistingCsv] = useState(false);
  const [submittingCsv, setSubmittingCsv] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Demo Seed State
  const [submittingDemo, setSubmittingDemo] = useState(false);

  // Result Banner
  const [lastResult, setLastResult] = useState<{
    type: "success" | "error";
    message: string;
    count?: number;
  } | null>(null);

  const fetchStatus = async () => {
    setLoadingStatus(true);
    try {
      const res = await fetch("/api/catalog/ingest/status");
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
      }
    } catch {
      // ignore
    } finally {
      setLoadingStatus(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchStatus();
      setLastResult(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  // Handle CSV file selection and client-side preview
  const handleFileChange = (selectedFile: File) => {
    if (!selectedFile.name.toLowerCase().endsWith(".csv")) {
      toast.error("Please select a valid CSV (.csv) file.");
      return;
    }
    setFile(selectedFile);
    setLastResult(null);

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      if (!text) return;
      const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
      if (lines.length > 0) {
        // Simple comma split preview
        const headers = lines[0].split(",").map((h) => h.trim().replace(/^["']|["']$/g, ""));
        setCsvHeaders(headers);
        const previewRows = lines.slice(1, 4).map((line) =>
          line.split(",").map((cell) => cell.trim().replace(/^["']|["']$/g, ""))
        );
        setCsvPreview(previewRows);
      }
    };
    reader.readAsText(selectedFile.slice(0, 10000));
  };

  // Submit API Key Ingestion
  const handleIngestApiKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey.trim()) {
      toast.error("Please enter a valid API Key to ingest data.");
      return;
    }

    setSubmittingApi(true);
    setLastResult(null);

    try {
      const res = await fetch("/api/catalog/ingest/api-key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: apiKey.trim(),
          provider,
          endpoint_url: customEndpoint.trim() || undefined,
          limit,
          clear_existing: clearExistingApi
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "API Key Ingestion failed.");
      }

      setLastResult({
        type: "success",
        message: data.message || `Successfully ingested ${data.count} items into PostgreSQL!`,
        count: data.count
      });
      toast.success(`Ingested ${data.count} items into PostgreSQL!`);
      fetchStatus();
      if (onIngestSuccess) onIngestSuccess();
    } catch (err: any) {
      setLastResult({
        type: "error",
        message: err.message || "Failed to ingest catalog via API Key."
      });
      toast.error(err.message || "Failed to ingest catalog via API Key.");
    } finally {
      setSubmittingApi(false);
    }
  };

  // Submit CSV Ingestion
  const handleIngestCsv = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      toast.error("Please choose a CSV file to upload.");
      return;
    }

    setSubmittingCsv(true);
    setLastResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("clear_existing", String(clearExistingCsv));

      const res = await fetch("/api/catalog/ingest/csv", {
        method: "POST",
        body: formData
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "CSV Ingestion failed.");
      }

      setLastResult({
        type: "success",
        message: data.message || `Successfully parsed and ingested ${data.count} products into PostgreSQL!`,
        count: data.count
      });
      toast.success(`Imported ${data.count} products from CSV into PostgreSQL!`);
      setFile(null);
      setCsvPreview([]);
      fetchStatus();
      if (onIngestSuccess) onIngestSuccess();
    } catch (err: any) {
      setLastResult({
        type: "error",
        message: err.message || "Failed to ingest CSV catalog."
      });
      toast.error(err.message || "Failed to ingest CSV catalog.");
    } finally {
      setSubmittingCsv(false);
    }
  };

  // Submit 1-Click Demo Seed
  const handleSeedDemo = async () => {
    setSubmittingDemo(true);
    setLastResult(null);

    try {
      const res = await fetch("/api/catalog/ingest/sample", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Demo seed failed.");

      setLastResult({
        type: "success",
        message: `Successfully seeded ${data.count} rich catalog products into PostgreSQL!`,
        count: data.count
      });
      toast.success(`Seeded ${data.count} demo products into PostgreSQL!`);
      fetchStatus();
      if (onIngestSuccess) onIngestSuccess();
    } catch (err: any) {
      setLastResult({
        type: "error",
        message: err.message || "Failed to seed demo catalog."
      });
      toast.error(err.message || "Failed to seed demo catalog.");
    } finally {
      setSubmittingDemo(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 overflow-y-auto animate-in fade-in duration-200">
      <div className="relative w-full max-w-2xl bg-white rounded-2xl shadow-2xl border border-border overflow-hidden my-8">
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-border/80 flex items-start justify-between bg-gradient-to-r from-slate-50 to-indigo-50/30">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                <Database size={12} className="text-emerald-600" />
                PostgreSQL Native
              </span>
              {status?.connected && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
                  <Server size={11} />
                  {status.product_count} SKUs Loaded
                </span>
              )}
            </div>
            <h2 className="text-xl font-bold tracking-tight text-slate-900">
              Database Catalog Ingestion
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Populate your PostgreSQL store database via live API Key authentication or bulk CSV upload.
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Database Status Callout */}
        <div className="px-6 py-2.5 bg-slate-50/80 border-b border-border/60 flex items-center justify-between text-xs text-slate-600">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="font-medium text-slate-700">Target Database:</span>
            <code className="px-1.5 py-0.5 bg-white border rounded text-[11px] font-mono text-indigo-700">
              {status?.database_display || "PostgreSQL (localhost:5432/cartpilot)"}
            </code>
          </div>
          <button
            onClick={fetchStatus}
            disabled={loadingStatus}
            className="flex items-center gap-1 text-slate-500 hover:text-slate-800 transition-colors"
            title="Refresh database stats"
          >
            <RefreshCw size={12} className={loadingStatus ? "animate-spin" : ""} />
            <span>Refresh</span>
          </button>
        </div>

        {/* Result Notification Banner */}
        {lastResult && (
          <div
            className={`mx-6 mt-4 p-3.5 rounded-xl border flex items-start gap-3 text-xs leading-relaxed ${
              lastResult.type === "success"
                ? "bg-emerald-50/90 border-emerald-200 text-emerald-900"
                : "bg-rose-50/90 border-rose-200 text-rose-900"
            }`}
          >
            {lastResult.type === "success" ? (
              <CheckCircle2 size={16} className="text-emerald-600 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle size={16} className="text-rose-600 shrink-0 mt-0.5" />
            )}
            <div className="flex-1">
              <span className="font-semibold block">
                {lastResult.type === "success" ? "Ingestion Successful" : "Ingestion Failed"}
              </span>
              <span>{lastResult.message}</span>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex border-b border-border px-6 pt-3 gap-2 bg-white">
          <button
            onClick={() => { setActiveTab("api"); setLastResult(null); }}
            className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold border-b-2 transition-all cursor-pointer ${
              activeTab === "api"
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <Key size={14} />
            API Key Ingestion
          </button>
          <button
            onClick={() => { setActiveTab("csv"); setLastResult(null); }}
            className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold border-b-2 transition-all cursor-pointer ${
              activeTab === "csv"
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <FileSpreadsheet size={14} />
            Upload CSV File
          </button>
          <button
            onClick={() => { setActiveTab("demo"); setLastResult(null); }}
            className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold border-b-2 transition-all cursor-pointer ${
              activeTab === "demo"
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <Sparkles size={14} />
            Quick Demo Seed
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6">
          {/* TAB 1: API Key Ingestion */}
          {activeTab === "api" && (
            <form onSubmit={handleIngestApiKey} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Store or Provider API Key <span className="text-rose-500">*</span>
                </label>
                <div className="relative">
                  <input
                    type={showApiKey ? "text" : "password"}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="e.g. cp_live_sec_prod_9f82ab... or Bearer token"
                    required
                    className="w-full text-xs font-mono px-3 py-2.5 pr-10 border border-slate-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-1"
                  >
                    {showApiKey ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
                <p className="text-[11px] text-slate-400 mt-1">
                  The API key will be transmitted via secure Authorization headers to fetch and authenticate the store catalog.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                    Data Provider / Protocol
                  </label>
                  <select
                    value={provider}
                    onChange={(e) => setProvider(e.target.value)}
                    className="w-full text-xs px-3 py-2 border border-slate-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none bg-white"
                  >
                    <option value="dummyjson">DummyJSON Live E-Commerce Catalog</option>
                    <option value="custom_api">Custom REST Store API Endpoint</option>
                    <option value="mock_erp">Enterprise ERP / Supplier Gateway</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                    Product Limit
                  </label>
                  <input
                    type="number"
                    min="10"
                    max="500"
                    value={limit}
                    onChange={(e) => setLimit(parseInt(e.target.value) || 200)}
                    className="w-full text-xs px-3 py-2 border border-slate-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
                  />
                </div>
              </div>

              {provider === "custom_api" && (
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                    Custom Endpoint URL <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="url"
                    value={customEndpoint}
                    onChange={(e) => setCustomEndpoint(e.target.value)}
                    placeholder="https://api.yourstore.com/v1/products"
                    required={provider === "custom_api"}
                    className="w-full text-xs px-3 py-2 border border-slate-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
                  />
                </div>
              )}

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="clearApi"
                  checked={clearExistingApi}
                  onChange={(e) => setClearExistingApi(e.target.checked)}
                  className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                <label htmlFor="clearApi" className="text-xs text-slate-600 select-none cursor-pointer">
                  Replace all existing products in PostgreSQL (truncate catalog table before ingest)
                </label>
              </div>

              <div className="pt-2 flex justify-end gap-2.5">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-xl transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingApi}
                  className="flex items-center gap-2 px-5 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded-xl shadow-xs transition-all cursor-pointer"
                >
                  {submittingApi ? (
                    <>
                      <RefreshCw size={14} className="animate-spin" />
                      Authenticating & Ingesting...
                    </>
                  ) : (
                    <>
                      <Key size={14} />
                      Authenticate & Ingest from API
                    </>
                  )}
                </button>
              </div>
            </form>
          )}

          {/* TAB 2: CSV Upload */}
          {activeTab === "csv" && (
            <form onSubmit={handleIngestCsv} className="space-y-4">
              {/* Drag and drop zone */}
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                    handleFileChange(e.dataTransfer.files[0]);
                  }
                }}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-2xl p-6 text-center cursor-pointer transition-all ${
                  dragOver
                    ? "border-indigo-500 bg-indigo-50/50"
                    : file
                    ? "border-emerald-500 bg-emerald-50/30"
                    : "border-slate-300 hover:border-slate-400 bg-slate-50/50"
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      handleFileChange(e.target.files[0]);
                    }
                  }}
                />
                <div className="w-10 h-10 mx-auto rounded-xl bg-indigo-100 text-indigo-700 flex items-center justify-center mb-2">
                  <Upload size={20} />
                </div>
                {file ? (
                  <div>
                    <span className="text-xs font-bold text-slate-800 block">
                      {file.name}
                    </span>
                    <span className="text-[11px] text-slate-500">
                      {(file.size / 1024).toFixed(1)} KB &bull; Click or drop another file to replace
                    </span>
                  </div>
                ) : (
                  <div>
                    <span className="text-xs font-semibold text-slate-700 block">
                      Click to choose CSV or drag & drop file here
                    </span>
                    <span className="text-[11px] text-slate-400">
                      Supports standard columns: sku, name, price, stock, category, merchant, image_url, description
                    </span>
                  </div>
                )}
              </div>

              {/* Sample CSV preview */}
              {csvPreview.length > 0 && (
                <div className="border rounded-xl p-3 bg-slate-50/60 overflow-hidden text-xs">
                  <span className="font-semibold text-slate-700 block mb-1 text-[11px]">
                    Previewing First {csvPreview.length} Rows:
                  </span>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-[11px] border-collapse">
                      <thead>
                        <tr className="border-b text-slate-500 font-mono">
                          {csvHeaders.slice(0, 5).map((h, i) => (
                            <th key={i} className="py-1 px-2 whitespace-nowrap">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {csvPreview.map((row, idx) => (
                          <tr key={idx} className="border-b border-slate-200/60 text-slate-700">
                            {row.slice(0, 5).map((cell, cIdx) => (
                              <td key={cIdx} className="py-1 px-2 max-w-[120px] truncate whitespace-nowrap">
                                {cell}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Download Template & Clear toggle */}
              <div className="flex items-center justify-between pt-1">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="clearCsv"
                    checked={clearExistingCsv}
                    onChange={(e) => setClearExistingCsv(e.target.checked)}
                    className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <label htmlFor="clearCsv" className="text-xs text-slate-600 select-none cursor-pointer">
                    Replace existing products in PostgreSQL
                  </label>
                </div>
                <a
                  href="/api/catalog/ingest/template"
                  download="cartpilot_sample_catalog.csv"
                  className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium transition-colors"
                >
                  <Download size={12} />
                  Download Sample CSV
                </a>
              </div>

              <div className="pt-2 flex justify-end gap-2.5">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-xl transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!file || submittingCsv}
                  className="flex items-center gap-2 px-5 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded-xl shadow-xs transition-all cursor-pointer"
                >
                  {submittingCsv ? (
                    <>
                      <RefreshCw size={14} className="animate-spin" />
                      Parsing & Ingesting to PostgreSQL...
                    </>
                  ) : (
                    <>
                      <Upload size={14} />
                      Import CSV to PostgreSQL
                    </>
                  )}
                </button>
              </div>
            </form>
          )}

          {/* TAB 3: 1-Click Demo Seed */}
          {activeTab === "demo" && (
            <div className="space-y-4 text-center py-2">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-indigo-500 to-violet-600 text-white flex items-center justify-center mx-auto shadow-md">
                <Sparkles size={24} />
              </div>
              <div className="max-w-md mx-auto">
                <h3 className="text-sm font-bold text-slate-900 mb-1">
                  Instant Production Catalog Seed
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed">
                  Quickly seed 194 enterprise e-commerce products across 28 categories with authentic images, rich metadata, 384-d dense vector embeddings, and autonomous cross-sell compatibility rules into PostgreSQL.
                </p>
              </div>

              <div className="grid grid-cols-3 gap-2.5 text-left max-w-md mx-auto py-2">
                <div className="p-2.5 rounded-xl border bg-slate-50/70">
                  <span className="text-[10px] text-slate-400 font-medium uppercase block">Products</span>
                  <span className="text-base font-bold text-slate-800">194 SKUs</span>
                </div>
                <div className="p-2.5 rounded-xl border bg-slate-50/70">
                  <span className="text-[10px] text-slate-400 font-medium uppercase block">Categories</span>
                  <span className="text-base font-bold text-slate-800">28 Types</span>
                </div>
                <div className="p-2.5 rounded-xl border bg-slate-50/70">
                  <span className="text-[10px] text-slate-400 font-medium uppercase block">Embeddings</span>
                  <span className="text-base font-bold text-indigo-700">384-Dim</span>
                </div>
              </div>

              <div className="pt-2 flex justify-center gap-2.5">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-xl transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSeedDemo}
                  disabled={submittingDemo}
                  className="flex items-center gap-2 px-6 py-2 text-xs font-semibold text-white bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 disabled:opacity-50 rounded-xl shadow-xs transition-all cursor-pointer"
                >
                  {submittingDemo ? (
                    <>
                      <RefreshCw size={14} className="animate-spin" />
                      Seeding PostgreSQL Database...
                    </>
                  ) : (
                    <>
                      <Sparkles size={14} />
                      Seed Demo Catalog into PostgreSQL
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
