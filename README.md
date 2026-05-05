# Provera

**AI-Powered Medicare Fraud Detection System**

Provera combines graph-based machine learning with AI agents to identify fraud rings in Medicare provider networks. It detects coordinated fraud schemes through ownership patterns, shared addresses, and network analysis — before billing anomalies appear.

![ROC-AUC](https://img.shields.io/badge/ROC--AUC-0.91-brightgreen)
![Golden Set](https://img.shields.io/badge/Golden%20Set-7%2F7-brightgreen)
![Facilities](https://img.shields.io/badge/Facilities-11%2C090-blue)
![Communities](https://img.shields.io/badge/Communities-8%2C015-blue)

---

## The Problem

- Medicare loses **$60-100 billion annually** to fraud
- Home Health Agencies are the **#1 fraud vector** — $17B in improper payments (2023)
- Florida accounts for **40% of all Medicare fraud prosecutions** despite having only 7% of beneficiaries
- Traditional rule-based detection generates **90%+ false positives**

## Our Solution

Provera shifts from reactive billing analysis to **proactive structural detection**:

1. **Graph Analysis** — Model provider networks to find hidden connections
2. **ML Triage** — XGBoost classifier scores all 11K facilities instantly
3. **AI Investigation** — Claude agent generates human-readable investigation briefs
4. **DOJ Cross-Reference** — Catches behavioral fraud that structural analysis misses

---

## Architecture

```
DATA LAYER         CMS NPPES + LEIE + Medicare Billing + FL SunBiz + Provider Enrollment
     ↓
GRAPH LAYER        26K nodes, 38K edges → Louvain community detection (8,015 communities)
     ↓
ML LAYER           XGBoost (33 features) → ROC-AUC: 0.91, Precision@100: 85%
     ↓
AGENT LAYER        Red Flags (5 checks) → DOJ Cross-Ref → Claude Investigation
     ↓
OUTPUT             Classification (HIGH/MEDIUM/LOW/CLEARED) + Investigation Dossier
```

## Key Results

| Metric | Value |
|--------|-------|
| ROC-AUC | 0.91 |
| Precision @ Top 100 | 85% |
| Golden Set Accuracy | 7/7 (100%) |
| DOJ Cases Identified | 7/8 (87.5%) |
| Factual Accuracy | 100% |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Anthropic API key

### Backend
```bash
# Install dependencies
pip install -r requirements.txt

# Set API key
export ANTHROPIC_API_KEY=sk-ant-xxxxx

# Run API server
uvicorn api:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

---

## Demo Cases

### High Risk — Shell Company Ring (Community 1597)
- 4 facilities, 100% excluded from Medicare
- All at similar Miami addresses, entity ages < 3 years
- Classification: **HIGH**

### False Positive Detection (Community 170)
- 227 facilities under Kindred Healthcare
- ML score elevated due to size, but agent identifies legitimate PE-backed system
- Classification: **LOW**

### DOJ Cross-Reference (NPI 1710078084)
- USA Home Care Solution Agency
- ML score: 0.27 (below threshold)
- DOJ layer catches it: Vladimir Prieto's 2015 Miami takedown operation
- Classification: **HIGH**

---

## Project Structure

```
Provera/
├── api.py                 # FastAPI backend
├── src/
│   ├── agent/             # AI investigation agent
│   │   ├── orchestrator.py
│   │   ├── prompts/
│   │   └── tools/
│   ├── graph/             # Graph construction & features
│   ├── models/            # XGBoost training
│   └── evals/             # Evaluation framework
├── frontend/              # React + Tailwind UI
├── data/processed/        # Pre-processed parquet files
└── presentation/          # Slides, report, architecture docs
```

## Data Sources

| Source | Records | Purpose |
|--------|---------|---------|
| CMS NPPES | 11,090 | Provider identity |
| OIG LEIE | 298 | Ground truth (exclusions) |
| Medicare Billing | 11,090 | Billing behavior |
| FL SunBiz | Lookups | Entity age detection |
| Provider Enrollment | 27,002 | Ownership network |

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check |
| `GET /api/stats` | System statistics |
| `GET /api/communities/top` | Top risk communities |
| `GET /api/facility/{npi}` | Facility details |
| `GET /api/facility/{npi}/shap` | SHAP explanations |
| `POST /api/investigate/community/{id}` | Run full investigation |
| `POST /api/investigate/npi/{npi}` | Investigate by NPI |

---

## Deployment

### Railway (Recommended)

1. Push to GitHub
2. Deploy backend from repo root
3. Deploy frontend from `frontend/` directory
4. Set environment variables:
   - Backend: `ANTHROPIC_API_KEY`
   - Frontend: `VITE_API_URL`

See [DEPLOY.md](DEPLOY.md) for detailed instructions.

### Docker

```bash
docker build -t provera .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-xxx provera
```

---

## Limitations

**What we detect (Structural Fraud):**
- Shell company networks
- Address-sharing schemes
- Ownership concentration
- Connections to excluded providers

**What we cannot detect (Behavioral Fraud):**
- Kickback schemes (requires referral data)
- Phantom billing (requires claims-level detail)
- Upcoding (requires procedure-level analysis)

This is why we added the DOJ cross-reference layer — it catches behavioral fraud that structural analysis misses.

---

## Authors

**Nikita Ravi** & **Jagannath Narayanswamy**

Data Analytics Capstone | Spring 2026
George Washington University

---

## License

MIT License - See [LICENSE](LICENSE) for details.
