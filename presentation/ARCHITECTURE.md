# Provera System Architecture
## Complete End-to-End Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                                         │
│                                    P R O V E R A   A R C H I T E C T U R E                              │
│                                    Medicare Fraud Detection System                                       │
│                                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════════════════════════════════
 LAYER 1: DATA INGESTION
═══════════════════════════════════════════════════════════════════════════════════════════════════════════

    ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
    │   CMS NPPES  │   │   OIG LEIE   │   │   Medicare   │   │  FL SunBiz   │   │   Provider   │
    │              │   │              │   │   Billing    │   │  Corporate   │   │  Enrollment  │
    │  11,090 FL   │   │ 298 Excluded │   │   11,090     │   │  Entity Age  │   │   27,002     │
    │  (HHA+SNF)   │   │              │   │              │   │   Lookups    │   │   Links      │
    └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
           │                  │                  │                  │                  │
           │    Provider      │   Ground Truth   │    Billing       │   Entity Age     │   Ownership
           │    Identity      │   Labels         │    Behavior      │   Shell Detect   │   Network
           │                  │                  │                  │                  │
           └────────────────────────────────────┬┴─────────────────────────────────────┘
                                                │
                                                ▼
                              ┌─────────────────────────────────────┐
                              │      ETL & NORMALIZATION            │
                              │  ─────────────────────────────────  │
                              │  • Address standardization          │
                              │  • Phone normalization (10-digit)   │
                              │  • Entity resolution (NPI + fuzzy)  │
                              │  • Date parsing & age calculation   │
                              └─────────────────┬───────────────────┘
                                                │
                                                ▼
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
 LAYER 2: GRAPH CONSTRUCTION
═══════════════════════════════════════════════════════════════════════════════════════════════════════════

                              ┌─────────────────────────────────────┐
                              │       ENTITY CREATION               │
                              └─────────────────┬───────────────────┘
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    │                           │                           │
                    ▼                           ▼                           ▼
          ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
          │    FACILITY     │         │     OWNER       │         │ ADDRESS / PHONE │
          │     NODES       │         │     NODES       │         │     NODES       │
          │   (11,090)      │         │   (5,854)       │         │  (9,800+)       │
          │                 │         │                 │         │                 │
          │ • npi           │         │ • owner_id      │         │ • address_hash  │
          │ • name          │         │ • name          │         │ • phone_number  │
          │ • risk_score    │         │ • type          │         │ • facility_count│
          │ • is_excluded   │         │ • facility_count│         │                 │
          └────────┬────────┘         └────────┬────────┘         └────────┬────────┘
                   │                           │                           │
                   └───────────────────────────┼───────────────────────────┘
                                               │
                                               ▼
                              ┌─────────────────────────────────────┐
                              │       EDGE CREATION                 │
                              └─────────────────┬───────────────────┘
                                                │
          ┌─────────────────────────────────────┼─────────────────────────────────────┐
          │                     │               │               │                     │
          ▼                     ▼               ▼               ▼                     ▼
   ┌─────────────┐       ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       ┌─────────────┐
   │    OWNS     │       │ LOCATED_AT  │ │  HAS_PHONE  │ │   SHARES    │       │   SHARES    │
   │  (27,002)   │       │  (11,090)   │ │  (11,090)   │ │   ADDRESS   │       │   OWNER     │
   │             │       │             │ │             │ │  (3,170)    │       │  (35,122)   │
   │ OWNER →     │       │ FACILITY →  │ │ FACILITY →  │ │ FACILITY ↔  │       │ FACILITY ↔  │
   │ FACILITY    │       │ ADDRESS     │ │ PHONE       │ │ FACILITY    │       │ FACILITY    │
   └─────────────┘       └─────────────┘ └─────────────┘ └─────────────┘       └─────────────┘
          │                     │               │               │                     │
          └─────────────────────┴───────────────┴───────────────┴─────────────────────┘
                                                │
                                                ▼
                              ┌─────────────────────────────────────┐
                              │     COMMUNITY DETECTION             │
                              │  ─────────────────────────────────  │
                              │  Algorithm: Louvain                 │
                              │  Output: 8,015 communities          │
                              │  Largest: 227 (Kindred Healthcare)  │
                              │  Median: 1 facility                 │
                              └─────────────────┬───────────────────┘
                                                │
                                                ▼
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
 LAYER 3: FEATURE ENGINEERING
