# 🛒 CartPilot: Explainable Agentic Commerce Platform

> **Autonomous AI Shopping Agents with Deterministic Guardrails, 4-Tier Hybrid Recommendations, Cryptographic Mandate Chains, and Merchant Autonomy Levers.**

---

## 🌟 Overview

**CartPilot** is an end-to-end explainable agentic commerce engine that empowers autonomous AI agents (via Web Chat and Model Context Protocol) to discover catalog products, construct policy-compliant carts, suggest high-lift cross-sells, and initiate secure Razorpay checkout links with full forensic auditability.

Unlike black-box AI chatbots, CartPilot enforces **cryptographic mandate chains** (`Intent Mandate` → `Cart Mandate` → `Payment Mandate`), evaluates **deterministic policy guardrails** in real-time, and provides merchants with granular control over AI autonomy, ranking boosts, category compatibility, and revenue recovery.

---

## 🚀 Key Architectural Pillars

### 1. 🛡️ Deterministic Guardrail Engine
- **Hard Spend Caps**: Real-time evaluation of user-specified budget ceilings before cart approval.
- **Prohibited Category Policies**: Configurable merchant policies preventing purchase of restricted items.
- **Reversibility & Explanations**: Intercepted carts provide actionable, plain-language reasoning and allow 1-click policy adjustments.

### 2. 🧠 4-Tier Hybrid Recommendation Engine
- **Tier 1 (Cold-Start Priors)**: LLM-synthesized Category Compatibility Graph with explicit human merchandising reasoning and merchant override controls.
- **Tier 2 (Behavioral Co-Purchase)**: Pure NumPy **Item2Vec** (Skip-Gram with Negative Sampling, 64-dimensional vectors trained over verified completed orders).
- **Tier 3 (Dense Semantic)**: 384-dimensional MiniLM-L6-v2 vector embeddings for semantic description matching.
- **Tier 4 (Business Velocity & Guardrails)**: Real-time stock gating, merchant promotion boosts (1.35x), and price-fit multipliers.

### 3. 📜 Cryptographic Mandate & Immutable Audit Ledger
- Every transaction produces a verifiable mandate chain:
  $$\text{Intent Mandate} \xrightarrow{\text{Guardrail Gate}} \text{Cart Mandate} \xrightarrow{\text{Razorpay Link}} \text{Payment Mandate} \xrightarrow{\text{Webhook}} \text{Settlement}$$
- **Full Forensic Timeline**: Inspect each step, error, recovery advice, and LLM reasoning event directly in the live dashboard.

### 4. 🔌 Model Context Protocol (MCP) Server
- Exposes standard MCP tools (`search_catalog`, `get_product`, `propose_cart`, `get_upsell_suggestions`, `checkout`, `get_order_audit_trail`) for native integration into **Claude Desktop**, **Cursor**, and other agent environments.

### 5. 💼 Merchant Growth & Autonomy Console
- **Real-time Revenue Telemetry**: AI Incremental Revenue attribution, Cart Recovery tracking, and idle cart revenue opportunities.
- **Next Best Actions (NBA)**: 1-click cart payment link recovery, SKU promotion boosts, and autonomous scheduled growth workflows.
- **Simulated Lift Benchmarking**: Live A/B preview comparing pure baseline rankings vs. CartPilot 4-tier hybrid ranking.

---

## 📁 Repository Structure

