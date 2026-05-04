# Provera Presentation Script
## 10-Minute Presentation + Demo

---

## SLIDE 1: Title (30 sec)

> "Hi everyone, I'm [Nikita/Jagannath] and today we're presenting Provera - an AI-powered Medicare fraud detection system that combines machine learning with AI agents to identify fraud rings in healthcare provider networks."

---

## SLIDE 2: Executive Summary (30 sec)

> "Here's what we built: A system that analyzes 11,000 Florida home health agencies and achieves 0.91 ROC-AUC in fraud prediction. We validated it against 7 curated test cases with 100% accuracy, and it successfully identifies 7 out of 8 DOJ-prosecuted facilities in our database."

> "The key innovation is that we detect fraud *structurally* through ownership networks - not just billing anomalies."

---

## SLIDE 3: Problem Statement (45 sec)

> "Medicare loses 60 to 100 billion dollars annually to fraud. Home health agencies are the number one fraud vector - 17 billion in improper payments in 2023 alone."

> "Florida is ground zero - despite having only 7% of Medicare beneficiaries, it accounts for 40% of all fraud prosecutions."

> "Current detection systems fail because they rely on billing rules that generate 90% false positives and can't see coordinated fraud rings operating across multiple shell companies."

> "Our approach is different: we model provider networks as graphs and detect fraud through ownership patterns *before* billing anomalies appear."

---

## SLIDE 4: Architecture Evolution (30 sec)

> "We went through four iterations. Started with basic ML on billing features - 0.72 AUC. Added graph features like network centrality - jumped to 0.81. Added ownership analysis - 0.87. Finally added the AI agent layer for explainability - 0.91."

> "Each iteration solved a specific problem from the previous one."

---

## SLIDE 5: System Architecture (30 sec)

> "Here's the final architecture. Five layers: Data ingestion from CMS and Florida corporate records. Graph construction with 26,000 nodes and 38,000 edges. XGBoost ML model with SHAP explainability. AI agent using Claude for investigation. And finally, actionable output with classifications and investigation reports."

---

## SLIDE 6: Data Sources (30 sec)

> "We integrate five datasets: NPPES for provider identities, LEIE for exclusion labels - that's our ground truth. Medicare billing data, Florida SunBiz for corporate records - this is critical for entity age - and Provider Enrollment for ownership relationships."

> "The key insight: shell companies are typically incorporated within 1-3 years of fraud. 50-year-old entities are almost never shell companies."

---

## SLIDE 7: Graph Data Model (30 sec)

> "We model this as a graph. Facility nodes linked to Owner nodes, Address nodes, and Phone nodes. Then we derive implicit edges: facilities that share an address, share an owner, or share a phone number."

> "Louvain community detection identifies 8,000 natural clusters. Fraud rings operate as communities - investigating the network reveals connections invisible when looking at individual providers."

---

## SLIDE 8: ML Model (30 sec)

> "We tested four models. XGBoost won with 0.91 AUC and 85% precision at top 100. We handle class imbalance - only 2.7% positives - with SMOTE and class weights."

> "Top risk factors from SHAP: shared address count, community excluded count, and entity age. Newer entities at shared addresses with excluded neighbors are high risk."

---

## SLIDE 9: AI Agent Pipeline (30 sec)

> "The investigation pipeline: ML triages all 11,000 facilities instantly. Then 5 deterministic red flag checks - no LLM needed. DOJ cross-reference catches behavioral fraud. Only then does the AI agent investigate, generating hypotheses and evaluation."

> "This hybrid approach gives us speed, cost efficiency, and explainability."

---

## SLIDE 10: Case Studies (45 sec)

> "Five case types we handle correctly:"

> "**HIGH**: Community 1597 - 4 facilities, 100% excluded, similar Miami addresses. Classic shell company ring."

> "**LOW**: Community 170 - 227 facilities, Kindred Healthcare. Agent correctly identifies this as a legitimate PE-backed system, not fraud."

> "**CLEARED**: 52-year-old nonprofit - entity age alone rules out shell company."

> "**HIGH**: DOJ-prosecuted facility - ML score was only 0.42, but DOJ cross-reference caught it. This was phantom billing - behavioral fraud our structural analysis would have missed."

