# Provera: AI-Powered Medicare Fraud Detection
## Using Hybrid ML + Agentic AI for Provider Network Analysis

**Data Analytics Capstone - Spring 2026**
**George Washington University**

---

# Slide 1: The Problem

## Medicare Fraud: A $100B+ Annual Problem

**Scale of the Problem:**
- Medicare loses **$60-100 billion annually** to fraud, waste, and abuse
- Home Health Agencies (HHAs) are the **#1 fraud vector** - $17B in improper payments (2023)
- Florida accounts for **40% of all Medicare fraud prosecutions** despite having only 7% of beneficiaries

**Why Current Detection Fails:**
- Rule-based systems generate **90%+ false positives**
- Fraud rings operate across **multiple shell companies** that appear independent
- By the time billing anomalies trigger alerts, **millions have already been stolen**

**Our Approach:**
- Detect fraud **structurally** through ownership networks, not just billing patterns
- Use **graph ML** to find hidden connections between seemingly independent facilities
- Deploy **AI agents** to investigate and explain findings with human-readable reports

---

# Slide 2: Evolution of Our Architecture

## From Simple ML to Hybrid Agentic System

```
ITERATION 1: Baseline ML (Week 1-2)
├── XGBoost on billing features only
├── ROC-AUC: 0.72
└── Problem: High false positives, no explainability

ITERATION 2: + Graph Features (Week 3)
├── Added network centrality, community detection
├── ROC-AUC: 0.81
└── Problem: Flagged legitimate hospital systems

ITERATION 3: + Ownership Analysis (Week 4)
├── Linked facilities through shared owners/addresses
├── ROC-AUC: 0.87
└── Problem: Still couldn't explain WHY something was flagged

ITERATION 4: + AI Agent Layer (Week 5-6)
├── Claude-powered investigation agent
├── Hypothesis generation, evidence evaluation
├── 7/7 golden set accuracy
└── Human-readable investigation briefs
```

**Key Insight:** Each layer addressed limitations of the previous one.

---

# Slide 3: Final System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA LAYER                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │  NPPES   │ │   LEIE   │ │ Medicare │ │  SunBiz  │           │
│  │ Provider │ │Exclusions│ │ Billing  │ │Corporate │           │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
│       └────────────┴────────────┴────────────┘                  │
│                           │                                      │
├───────────────────────────▼──────────────────────────────────────┤
│                      GRAPH LAYER                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Provider Network Graph (11,090 nodes, 38,000 edges)   │    │
│  │  Edge Types: ownership, address, phone, billing         │    │
│  │  Community Detection: Louvain (8,015 communities)       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
├───────────────────────────▼──────────────────────────────────────┤
│                       ML LAYER                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  XGBoost Classifier (30+ features)                      │    │
│  │  ROC-AUC: 0.91 | Precision@100: 85%                     │    │
│  │  SHAP Explainability for each prediction                │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
├───────────────────────────▼──────────────────────────────────────┤
│                    AI AGENT LAYER                                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  FraudInvestigator (Claude 3.5 Sonnet)                  │    │
│  │  ├── Red Flag Checklist (5 automated checks)           │    │
│  │  ├── DOJ Records Cross-Reference                        │    │
│  │  ├── Hypothesis Generation (3 competing theories)       │    │
│  │  ├── Evidence Evaluation (support/refute each)          │    │
│  │  └── Investigation Brief (actionable report)            │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
├───────────────────────────▼──────────────────────────────────────┤
│                    OUTPUT LAYER                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Classification: HIGH / MEDIUM / LOW / CLEARED          │    │
│  │  Investigation Dossier with evidence chain              │    │
│  │  Recommended Actions for investigators                  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

# Slide 4: Data Pipeline & Feature Engineering

## Data Sources (Florida Focus)

| Source | Records | Key Fields |
|--------|---------|------------|
| CMS NPPES | 11,090 HHAs | NPI, name, address, phone |
| LEIE Exclusions | 298 excluded | Exclusion type, date, reason |
| Medicare Billing | 11,090 | Charges, payments, beneficiaries |
| FL SunBiz | Lookups | Incorporation date, status, principals |
| Provider Enrollment | 11,090 | Ownership %, association dates |

## Feature Categories (30+ Features)

**Billing Features:**
- Total charges, payments, beneficiaries
- Charges per beneficiary (state percentile)
- Payment-to-charge ratio

**Network Features:**
- PageRank, degree centrality, betweenness
- Clustering coefficient
- Community size, fraud density in community

**Ownership Features:**
- Owner count, max facilities per owner
- Shared address count, shared phone count
- Entity age (years since incorporation)

**Target Variable:** LEIE exclusion status (binary)

---

# Slide 5: Hybrid ML + AI Agent Approach

## Why Hybrid? Neither Alone is Sufficient

| Approach | Strengths | Weaknesses |
|----------|-----------|------------|
| **ML Only** | Fast, scalable, consistent | Black box, high false positives, no context |
| **Agent Only** | Explainable, contextual | Slow, expensive, inconsistent |
| **Hybrid** | Best of both worlds | Complexity in orchestration |

## Our Pipeline

```
1. ML TRIAGE (Fast, Cheap)
   └── XGBoost scores all 11,090 facilities
   └── Filters to top ~500 high-risk communities
   └── Cost: ~$0 (local inference)

2. RED FLAG ANALYSIS (Deterministic)
   └── 5 automated checks per community
   └── No LLM calls - pure rule-based
   └── Cost: ~$0

3. AI INVESTIGATION (Deep, Expensive)
   └── Only for communities with risk score > 0.3 OR flags > 0
   └── 3 LLM calls per investigation:
       - Hypothesis generation
       - Evidence evaluation
       - Narrative synthesis
   └── Cost: ~$0.03 per investigation

4. DOJ CROSS-REFERENCE (New Layer)
   └── Checks facility names against prosecution database
   └── Forces full investigation if match found
   └── Catches behavioral fraud ML might miss
```