═══════════════════════════════════════════════════════════════════════════════════════════════════════════

    ┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
    │                                    30+ FEATURES PER FACILITY                                    │
    ├─────────────────────────┬─────────────────────────┬─────────────────────────┬───────────────────┤
    │     BILLING (6)         │     NETWORK (8)         │    OWNERSHIP (8)        │   DERIVED (8+)    │
    ├─────────────────────────┼─────────────────────────┼─────────────────────────┼───────────────────┤
    │ • total_charges         │ • pagerank              │ • owner_count           │ • community_      │
    │ • total_payments        │ • degree_centrality     │ • max_facilities_owner  │   excluded_count  │
    │ • total_beneficiaries   │ • betweenness           │ • shared_address_count  │ • fraud_density   │
    │ • charges_per_bene      │ • clustering_coef       │ • shared_phone_count    │ • fraud_neighbor  │
    │ • payment_ratio         │ • community_size        │ • entity_age_years      │   _ratio          │
    │ • state_percentile      │ • neighbor_count        │ • is_nonprofit          │ • billing_        │
    │                         │ • excluded_neighbor_    │ • has_quality_ratings   │   deviation       │
    │                         │   ratio                 │                         │                   │
    └─────────────────────────┴─────────────────────────┴─────────────────────────┴───────────────────┘
                                                │
                                                ▼
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
 LAYER 4: MACHINE LEARNING
═══════════════════════════════════════════════════════════════════════════════════════════════════════════

                    ┌───────────────────────────────────────────────────────────────┐
                    │                     XGBOOST CLASSIFIER                        │
                    │  ───────────────────────────────────────────────────────────  │
                    │                                                               │
                    │  Config:                      Performance:                    │
                    │  • n_estimators: 200          • ROC-AUC: 0.91                 │
                    │  • max_depth: 6               • Precision@100: 85%            │
                    │  • scale_pos_weight: 36       • Training time: 8s             │
                    │  • eval_metric: auc                                           │
                    │                                                               │
                    │  Class Imbalance: 298/11,090 = 2.7% positive                  │
                    │  Solution: SMOTE + class weights                              │
                    │                                                               │
                    └───────────────────────────────┬───────────────────────────────┘
                                                    │
                              ┌─────────────────────┴─────────────────────┐
                              │                                           │
                              ▼                                           ▼
               ┌──────────────────────────┐                ┌──────────────────────────┐
               │    RISK SCORE OUTPUT     │                │   SHAP EXPLAINABILITY    │
               │  ──────────────────────  │                │  ──────────────────────  │
               │                          │                │                          │
               │  fraud_risk_score: 0.0   │                │  Top factors for each    │
               │         to 1.0           │                │  prediction:             │
               │                          │                │                          │
               │  Example:                │                │  +1.78 louvain_community │
               │  Community 1597: 0.94    │                │  +1.04 shared_address    │
               │  Community 170:  0.65    │                │  -0.39 community_size    │
               │                          │                │                          │
               └──────────────┬───────────┘                └──────────────────────────┘
                              │
                              ▼
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
 LAYER 5: TRIAGE & FILTERING
═══════════════════════════════════════════════════════════════════════════════════════════════════════════

                              ┌─────────────────────────────────────┐
                              │      INVESTIGATION THRESHOLD        │
                              │  ─────────────────────────────────  │
                              │                                     │
                              │   IF any of:                        │
                              │   • risk_score > 0.3                │
                              │   • red_flags > 0                   │
                              │   • DOJ_match = true                │
                              │                                     │
                              │   THEN → Full Investigation         │
                              │   ELSE → Skip (save cost)           │
                              │                                     │
                              └─────────────────┬───────────────────┘
                                                │
                         ┌──────────────────────┴──────────────────────┐
                         │                                             │
                    INVESTIGATE                                      SKIP
                         │                                             │
                         ▼                                             ▼
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
 LAYER 6: RED FLAG ANALYSIS (Deterministic - No LLM)
