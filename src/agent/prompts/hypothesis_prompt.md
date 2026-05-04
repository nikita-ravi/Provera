Given the following community of {member_count} facilities:

{member_list_with_scores}

Community statistics:
- Average risk score: {avg_risk_score:.3f}
- Maximum risk score: {max_risk_score:.3f}
- Excluded members: {excluded_count}
- Red flags triggered: {flags_triggered}/5

Red flag details:
{red_flag_details}

Generate exactly 3 competing hypotheses:
- H1: A specific fraud-related explanation (e.g., coordinated billing, shell entities, kickback scheme)
- H2: A different fraud-related explanation (e.g., referral capture, phantom services, upcoding)
- H3: A benign (non-fraud) explanation (e.g., legitimate healthcare chain, geographic co-location, family business)

For each hypothesis, state what evidence would confirm or refute it using the available data.

Respond in this exact format:

H1: [specific fraud hypothesis]
Evidence needed: [what data points would confirm or refute this]

H2: [different fraud hypothesis]
Evidence needed: [what data points would confirm or refute this]

H3: [benign explanation]
Evidence needed: [what data points would confirm or refute this]