```
CartPilot/
├── backend/                        # Python FastAPI backend & agents
│   ├── main.py                     # FastAPI entrypoint, routes, and startup hooks
│   ├── mcp_server.py               # FastMCP Server (Claude Desktop & Cursor integration)
│   ├── db.py                       # SQLite database connection & initialization
│   ├── agents/                     # BuyerGraph, GrowthAgent, RecoveryAgent, ResolutionAgent
│   ├── api/                        # Routes for Checkout, Console, Growth, Webhooks
│   ├── engine/                     # Deterministic Guardrails, Mandates, & LLM Adapters
│   ├── integrations/               # Razorpay Order, Payment Link, & Refund client
│   └── recommendations/           # 4-Tier RecSys & Item2Vec neural training engine
│
├── cartpilot-merchant/             # Unified React + TypeScript + Vite SPA
│   ├── client/
│   │   └── src/
│   │       ├── pages/
│   │       │   ├── buyer/BuyerApp.tsx       # Interactive AI Buyer Storefront & Chat
│   │       │   ├── merchant/                # Merchant Growth Console & Rules Engine
│   │       │   ├── checkout/                # Razorpay Test Checkout Simulation (/pay)
│   │       │   ├── Home.tsx                 # Command Center & Forensic Audit Ledger
│   │       │   └── Auth.tsx                 # Role Switcher (Merchant / Buyer)
│   │       └── contexts/                    # AuthContext, ThemeContext
│   ├── package.json
│   └── vite.config.ts
│
├── docs/                           # Documentation Hub
│   ├── README.md                   # Master Documentation Index
│   ├── specs/                      # Buildathon specifications (00_ to 04_)
│   ├── architecture/               # Audit trail explanation & Azure deployment specs
│   └── scripts/                    # Merchant pitch & video presentation scripts
│
├── tests/                          # Automated Pytest validation test suite
├── ops/                            # Database migrations & verification scripts
├── requirements.txt                # Python backend dependencies
├── package.json                    # Root convenience workspace scripts
├── .env.example                    # Environment variable template
└── README.md                       # Documentation & setup guide
```

---

## 🛠️ Step-by-Step Setup Guide

### 1. Prerequisites
Ensure you have the following installed:
- **Python 3.10+**
- **Node.js 18+** and **npm**
- **Google Gemini API Key** (or OpenAI API Key)

---

### 2. Clone the Repository
```bash
git clone https://github.com/VishalDhariwal/CartPilot.git
cd CartPilot
```

---

### 3. Backend Setup

1. **Create and activate a virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and fill in your credentials:
   ```ini
    # Database Configuration (Enterprise PostgreSQL Native)
    DATABASE_URL=postgresql://localhost:5432/cartpilot

    # Razorpay API Credentials (or leave BYPASS_RAZORPAY=true for instant testing)
    RAZORPAY_KEY_ID=rzp_test_your_key_id
    RAZORPAY_KEY_SECRET=your_key_secret
    RAZORPAY_WEBHOOK_SECRET=your_webhook_secret
    BYPASS_RAZORPAY=true

    # AI LLM Provider Key (Google Gemini)
    GEMINI_API_KEY=your_gemini_api_key

    # Merchant Secret Key
    CARTPILOT_MERCHANT_KEY=cartpilot_merchant_secret_key_v1
    ```

4. **Initialize PostgreSQL Database Schema**:
   ```bash
   python3 backend/db.py
   ```
   Or migrate existing data from SQLite to PostgreSQL:
   ```bash
   python3 ops/migrate_sqlite_to_postgres.py
   ```

5. **Start the FastAPI Backend Server**:
   ```bash
   python3 -m uvicorn backend.main:app --reload --port 8000
   ```
   The backend API will be live at `http://127.0.0.1:8000`. Interactive Swagger API docs are available at `http://127.0.0.1:8000/docs`.

---

### 4. Catalog Ingestion & Onboarding Workflow

CartPilot features an autonomous, deployment-ready data ingestion engine:

- **Deployment Auto-Prompt**: When deployed with a clean PostgreSQL database, CartPilot automatically opens the **Database Catalog Ingestion** modal on first visit.
- **Option A — API Key Ingestion**:
  - Provide your store API key, supplier token, or DummyJSON API key.
  - The engine authenticates via HTTP headers, fetches products, generates 384-dimensional dense embeddings (`SentenceTransformer('all-MiniLM-L6-v2')`), and seeds category compatibility rules.
- **Option B — CSV File Upload**:
  - Upload any `.csv` catalog (columns: `sku, name, price, stock, category, merchant, description, image_url, tags`).
  - Includes real-time client-side preview and downloadable template (`/api/catalog/ingest/template`).