═══════════════════════════════════════════════════════════════════════════════════════════════════════════

    ┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
    │                               5 AUTOMATED RED FLAG CHECKS                                       │
    ├───────┬─────────────────────────────┬───────────────────────────────────────────────────────────┤
    │  #    │  RED FLAG                   │  TRIGGER CONDITION                                        │
    ├───────┼─────────────────────────────┼───────────────────────────────────────────────────────────┤
    │  1    │  Ownership Concentration    │  Single owner controls 3+ facilities                      │
    ├───────┼─────────────────────────────┼───────────────────────────────────────────────────────────┤
    │  2    │  Shared Address             │  Multiple entities with different names at same address   │
    ├───────┼─────────────────────────────┼───────────────────────────────────────────────────────────┤
    │  3    │  LEIE Connection            │  Any facility or owner on OIG exclusion list              │
    ├───────┼─────────────────────────────┼───────────────────────────────────────────────────────────┤
    │  4    │  Billing Deviation          │  Billing > 2 standard deviations from state median        │
    ├───────┼─────────────────────────────┼───────────────────────────────────────────────────────────┤
    │  5    │  Shared Phone               │  Multiple entities sharing same phone number              │
    └───────┴─────────────────────────────┴───────────────────────────────────────────────────────────┘
                                                │
                                                ▼
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
 LAYER 7: DOJ CROSS-REFERENCE
═══════════════════════════════════════════════════════════════════════════════════════════════════════════

                    ┌───────────────────────────────────────────────────────────────┐
                    │                  DOJ PROSECUTION DATABASE                     │
                    │  ───────────────────────────────────────────────────────────  │
                    │                                                               │
                    │  Local database of 50+ prosecuted facilities/individuals:    │
                    │                                                               │
                    │  • USA Home Care Solution (2015 Miami takedown)               │
                    │  • Florida Patient Care Corp (phantom billing)                │
                    │  • Easy Care Home Health (kickback scheme)                    │
                    │  • ... 47 more entries                                        │
                    │                                                               │
                    │  Match methods:                                               │
                    │  • Exact NPI match                                            │
                    │  • Fuzzy facility name (Levenshtein < 3)                      │
                    │  • Owner name match                                           │
                    │                                                               │
                    │  IF MATCH FOUND:                                              │
                    │  → Force full investigation regardless of ML score            │
                    │  → Flag as "DOJ PROSECUTION RECORD FOUND"                     │
                    │                                                               │
                    └───────────────────────────────┬───────────────────────────────┘
                                                    │
                                                    ▼
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
 LAYER 8: AI AGENT INVESTIGATION
═══════════════════════════════════════════════════════════════════════════════════════════════════════════

                    ┌───────────────────────────────────────────────────────────────┐
                    │                 FRAUD INVESTIGATOR AGENT                      │
                    │                   (Claude 3.5 Sonnet)                         │
                    │  ───────────────────────────────────────────────────────────  │
                    │                                                               │
                    │  CONTEXT INJECTION:                                           │
                    │  • Community members (NPIs, names, addresses)                 │
                    │  • Risk scores and SHAP values                                │
                    │  • Red flag results (deterministic)                           │
                    │  • DOJ match details (if any)                                 │
                    │  • Entity ages from SunBiz                                    │
                    │                                                               │
                    └───────────────────────────────┬───────────────────────────────┘
                                                    │
                    ┌───────────────────────────────┼───────────────────────────────┐
                    │                               │                               │
                    ▼                               ▼                               ▼
         ┌─────────────────────┐       ┌─────────────────────┐       ┌─────────────────────┐
         │   LLM CALL 1        │       │   LLM CALL 2        │       │   LLM CALL 3        │
         │  ─────────────────  │       │  ─────────────────  │       │  ─────────────────  │
         │                     │       │                     │       │                     │
         │  HYPOTHESIS         │       │  EVIDENCE           │       │  NARRATIVE          │
         │  GENERATION         │  ───▶ │  EVALUATION         │  ───▶ │  SYNTHESIS          │
         │                     │       │                     │       │                     │
         │  Generate 3         │       │  For each H:        │       │  Write final        │
         │  competing fraud    │       │  • SUPPORTED or     │       │  investigation      │
         │  hypotheses         │       │  • REFUTED          │       │  brief with         │
         │                     │       │  with evidence      │       │  classification     │
         │                     │       │                     │       │                     │
         │  ~1,200 tokens      │       │  ~800 tokens        │       │  ~1,500 tokens      │
         │  ~$0.01             │       │  ~$0.008            │       │  ~$0.012            │
         └─────────────────────┘       └─────────────────────┘       └─────────────────────┘
                                                    │
                                                    ▼
                    ┌───────────────────────────────────────────────────────────────┐
                    │                 FALSE POSITIVE DETECTION                      │
                    │  ───────────────────────────────────────────────────────────  │
                    │                                                               │
                    │  System prompt includes:                                      │
                    │  • Known hospital systems (Kindred, HCA, Solaris)             │
                    │  • 30+ year entities CANNOT be shell companies                │
                    │  • Large community size may indicate legitimate system        │
                    │  • Quality ratings suggest established provider               │
                    │                                                               │
                    └───────────────────────────────┬───────────────────────────────┘
                                                    │
                                                    ▼
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
 LAYER 9: OUTPUT GENERATION
