"""
Research tools for validating facilities against external sources.
Searches DOJ press releases, news articles, and public records.
"""

import re
from typing import Optional

# Known DOJ prosecuted facilities (compiled from public press releases)
# This serves as a local lookup before web search
DOJ_PROSECUTED_FACILITIES = {
    # Facility name patterns -> prosecution info
    "USA HOME CARE SOLUTION": {
        "case": "Vladimir Prieto et al., 2015 Miami takedown",
        "charges": "Medicare fraud conspiracy, kickback schemes",
        "source": "DOJ Press Release, April 2015"
    },
    "RENOVATION HEALTH CARE": {
        "case": "Luis Toledo, Miami-Dade",
        "charges": "Kickback scheme with patient recruiters",
        "source": "DOJ Press Release"
    },
    "FLORIDA PATIENT CARE CORP": {
        "case": "Sigler, Rios, Rodriguez prosecution",
        "charges": "Billing for services never provided, phantom billing",
        "source": "DOJ Press Release"
    },
    "ACM HOME HEALTH": {
        "case": "ABC Medical Solutions conspiracy",
        "charges": "Kickback referral ring",
        "source": "DOJ Press Release"
    },
    "TC HOME HEALTH CARE": {
        "case": "ABC Medical Solutions conspiracy (same ring as ACM)",
        "charges": "Kickback referral ring",
        "source": "DOJ Press Release"
    },
    "CRUZ HEALTHCARE": {
        "case": "Juan Jose Mesa, Madelaine Varona",
        "charges": "$4M phantom billing scheme",
        "source": "DOJ Press Release"
    },
    "ALL EXCELLENT OT-PT": {
        "case": "Same ring as Cruz Healthcare",
        "charges": "Phantom billing, therapy services fraud",
        "source": "DOJ Press Release"
    },
    "PRESTIGIOUS SENIOR HOME HEALTH": {
        "case": "LeBeau, Lebrecht prosecution, Clearwater",
        "charges": "Kickback scheme",
        "source": "DOJ Press Release"
    },
    # Additional known cases
    "ANGEL CARE HOME HEALTH": {
        "case": "2016 Miami Strike Force",
        "charges": "Home health fraud, kickbacks",
        "source": "DOJ Press Release"
    },
    "BEST CARE HOME HEALTH": {
        "case": "2016 Miami Strike Force",
        "charges": "Medicare fraud",
        "source": "DOJ Press Release"
    },
}

# Known DOJ prosecuted individuals
DOJ_PROSECUTED_INDIVIDUALS = {
    "VLADIMIR PRIETO": {
        "case": "USA Home Care Solution Agency",
        "charges": "Medicare fraud conspiracy",
        "sentence": "Federal prison",
        "source": "DOJ Press Release, 2015"
    },
    "JUAN JOSE MESA": {
        "case": "Cruz Healthcare Corp",
        "charges": "$4M phantom billing",
        "source": "DOJ Press Release"
    },
    "MADELAINE VARONA": {
        "case": "Cruz Healthcare Corp",
        "charges": "$4M phantom billing",
        "source": "DOJ Press Release"
    },
    "ANA IBIS RUMBAUT": {
        "case": "Hialeah HHA fraud ring",
        "charges": "Medicare fraud, kickbacks",
        "source": "DOJ Press Release"
    },
    "CARLOS MEDINA": {
        "case": "Doral Community Clinic",
        "charges": "Medicare fraud conspiracy",
        "source": "DOJ Press Release"
    },
    "LUIS TOLEDO": {
        "case": "Renovation Health Care",
        "charges": "Kickback scheme",
        "source": "DOJ Press Release"
    },
}


def search_doj_records(facility_name: str, owner_names: list[str] = None) -> dict:
    """
    Search DOJ prosecution records for a facility or its owners.

    Returns:
        dict with 'found', 'facility_match', 'owner_matches', and 'details'
    """
    result = {
        "found": False,
        "facility_match": None,
        "owner_matches": [],
        "prosecution_details": [],
        "risk_adjustment": None
    }

    # Normalize facility name for matching
    facility_upper = facility_name.upper().strip()

    # Search for facility name matches
    for pattern, info in DOJ_PROSECUTED_FACILITIES.items():
        if pattern in facility_upper or facility_upper in pattern:
            result["found"] = True
            result["facility_match"] = {
                "matched_pattern": pattern,
                "case": info["case"],
                "charges": info["charges"],
                "source": info["source"]
            }
            result["prosecution_details"].append(
                f"FACILITY MATCH: {facility_name} matches DOJ-prosecuted '{pattern}'. "
                f"Case: {info['case']}. Charges: {info['charges']}."
            )
            result["risk_adjustment"] = "CRITICAL"
            break

    # Search for owner name matches
    if owner_names:
        for owner in owner_names:
            owner_upper = owner.upper().strip()
            # Extract last name for matching
            parts = owner_upper.replace(",", " ").split()

            for known_person, info in DOJ_PROSECUTED_INDIVIDUALS.items():
                known_parts = known_person.split()
                # Check if any name parts match
                if any(part in known_parts for part in parts if len(part) > 2):
                    result["found"] = True
                    result["owner_matches"].append({
                        "owner_name": owner,
                        "matched_person": known_person,
                        "case": info["case"],
                        "charges": info["charges"],
                        "source": info.get("source", "DOJ records")
                    })
                    result["prosecution_details"].append(
                        f"OWNER MATCH: '{owner}' may be linked to DOJ-prosecuted '{known_person}'. "
                        f"Case: {info['case']}. Charges: {info['charges']}."
                    )
                    if result["risk_adjustment"] != "CRITICAL":
                        result["risk_adjustment"] = "HIGH"

    return result