> "**MEDIUM**: Doral fraud corridor - geographic risk factor, warrants monitoring but can't confirm without claims data."

---

## SLIDE 11: Edge Cases (30 sec)

> "Critical point: ML score does NOT equal classification. A facility can have 0.8 risk score but get classified LOW if the agent determines it's a legitimate hospital system."

> "And a facility with 0.4 score can be classified HIGH if it matches DOJ prosecution records."

> "The threshold logic: if score above 0.3, OR red flags triggered, OR DOJ match - we run full investigation. Otherwise skip to save cost."

---

## SLIDE 12: Iterative Improvements (30 sec)

> "Seven improvements we made: SunBiz integration for entity age. DOJ cross-reference layer. Deterministic red flags before LLM. False positive rules for hospital systems. SHAP explainability. Louvain community detection. And confidence calibration."

> "Each made the system smarter and more accurate."

---

## SLIDE 13: Golden Set (30 sec)

> "We validated on 7 curated cases covering all classification types. 7 out of 7 correct. 100% factual accuracy - every facility name, NPI, address verified against source data. Zero hallucinations in generated reports."

---

## SLIDE 14: Limitations (30 sec)

> "Honest limitations: We detect structural fraud - shell companies, shared addresses. We cannot detect behavioral fraud like kickbacks or phantom billing without claims-level data."

> "3 of 7 DOJ cases were behavioral fraud we'd miss with structure alone - that's why we added the DOJ cross-reference."

> "For scalability: Florida is 11,000 providers. National scale is 1.2 million - about $36K in API costs for a full scan."

---

## DEMO (2-3 min)

### Setup
> "Let me show you the live system."

*Open browser to localhost:5173*

### Search & Investigation
> "Here's the investigation interface. I'll search for a high-risk community."

*Click on Community 1597 or enter it*

> "Watch the pipeline run - it's loading data, building the network, checking exclusions, running red flags, cross-referencing DOJ, generating hypotheses, evaluating evidence, writing the report."

*Wait for results*

> "Here's the result. Classification: HIGH. 4 facilities, all excluded. Look at the network visualization - they're all connected."

> "The SHAP panel shows why ML flagged this - shared address count is the top factor."

> "And here's the AI-generated investigation brief - it identifies this as entity cycling to evade oversight."

### False Positive Demo (if time)
> "Let me show a false positive case - Community 170."

*Navigate to Community 170*

> "227 facilities - Kindred Healthcare. ML score is elevated because of size, but the agent correctly classifies it as LOW - legitimate PE-backed healthcare chain."

### Wrap Up
> "That's Provera - hybrid ML plus AI agents for Medicare fraud detection. Questions?"

---

## TIMING SUMMARY

| Section | Time |
|---------|------|
| Slides 1-5 | 2:30 |
| Slides 6-9 | 2:00 |
| Slides 10-14 | 2:30 |
| Demo | 2:30 |
| Buffer/Questions | 0:30 |
| **Total** | **10:00** |

---

## KEY POINTS TO EMPHASIZE

1. **Structural vs Behavioral**: We detect fraud through ownership patterns, not billing anomalies
2. **Hybrid Approach**: ML for speed, Agent for explainability
3. **Edge Cases**: High score ≠ High risk (Kindred example)
4. **Honest Limitations**: Can't detect kickbacks without claims data
5. **Validation**: 7/7 golden set, 7/8 DOJ cases

## IF RUNNING SHORT ON TIME

Skip slides 6-7 (data sources, graph model) - say "We integrate 5 government datasets into a graph with 26K nodes and 38K edges"

## IF ASKED ABOUT...

**"Why not just use rules?"**
> Rules generate 90% false positives. Our ML+Agent approach gets 85% precision.

**"How do you handle false positives?"**
> Agent has explicit rules: 30+ year entities can't be shell companies. System prompt warns about hospital systems like Kindred, HCA.

**"What about real-time?"**
> Current system is batch. Future work includes real-time monitoring of new provider registrations.

**"Cost at scale?"**
> ML is free (local). Agent is $0.03 per investigation. Full national scan ~$36K.