═══════════════════════════════════════════════════════════════════════════════════════════════════════════

                    ┌───────────────────────────────────────────────────────────────┐
                    │                   STRUCTURED OUTPUT                           │
                    │  ───────────────────────────────────────────────────────────  │
                    │                                                               │
                    │  {                                                            │
                    │    "community_id": 1597,                                      │
                    │    "classification": "HIGH | MEDIUM | LOW | CLEARED",         │
                    │    "confidence": "HIGH | MEDIUM | LOW",                       │
                    │    "member_count": 4,                                         │
                    │    "excluded_count": 4,                                       │
                    │    "flags_triggered": 5,                                      │
                    │    "avg_risk_score": 0.94,                                    │
                    │    "doj_match": true | false,                                 │
                    │    "hypotheses": "H1: Shell company network...",              │
                    │    "evaluation": "H1: SUPPORTED - all excluded...",           │
                    │    "narrative": "# INVESTIGATION BRIEF\n\n..."                │
                    │  }                                                            │
                    │                                                               │
                    └───────────────────────────────┬───────────────────────────────┘
                                                    │
                              ┌─────────────────────┴─────────────────────┐
                              │                                           │
                              ▼                                           ▼
               ┌──────────────────────────┐                ┌──────────────────────────┐
               │   INVESTIGATION DOSSIER  │                │   RECOMMENDED ACTIONS    │
               │  ──────────────────────  │                │  ──────────────────────  │
               │                          │                │                          │
               │  • Executive summary     │                │  HIGH:                   │
               │  • Risk classification   │                │  → Immediate referral    │
               │  • Member list + scores  │                │  → Freeze payments       │
               │  • Network visualization │                │                          │
               │  • Evidence chain        │                │  MEDIUM:                 │
               │  • Agent hypotheses      │                │  → Enhanced monitoring   │
               │  • SHAP explanations     │                │  → Request claims data   │
               │                          │                │                          │
               │  Export: JSON, Markdown  │                │  LOW/CLEARED:            │
               │                          │                │  → Standard monitoring   │
               └──────────────────────────┘                └──────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════════════════════════════════
 OBSERVABILITY & EVALUATION
═══════════════════════════════════════════════════════════════════════════════════════════════════════════

    ┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
    │                                                                                                 │
    │   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐     │
    │   │  SCHEMA         │    │  FACTUAL        │    │  GOLDEN SET     │    │  DRIFT          │     │
    │   │  VALIDATION     │    │  GROUNDING      │    │  REGRESSION     │    │  MONITORING     │     │
    │   │                 │    │                 │    │                 │    │                 │     │
    │   │ Every output    │    │ Verify:         │    │ 7 curated       │    │ Weekly check:   │     │
    │   │ must match      │    │ • NPI exists    │    │ test cases      │    │ • Classification│     │
    │   │ JSON schema     │    │ • Address match │    │ run on every    │    │   distribution  │     │
    │   │                 │    │ • Exclusion     │    │ model/prompt    │    │ • Confidence    │     │
    │   │                 │    │   status        │    │ change          │    │   scores        │     │
    │   └─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘     │
    │                                                                                                 │
    │   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐     │
    │   │  LOGGING        │    │  COST           │    │  HUMAN          │    │  FEEDBACK       │     │
    │   │                 │    │  TRACKING       │    │  SAMPLING       │    │  LOOP           │     │
    │   │                 │    │                 │    │                 │    │                 │     │
    │   │ Every LLM call: │    │ Per invest:     │    │ Daily review:   │    │ Investigator    │     │
    │   │ • Tokens        │    │ ~$0.03          │    │ 5% of HIGH      │    │ corrections →   │     │
    │   │ • Latency       │    │                 │    │ 100% edge cases │    │ Golden set      │     │
    │   │ • Input/Output  │    │ Full FL scan:   │    │ All DOJ matches │    │ expansion       │     │
    │   │                 │    │ ~$330           │    │                 │    │                 │     │
    │   └─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘     │
    │                                                                                                 │
    └─────────────────────────────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════════════════════════════════
 TECHNOLOGY STACK