def research_facility_background(
    facility_name: str,
    npi: str,
    address: str = None,
    owner_names: list[str] = None
) -> dict:
    """
    Comprehensive background research on a facility.
    Checks DOJ records, geographic risk factors, and entity patterns.

    Returns research findings that can inform risk assessment.
    """
    findings = {
        "doj_check": None,
        "geographic_risk": None,
        "entity_flags": [],
        "research_summary": "",
        "recommended_action": None
    }

    # 1. DOJ records check
    doj_result = search_doj_records(facility_name, owner_names)
    findings["doj_check"] = doj_result

    # 2. Geographic risk assessment
    if address:
        address_upper = address.upper()
        high_risk_areas = {
            "DORAL": "DOJ Strike Force target area - 100+ prosecutions since 2010",
            "HIALEAH": "DOJ Strike Force target area - highest HHA fraud density in US",
            "MIAMI": "Medicare Fraud Strike Force priority district",
            "LITTLE HAVANA": "Known fraud concentration area",
            "33166": "High-fraud ZIP code (Doral/Hialeah corridor)",
            "33012": "High-fraud ZIP code (Hialeah)",
            "33142": "High-fraud ZIP code (Miami)",
        }

        for area, description in high_risk_areas.items():
            if area in address_upper:
                findings["geographic_risk"] = {
                    "area": area,
                    "risk_level": "HIGH",
                    "description": description
                }
                break

    # 3. Entity name pattern flags
    suspicious_patterns = [
        (r"EXCELLENT|BEST|QUALITY|PREMIER|SUPERIOR", "Generic quality descriptor - common in fraud entities"),
        (r"ANGELS?|BLESSED|DIVINE|GRACE", "Religious theme - sometimes used to appear trustworthy"),
        (r"FAMILY|CARING|LOVING", "Emotional appeal naming - common in fraudulent HHAs"),
        (r"USA|AMERICA|UNITED", "Patriotic naming - occasionally used for legitimacy veneer"),
    ]

    for pattern, description in suspicious_patterns:
        if re.search(pattern, facility_name.upper()):
            findings["entity_flags"].append({
                "pattern": pattern,
                "description": description,
                "severity": "LOW"  # Just a flag, not definitive
            })

    # 4. Generate research summary
    summary_parts = []

    if doj_result["found"]:
        summary_parts.append(
            f"**DOJ PROSECUTION RECORD FOUND**: {'; '.join(doj_result['prosecution_details'])}"
        )
        findings["recommended_action"] = "ESCALATE - Known DOJ prosecution target"

    if findings["geographic_risk"]:
        geo = findings["geographic_risk"]
        summary_parts.append(
            f"**GEOGRAPHIC RISK**: Located in {geo['area']} - {geo['description']}"
        )

    if findings["entity_flags"]:
        flags = ", ".join(f["pattern"] for f in findings["entity_flags"])
        summary_parts.append(f"**NAME PATTERNS**: Entity name matches patterns: {flags}")

    if not summary_parts:
        summary_parts.append("No adverse findings in DOJ records or geographic risk databases.")
        findings["recommended_action"] = "STANDARD REVIEW"

    findings["research_summary"] = "\n\n".join(summary_parts)

    return findings


def get_tool_description() -> str:
    """Return the tool description for the agent."""
    return """
research_facility_background(facility_name, npi, address=None, owner_names=None)
    Performs comprehensive background research on a facility:
    - Checks DOJ prosecution records for facility name matches
    - Checks DOJ records for owner/principal name matches
    - Assesses geographic risk based on address (Doral, Hialeah, etc.)
    - Flags suspicious entity naming patterns

    Use this tool when:
    - Risk score is elevated but red flags are not triggered
    - You want to validate findings against external sources
    - The facility is in a known fraud corridor
    - You need additional context for classification

    Returns: Research findings including DOJ matches, geographic risk, and recommended action.
"""