---

# Slide 6: Five Case Types Demonstrated

## Case 1: Shell Company Network (Community 1597)
- **4 HHAs, 100% excluded**, all at similar Miami addresses
- ML Score: 0.94 | Red Flags: 5/5 | Classification: **HIGH**
- Agent identified: "Entity cycling to evade oversight"

## Case 2: Legitimate Hospital System (Community 170)
- **227 facilities** under Kindred Healthcare umbrella
- ML Score: 0.65 | Red Flags: 2/5 | Classification: **LOW**
- Agent identified: "PE-backed chain with legitimate infrastructure"

## Case 3: Established Nonprofit (Community 215)
- **52-year-old** organization, no exclusions
- ML Score: 0.45 | Red Flags: 0/5 | Classification: **CLEARED**
- Agent identified: "Long operational history rules out shell company"

## Case 4: DOJ-Prosecuted Facility (NPI 1851563381)
- Florida Patient Care Corp - **prosecuted for phantom billing**
- ML Score: 0.79 | Red Flags: 1/5 (DOJ match) | Classification: **HIGH**
- Research layer caught what structural analysis missed

## Case 5: False Positive Correction (Community 731)
- Doral office building with **5 HHAs, 1 excluded**
- ML Score: 0.72 | Initial: HIGH | Final: **MEDIUM**
- Agent identified legitimate co-location but flagged geographic risk

---

# Slide 7: Golden Set Evaluation (7/7)

## Curated Test Cases for Classification Accuracy

| Community | Type | Expected | Actual | Key Evidence |
|-----------|------|----------|--------|--------------|
| 1597 | Shell company ring | HIGH | HIGH | 4/4 excluded, entity cycling |
| 731 | Doral fraud corridor | MEDIUM+ | MEDIUM | 1/5 excluded, geographic risk |
| 215 | Established nonprofit | LOW | LOW | 52-year entity, no exclusions |
| 170 | PE healthcare chain | LOW | LOW | Kindred system, legitimate |
| 4446 | Mixed risk cluster | MEDIUM | MEDIUM | 2/6 excluded, shared owner |
| 5806 | Clean single facility | CLEARED | CLEARED | 0 flags, isolated |
| 5411 | New entity, clean | LOW | LOW | Recent but no red flags |

## Factual Accuracy: 100%
- All facility names correct
- All NPI numbers valid
- All exclusion statuses accurate
- All addresses verified

---

# Slide 8: Observability & Evaluation Layer

## How We Ensure Quality

**1. Structured Output Enforcement**
```python
# Agent must output in this exact format:
{
  "classification": "HIGH|MEDIUM|LOW|CLEARED",
  "hypotheses": "H1: ... H2: ... H3: ...",
  "evaluation": "H1: SUPPORTED/REFUTED because...",
  "narrative": "# INVESTIGATION BRIEF..."
}
```

**2. Red Flag Checklist (Deterministic)**
- Every investigation runs 5 automated checks BEFORE LLM
- Results injected into agent context
- Agent cannot contradict deterministic findings

**3. False Positive Detection**
- System prompt includes major healthcare system names
- Agent warned about HCA, Kindred, Solaris subsidiaries
- 30+ year entities cannot be called "shell companies"

**4. DOJ Cross-Reference Layer**
- Local database of 50+ prosecuted facilities/individuals
- Runs BEFORE triage to prevent false clears
- Forces full investigation on matches

**5. SHAP Explainability**
- Every ML prediction has feature attribution
- Top features shown to investigators
- Example: Community 1597 flagged for "shared_address_count: +1.04"

---

# Slide 9: Results & Limitations

## Performance Metrics

| Metric | Value |
|--------|-------|
| ML ROC-AUC | 0.91 |
| Precision @ 100 | 85% |
| Golden Set Accuracy | 7/7 (100%) |
| DOJ Cases Found | 7/8 (87.5%) |
| Factual Accuracy | 100% |
| Avg Investigation Time | 35 seconds |

## What We Detect (Structural Fraud)
- Shell company networks
- Address-sharing schemes
- Ownership concentration
- Connections to excluded providers

## What We Cannot Detect (Behavioral Fraud)
- Kickback schemes (requires referral data)
- Phantom billing (requires claims-level detail)
- Upcoding (requires procedure-level analysis)

**Honest Assessment:** 3/7 DOJ-prosecuted facilities would be flagged by structural analysis alone. The remaining 4 were prosecuted for kickbacks - invisible without claims data.

---

# Slide 10: Conclusion & Future Work

## Key Contributions

1. **Novel Architecture**: First hybrid ML + agentic system for Medicare fraud
2. **Graph-Based Detection**: Ownership networks reveal hidden fraud rings
3. **Explainable AI**: Every classification includes evidence chain
4. **DOJ Validation**: Tested against real prosecuted cases
5. **Production-Ready Tool**: React frontend for live investigations

## Scalability

| Current (Florida) | National Scale |
|-------------------|----------------|
| 11,090 providers | 1.2M+ providers |
| 8,015 communities | ~800K communities |
| $0.03/investigation | ~$36K for full national scan |

## Future Enhancements

1. **Claims Integration**: Add Medicare FFS claims for behavioral detection
2. **Temporal Analysis**: Track entity cycling over time
3. **Multi-State Expansion**: Apply to Texas, California, New York
4. **Real-Time Monitoring**: Alert on new high-risk registrations

---

## Thank You

**Provera** | Medicare Fraud Detection System
George Washington University | Data Analytics Capstone | Spring 2026

*Demo available at: http://localhost:5173*
