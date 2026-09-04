# 📚 CartPilot Documentation Hub

Welcome to the **CartPilot** technical documentation and specifications repository.

---

## 📂 Documentation Directory Map

```
docs/
├── specs/                   # Core Buildathon requirements & specifications
│   ├── 00_PROJECT_BRIEF.md
│   ├── 01_ARCHITECTURE_AND_DATA_MODEL.md
│   ├── 02_BUILD_PHASES_AND_TASKS.md
│   ├── 03_RAZORPAY_TESTMODE_REFERENCE.md
│   └── 04_VERIFICATION_CHECKLIST.md
│
├── architecture/            # Deep-dive architectural design documents
│   ├── audit_trail_explanation.md
│   └── azure_deployment_specification.md
│
└── scripts/                 # Walkthrough & video recording scripts
    ├── merchant_video_script.md
    ├── audit_trail_spoken_script.md
    └── merchant_console_overview_script.md
```

---

## 📑 1. Core Specifications (`docs/specs/`)

| Specification Document | Description |
|:---|:---|
| [00_PROJECT_BRIEF.md](./specs/00_PROJECT_BRIEF.md) | High-level problem statement, Razorpay Buildathon track alignment, and non-negotiables. |
| [01_ARCHITECTURE_AND_DATA_MODEL.md](./specs/01_ARCHITECTURE_AND_DATA_MODEL.md) | Data schemas (SQLite), mandate chain definitions, and system interaction flows. |
| [02_BUILD_PHASES_AND_TASKS.md](./specs/02_BUILD_PHASES_AND_TASKS.md) | Phased build roadmap and milestone completion deliverables. |
| [03_RAZORPAY_TESTMODE_REFERENCE.md](./specs/03_RAZORPAY_TESTMODE_REFERENCE.md) | Razorpay Orders, Payment Links, Webhooks, and test-card simulation references. |
| [04_VERIFICATION_CHECKLIST.md](./specs/04_VERIFICATION_CHECKLIST.md) | End-to-end verification checklist and acceptance criteria. |

---

## 🏛️ 2. Architectural Deep-Dives (`docs/architecture/`)

| Architecture Guide | Description |
|:---|:---|
| [audit_trail_explanation.md](./architecture/audit_trail_explanation.md) | Deep dive into SHA-256 hash-chained mandate ledgers and forensic auditability. |
| [azure_deployment_specification.md](./architecture/azure_deployment_specification.md) | Enterprise deployment specs for Azure App Service, Azure PostgreSQL, and Container Apps. |

---

## 🎙️ 3. Presentation & Demo Scripts (`docs/scripts/`)

| Script | Duration | Focus Area |
|:---|:---|:---|
| [merchant_video_script.md](./scripts/merchant_video_script.md) | 5–7 min | Master video recording script with live navigation cues. |
| [audit_trail_spoken_script.md](./scripts/audit_trail_spoken_script.md) | ~2 min | Focused pitch script explaining mandate chains & forensic audit trail. |
| [merchant_console_overview_script.md](./scripts/merchant_console_overview_script.md) | ~2 min | Spoken walkthrough of the Merchant Growth Console and rules engine. |