═══════════════════════════════════════════════════════════════════════════════════════════════════════════

    ┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
    │                                                                                                 │
    │   DATA PROCESSING        GRAPH              ML                 AI AGENT         FRONTEND       │
    │   ─────────────────      ─────              ──                 ────────         ────────       │
    │                                                                                                 │
    │   • Python 3.11          • NetworkX         • XGBoost          • Claude 3.5     • React        │
    │   • Pandas               • Louvain          • SHAP             • Anthropic      • Tailwind     │
    │   • Parquet              • Community        • Scikit-learn       API            • Vite         │
    │                            Detection        • SMOTE                                            │
    │                                                                                                 │
    │   BACKEND                STORAGE            DEPLOYMENT                                         │
    │   ───────                ───────            ──────────                                         │
    │                                                                                                 │
    │   • FastAPI              • Parquet files    • Local dev        Production ready:               │
    │   • Uvicorn              • In-memory        • Docker           • AWS/GCP                       │
    │   • Pydantic               graph              compatible       • Kubernetes                    │
    │                                                                • CI/CD                         │
    │                                                                                                 │
    └─────────────────────────────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════════════════════════════════
 DATA FLOW SUMMARY
═══════════════════════════════════════════════════════════════════════════════════════════════════════════

    5 Data Sources → ETL → Graph (26K nodes, 38K edges) → Features (33) → XGBoost → Risk Score
                                                                                          │
                                                                                          ▼
                                                          ┌─────────────────────────────────────┐
                                                          │  Score > 0.3 OR Flags OR DOJ?      │
                                                          └──────────────────┬──────────────────┘
                                                                             │
                                                       ┌─────────YES─────────┴─────────NO──────┐
                                                       │                                       │
                                                       ▼                                       ▼
                                              Red Flags (5 checks)                    Classification:
                                                       │                              CLEARED/LOW
                                                       ▼
                                              DOJ Cross-Reference
                                                       │
                                                       ▼
                                              AI Agent (3 LLM calls)
                                                       │
                                                       ▼
                                              Classification + Dossier
                                              (HIGH/MEDIUM/LOW/CLEARED)


═══════════════════════════════════════════════════════════════════════════════════════════════════════════
 KEY METRICS
═══════════════════════════════════════════════════════════════════════════════════════════════════════════

    ┌──────────────────────┬──────────────────────┬──────────────────────┬──────────────────────┐
    │      ML MODEL        │      VALIDATION      │       COST           │      LATENCY         │
    ├──────────────────────┼──────────────────────┼──────────────────────┼──────────────────────┤
    │  ROC-AUC: 0.91       │  Golden Set: 7/7     │  Per investigation:  │  ML scoring:         │
    │  Precision@100: 85%  │  DOJ Cases: 7/8      │  ~$0.03              │  <100ms              │
    │  True Positive: 82%  │  Factual: 100%       │                      │                      │
    │  False Positive: 12% │                      │  Full FL scan:       │  Full investigation: │
    │  (before agent)      │                      │  ~$330               │  30-60 seconds       │
    └──────────────────────┴──────────────────────┴──────────────────────┴──────────────────────┘

```

---

## SIMPLIFIED ONE-PAGE FLOW

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                         │
│   DATA            GRAPH           ML              TRIAGE          AGENT         OUTPUT  │
│   ────            ─────           ──              ──────          ─────         ──────  │
│                                                                                         │
│   5 Sources  →  26K Nodes   →  XGBoost    →   Threshold   →   Claude    →   HIGH      │
│   11K Facilities 38K Edges     33 features    Score>0.3?      3 calls       MEDIUM    │
│   298 excluded  8K communities ROC:0.91        Flags>0?        $0.03/ea      LOW       │
│                                                DOJ match?                    CLEARED   │
│                                                                                         │
│   $0             $0             $0              $0              $0.03         Dossier  │
│   (data free)    (local)        (local)         (local)         (API)         + Report │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```
