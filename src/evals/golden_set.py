"""
Golden Set for MediGraph Agent Evaluation

Each entry represents a manually verified community with expected classification.
Used to measure classification accuracy and detect regressions.
"""

GOLDEN_SET = [
    # === CONFIRMED FALSE POSITIVES ===
    # NOTE: Community IDs change on Louvain re-runs. These are updated after pipeline rebuild.
    {
        "community_id": 215,  # Was 216, shifted after Louvain re-run
        "expected_class": "FALSE_POSITIVE",
        "expected_label": "MEDIUM",  # Should be downgraded from HIGH
        "reason": "United Home Care Services - 51-year-old United Way nonprofit",
        "verified_by": "Manual research - BBB A+ rating, GuideStar 501(c)(3)",
        "key_signals": ["entity_age_years > 50", "legitimate nonprofit"],
        "representative_npi": "1164481289",
    },
    {
        "community_id": 170,  # Was 171, shifted after Louvain re-run
        "expected_class": "FALSE_POSITIVE",
        "expected_label": "MEDIUM",
        "reason": "Nautic Partners PE-backed healthcare chain",
        "verified_by": "Ownership analysis - institutional investors",
        "key_signals": ["PE ownership", "multi-state operations", "19-year history"],
        "representative_npi": "1376724146",
    },

    # === CONFIRMED FRAUD RINGS ===
    {
        "community_id": 1597,  # Was 1598, shifted after Louvain re-run
        "expected_class": "CONFIRMED_FRAUD",
        "expected_label": "HIGH",
        "reason": "100% exclusion rate - all 4 facilities LEIE excluded",
        "verified_by": "LEIE database verification",
        "key_signals": ["100% fraud_density", "shared address", "shared phone"],
        "representative_npi": "1851562433",
    },
    {
        "community_id": 731,  # Was 732, shifted after Louvain re-run
        "expected_class": "SUSPICIOUS",
        "expected_label": "MEDIUM",  # 2/5 flags, legitimately suspicious
        "reason": "Doral HHA cluster - 3/11 excluded, shell company pattern",
        "verified_by": "Investigation dossier analysis",
        "key_signals": ["27% fraud_density", "shared address", "same building"],
        "representative_npi": "1174764880",
    },

    # === CLEARED COMMUNITIES ===
    {
        "community_id": 5806,  # Was 5807, shifted after Louvain re-run
        "expected_class": "CLEARED",
        "expected_label": "LOW",
        "reason": "Tampa cluster - 0 exclusions, 0 red flags",
        "verified_by": "Automated triage",
        "key_signals": ["0 flags", "low risk scores", "no exclusions"],
    },
    {
        "community_id": 4446,  # Was 4447, shifted after Louvain re-run
        "expected_class": "CLEARED",
        "expected_label": "LOW",
        "reason": "Clean community with no suspicious patterns",
        "verified_by": "Red flag checklist",
        "key_signals": ["0 flags", "normal billing"],
        "representative_npi": "1588258206",
    },

    # === SUSPICIOUS (WARRANTS INVESTIGATION) ===
    {
        "community_id": 5411,  # Was 5412, shifted after Louvain re-run
        "expected_class": "SUSPICIOUS",
        "expected_label": "HIGH",  # 3/5 flags
        "reason": "Tampa Henderson Blvd cluster - shared phone, 1 excluded",
        "verified_by": "Investigation dossier",
        "key_signals": ["shared_phone", "same building", "1 exclusion"],
    },
]


def get_golden_set():
    """Return the golden set for evaluation."""
    return GOLDEN_SET


def get_by_class(expected_class: str):
    """Filter golden set by expected classification."""
    return [g for g in GOLDEN_SET if g["expected_class"] == expected_class]