- **Option C — 1-Click Demo Seed**:
  - Instant one-click trigger to seed 194 rich e-commerce products for evaluators.
- **Live Status & Re-Ingestion**:
  - The Merchant Console top navigation bar features a live **PostgreSQL: Connected** badge with an **"Ingest Data"** button to upload new CSVs or re-sync with external APIs anytime.

---

### 4. Unified Frontend Setup

1. In a new terminal window, navigate to the `cartpilot-merchant/` directory:
   ```bash
   cd cartpilot-merchant
   npm install
   ```

2. **Start the Vite Dev Server**:
   ```bash
   npm run dev
   ```
   The unified frontend will be live at `http://localhost:5000` (or the port Vite provides). You can seamlessly toggle between the **Buyer Storefront** and **Merchant Console** via `/auth`, `/buyer`, or `/merchant`.

---

### 5. Running the MCP Server (Claude Desktop Integration)

CartPilot includes a native FastMCP server for Claude Desktop and Cursor.

1. Open your Claude Desktop configuration file:
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

2. Add the CartPilot server definition:
   ```json
   {
     "mcpServers": {
       "cartpilot": {
         "command": "/ABSOLUTE/PATH/TO/CartPilot/venv/bin/python",
         "args": [
           "/ABSOLUTE/PATH/TO/CartPilot/backend/mcp_server.py"
         ],
         "env": {
           "PYTHONPATH": "/ABSOLUTE/PATH/TO/CartPilot"
         }
       }
     }
   }
   ```
   *(Replace `/ABSOLUTE/PATH/TO/CartPilot` with your actual workspace path).*

3. Fully restart Claude Desktop (`Cmd + Q` and reopen). You will see the 🔌 **tools icon** active in Claude Desktop.

---

## 🧪 Testing & Verification

### Buyer Web Chat (`/`)
- Navigate to `http://localhost:5173/`.
- Type shopping queries (e.g. *"I want a pair of sunglasses and perfume for under ₹3000"*).
- Observe intent parsing, deterministic guardrail validation, recommended cross-sells, and 1-click Razorpay test payment links.

### Merchant Ledger & Audit Trail (`/audit`)
- Navigate to `http://localhost:5173/audit`.
- View the real-time breakdown of **Gross Order Volume**, **AI Growth Revenue**, **Settled Orders**, and **Guardrail Interceptions**.
- Click any order headline row to expand its item thumbnails, payment transaction IDs, and cryptographic audit log timeline.
- Filter by `Settled`, `AI Growth`, `Guardrail Intercepted`, `Refunded`, `🤖 MCP Agent`, or `🌐 Web Chat`.

### Merchant Growth Console (`/console`)
- Navigate to `http://localhost:5173/console`.
- Monitor **Next Best Actions (NBA)** with automated cart recovery and stock promotion.
- Inspect the **4-Tier Recommendation Architecture** and trigger **Layer 2 Item2Vec Neural Training** when order volume thresholds are met.

---

## 🚀 CI/CD & Azure Cloud Deployment

CartPilot includes automated, standalone GitHub Actions workflows for continuous integration, automated semantic release tagging, and container publishing to **Azure Container Registry (ACR)**:

- **`.github/workflows/ci.yml`**: Pre-merge gatekeeper running Python unit tests (`pytest`) and frontend build checks.
- **`.github/workflows/release-tag-on-merge.yml`**: Automatically generates sequential/semver release tags on merge to `main` and creates official GitHub Releases.
- **`.github/workflows/azure-container-publish.yml`**: Multi-stage Docker build pushing to your private Azure Container Registry with commit SHA, semver, and `latest` tags.

For complete step-by-step instructions on setting up your Azure Container Registry, configuring GitHub Secrets, and deploying to Azure Container Apps, see the [Azure CI/CD & Production Deployment Guide](docs/deployment/azure_cicd_setup.md).

---

## 🛡️ License

Built with ❤️ for explainable agentic commerce. Distributed under the MIT License.

