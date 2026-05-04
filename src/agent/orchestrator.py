"""
MediGraph Investigation Orchestrator

Controls the investigation flow, calls tools, and coordinates LLM reasoning.
"""
import os
import json
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import anthropic

from .tools.facility_tools import get_facility_profile, get_billing_comparison
from .tools.graph_tools import (
    get_community_members,
    get_community_stats,
    get_neighbors,
    get_top_risk_communities,
    ego_network_expand,
    get_ego_cluster_stats,
)
from .tools.ownership_tools import (
    get_ownership_cluster,
    get_facility_owners,
    get_shared_entities,
)
from .tools.risk_tools import get_shap_explanation, get_risk_score
from .tools.red_flag_tools import check_red_flags, check_ego_red_flags
from .tools.research_tools import research_facility_background, search_doj_records


PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    """Load a prompt template."""
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text()


class FraudInvestigator:
    """Orchestrates fraud investigations on facility communities."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the investigator.

        Args:
            api_key: Anthropic API key. If not provided, uses ANTHROPIC_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)
        else:
            self.client = None
            print("WARNING: No ANTHROPIC_API_KEY found. LLM features disabled.")

        self.system_prompt = _load_prompt("system_prompt")

    def _call_llm(self, user_message: str, max_tokens: int = 2000) -> str:
        """Call the LLM with a message."""
        if not self.client:
            return "[LLM unavailable - set ANTHROPIC_API_KEY]"

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_message}]
        )
        return response.content[0].text

    def investigate_community(self, community_id: int) -> dict:
        """
        Full investigation pipeline for a community.

        Returns a structured dossier dict.
        """
        # Step 1: Triage
        members = get_community_members(community_id)
        stats = get_community_stats(community_id)

        if isinstance(stats, dict) and "error" in stats:
            return {"error": stats["error"]}

        if not members:
            return {"error": f"Community {community_id} has no members"}

        # Step 1.5: Research validation - check DOJ records BEFORE triage
        doj_findings = []
        force_full_investigation = False
        for member in members:
            # Get owner names for this facility
            owner_names = []
            try:
                owners = get_facility_owners(member["npi"])
                if isinstance(owners, list):
                    owner_names = [o.get("owner_name", "") for o in owners if o.get("owner_name")]
            except:
                pass

            research = research_facility_background(
                facility_name=member.get("facility_name", ""),
                npi=member["npi"],
                address=member.get("address", ""),
                owner_names=owner_names
            )

            if research["doj_check"]["found"]:
                force_full_investigation = True
                doj_findings.append({
                    "npi": member["npi"],
                    "facility_name": member.get("facility_name", ""),
                    "doj_match": research["doj_check"],
                    "research_summary": research["research_summary"]
                })

        # Quick triage for low-risk communities (UNLESS DOJ match found)
        if not force_full_investigation:
            if stats["avg_risk_score"] < 0.3 and stats["excluded_count"] == 0:
                red_flags = check_red_flags(community_id)
                if red_flags["flags_triggered"] == 0:
                    return self._generate_cleared_report(community_id, members, stats, red_flags)

        # Step 2: Run red flag checklist
        red_flags = check_red_flags(community_id)

        # Inject DOJ findings into red flags if found
        if doj_findings:
            red_flags["doj_prosecution_matches"] = doj_findings
            red_flags["flags_triggered"] = max(red_flags["flags_triggered"], 1)
            red_flags["details"]["doj_records"] = {
                "triggered": True,
                "detail": f"DOJ prosecution records found for {len(doj_findings)} facility(ies): " +
                         ", ".join(f["facility_name"] for f in doj_findings)
            }

        # Step 3: Collect evidence (all deterministic)
        evidence = self._collect_evidence(community_id, members)

        # Step 4: Generate hypotheses (LLM)
        hypotheses = self._llm_generate_hypotheses(members, stats, red_flags)

        # Step 5: Evaluate hypotheses (LLM)
        evaluation = self._llm_evaluate_hypotheses(hypotheses, evidence, red_flags)

        # Step 6: Generate dossier narrative (LLM)
        dossier = self._llm_generate_dossier(
            community_id, members, stats, evidence, red_flags, hypotheses, evaluation
        )

        return dossier

    def investigate_npi(self, npi: str, hops: int = 2) -> dict:
        """
        Investigation pipeline using ego network expansion.

        Instead of relying on global Louvain communities, this method:
        1. Starts from the specified NPI
        2. Expands outward through ownership, address, and phone edges
        3. Builds a dynamic cluster from everything reachable within k hops
        4. Scores and investigates that cluster

        This approach finds rings that Louvain might split across communities
        or bury inside giant components.

        Returns a structured dossier dict.
        """
        # Step 1: Expand ego network
        members = ego_network_expand(npi, hops=hops)
        stats = get_ego_cluster_stats(npi, hops=hops)

        if isinstance(stats, dict) and "error" in stats:
            return {"error": stats["error"]}

        if not members:
            return {"error": f"NPI {npi} not found in graph or has no connections"}

        # Step 1.5: Research validation - check DOJ records BEFORE triage
        doj_findings = []
        force_full_investigation = False
        for member in members:
            owner_names = []
            try:
                owners = get_facility_owners(member["npi"])
                if isinstance(owners, list):
                    owner_names = [o.get("owner_name", "") for o in owners if o.get("owner_name")]
            except:
                pass

            research = research_facility_background(
                facility_name=member.get("facility_name", ""),
                npi=member["npi"],
                address=member.get("address", ""),
                owner_names=owner_names
            )

            if research["doj_check"]["found"]:
                force_full_investigation = True
                doj_findings.append({
                    "npi": member["npi"],
                    "facility_name": member.get("facility_name", ""),
                    "doj_match": research["doj_check"],
                    "research_summary": research["research_summary"]
                })

        # Step 2: Run red flag checklist on ego network
        member_npis = set(m["npi"] for m in members)
        red_flags = check_ego_red_flags(member_npis, seed_npi=npi)

        # Inject DOJ findings if found
        if doj_findings:
            red_flags["doj_prosecution_matches"] = doj_findings
            red_flags["flags_triggered"] = max(red_flags["flags_triggered"], 1)
            red_flags["details"]["doj_records"] = {
                "triggered": True,
                "detail": f"DOJ prosecution records found for {len(doj_findings)} facility(ies): " +
                         ", ".join(f["facility_name"] for f in doj_findings)
            }

        # Quick triage for low-risk clusters (UNLESS DOJ match found)
        if not force_full_investigation:
            if stats["avg_risk_score"] < 0.3 and stats["excluded_count"] == 0:
                if red_flags["flags_triggered"] == 0:
                    return self._generate_ego_cleared_report(npi, members, stats, red_flags, hops)

        # Step 3: Collect evidence (all deterministic)
        evidence = self._collect_ego_evidence(members)

        # Step 4: Generate hypotheses (LLM)
        hypotheses = self._llm_generate_ego_hypotheses(npi, members, stats, red_flags)

        # Step 5: Evaluate hypotheses (LLM)
        evaluation = self._llm_evaluate_hypotheses(hypotheses, evidence, red_flags)

        # Step 6: Generate dossier narrative (LLM)
        dossier = self._llm_generate_ego_dossier(
            npi, members, stats, evidence, red_flags, hypotheses, evaluation, hops
        )

        return dossier

    def _collect_ego_evidence(self, members: list) -> dict:
        """Deterministic evidence collection for ego network clusters."""
        evidence = {
            "facility_profiles": [],
            "ownership_clusters": [],
            "shap_explanations": [],
            "billing_comparisons": [],
            "shared_entities": None,
        }

        seen_owners = set()

        for member in members:
            npi = member["npi"]

            # Facility profile
            profile = get_facility_profile(npi)
            evidence["facility_profiles"].append(profile)

            # SHAP explanation
            shap_exp = get_shap_explanation(npi)
            evidence["shap_explanations"].append({"npi": npi, "shap": shap_exp})

            # Billing comparison
            billing = get_billing_comparison(npi)
            evidence["billing_comparisons"].append(billing)

            # Ownership clusters (deduplicated by owner)
            owners = get_facility_owners(npi)
            for owner in owners:
                owner_key = owner["owner_name"].upper().strip()
                if owner_key not in seen_owners and owner_key != "UNKNOWN":
                    seen_owners.add(owner_key)
                    cluster = get_ownership_cluster(owner["owner_name"])
                    if cluster["facility_count"] > 0:
                        evidence["ownership_clusters"].append(cluster)

        # Build shared entities from the ego network members
        evidence["shared_entities"] = self._compute_ego_shared_entities(members)

        return evidence

    def _compute_ego_shared_entities(self, members: list) -> dict:
        """Compute shared owners, addresses, phones within ego network."""
        from collections import Counter
        import pandas as pd
        from pathlib import Path

        PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
        PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

        ownership = pd.read_parquet(PROCESSED_DIR / "master_ownership.parquet")
        master = pd.read_parquet(PROCESSED_DIR / "master_facilities.parquet")

        member_npis = set(m["npi"] for m in members)

        # Shared owners
        member_ownership = ownership[ownership["facility_npi"].astype(str).isin(member_npis)]
        owner_counts = member_ownership.groupby("owner_normalized_name")["facility_npi"].nunique()
        shared_owners = [
            {"name": name, "facility_count": int(count)}
            for name, count in owner_counts.items()
            if count >= 2
        ]
        shared_owners.sort(key=lambda x: x["facility_count"], reverse=True)

        # Shared addresses and phones
        member_master = master[master["npi"].astype(str).isin(member_npis)]

        address_counts = member_master.groupby("address")["npi"].nunique()
        shared_addresses = [
            {"address": addr, "facility_count": int(count)}
            for addr, count in address_counts.items()
            if count >= 2 and pd.notna(addr)
        ]
        shared_addresses.sort(key=lambda x: x["facility_count"], reverse=True)

        phone_counts = member_master.groupby("phone")["npi"].nunique()
        shared_phones = [
            {"phone": phone, "facility_count": int(count)}
            for phone, count in phone_counts.items()
            if count >= 2 and pd.notna(phone)
        ]
        shared_phones.sort(key=lambda x: x["facility_count"], reverse=True)

        return {
            "shared_owners": shared_owners[:10],
            "shared_addresses": shared_addresses[:5],
            "shared_phones": shared_phones[:5],
        }

    def _format_ego_members_for_prompt(self, members: list) -> str:
        """Format ego network member list for prompt injection."""
        lines = []
        for m in members[:20]:
            status = "EXCLUDED" if m["is_excluded"] else ""
            hop_info = f"[{m['hop_distance']}-hop]" if m["hop_distance"] > 0 else "[SEED]"
            connection = f" via {m['connection_path']}" if m.get("connection_path") else ""
            lines.append(
                f"- {hop_info} NPI {m['npi']}: {m['facility_name'][:35]} "
                f"(risk: {m['fraud_risk_score']:.3f}, {m['provider_type']}){connection} {status}"
            )
        if len(members) > 20:
            lines.append(f"... and {len(members) - 20} more facilities")
        return "\n".join(lines)

    def _llm_generate_ego_hypotheses(self, seed_npi: str, members: list, stats: dict, red_flags: dict) -> str:
        """Call LLM to generate hypotheses for ego network cluster."""
        # Use the same hypothesis prompt template but with ego network framing
        template = _load_prompt("hypothesis_prompt")

        prompt = f"""You are analyzing an EGO NETWORK cluster, not a Louvain community.

This cluster was built by starting from seed facility NPI {seed_npi} ({stats['seed_name']})
and expanding {stats['hops']} hops through ownership, address, and phone connections.

Hop distribution: {stats['hop_distribution']}

{template.format(
    member_count=stats['member_count'],
    member_list_with_scores=self._format_ego_members_for_prompt(members),
    avg_risk_score=stats['avg_risk_score'],
    max_risk_score=stats['max_risk_score'],
    excluded_count=stats['excluded_count'],
    flags_triggered=red_flags['flags_triggered'],
    red_flag_details=self._format_red_flags_for_prompt(red_flags),
)}"""

        return self._call_llm(prompt, max_tokens=800)

    def _llm_generate_ego_dossier(
        self,
        seed_npi: str,
        members: list,
        stats: dict,
        evidence: dict,
        red_flags: dict,
        hypotheses: str,
        evaluation: str,
        hops: int,
    ) -> dict:
        """Generate dossier for ego network investigation."""
        template = _load_prompt("dossier_prompt")

        # Extract primary hypothesis and confidence from evaluation
        primary_hypothesis = "Unknown"
        confidence = "MEDIUM"
        for line in evaluation.split("\n"):
            if "PRIMARY HYPOTHESIS:" in line:
                primary_hypothesis = line.split(":")[-1].strip()
            if "CONFIDENCE:" in line:
                confidence = line.split(":")[-1].strip()

        prompt = f"""You are generating a dossier for an EGO NETWORK investigation.

Seed Facility: NPI {seed_npi} ({stats['seed_name']})
Expansion: {hops} hops through ownership/address/phone connections
Cluster Size: {stats['member_count']} facilities

{template.format(
    community_id=f"Ego-{seed_npi}",
    risk_label=red_flags['risk_label'],
    flags_triggered=red_flags['flags_triggered'],
    primary_hypothesis=primary_hypothesis,
    confidence=confidence,
    member_details=self._format_ego_members_for_prompt(members),
    ownership_details=self._format_ownership_for_prompt(evidence),
    evidence_summary=self._format_facility_evidence(evidence),
    red_flag_summary=self._format_red_flags_for_prompt(red_flags),
)}"""

        narrative = self._call_llm(prompt, max_tokens=1500)

        return {
            "cluster_type": "ego_network",
            "seed_npi": seed_npi,
            "seed_name": stats["seed_name"],
            "hops": hops,
            "classification": red_flags["risk_label"],
            "flags_triggered": red_flags["flags_triggered"],
            "total_flags": 5,
            "member_count": stats["member_count"],
            "excluded_count": stats["excluded_count"],
            "avg_risk_score": stats["avg_risk_score"],
            "hop_distribution": stats["hop_distribution"],
            "members": members,
            "red_flags": red_flags,
            "hypotheses": hypotheses,
            "evaluation": evaluation,
            "narrative": narrative,
        }

    def _generate_ego_cleared_report(
        self, seed_npi: str, members: list, stats: dict, red_flags: dict, hops: int
    ) -> dict:
        """Generate a brief report for ego networks that don't warrant investigation."""
        return {
            "cluster_type": "ego_network",
            "seed_npi": seed_npi,
            "seed_name": stats["seed_name"],
            "hops": hops,
            "classification": "CLEARED",
            "flags_triggered": 0,
            "total_flags": 5,
            "member_count": stats["member_count"],
            "excluded_count": 0,
            "avg_risk_score": stats["avg_risk_score"],
            "hop_distribution": stats["hop_distribution"],
            "members": members,
            "red_flags": red_flags,
            "narrative": (
                f"## CLEARED\n\n"
                f"Ego network around NPI {seed_npi} ({stats['seed_name']}) contains "
                f"{stats['member_count']} facilities within {hops} hops, "
                f"with average risk score {stats['avg_risk_score']:.3f} and no LEIE connections. "
                f"No red flags triggered (0/5). No investigation warranted.\n\n"
                f"### Connected Facilities\n"
                + "\n".join(
                    f"- [{m['hop_distance']}-hop] {m['facility_name']} (NPI: {m['npi']}, risk: {m['fraud_risk_score']:.3f})"
                    for m in members[:10]
                )
            ),
        }

    def _collect_evidence(self, community_id: int, members: list) -> dict:
        """Deterministic evidence collection — no LLM involved."""
        evidence = {
            "facility_profiles": [],
            "ownership_clusters": [],
            "shap_explanations": [],
            "billing_comparisons": [],
            "shared_entities": None,
        }

        seen_owners = set()

        for member in members:
            npi = member["npi"]

            # Facility profile
            profile = get_facility_profile(npi)
            evidence["facility_profiles"].append(profile)

            # SHAP explanation
            shap_exp = get_shap_explanation(npi)
            evidence["shap_explanations"].append({"npi": npi, "shap": shap_exp})

            # Billing comparison
            billing = get_billing_comparison(npi)
            evidence["billing_comparisons"].append(billing)

            # Ownership clusters (deduplicated by owner)
            owners = get_facility_owners(npi)
            for owner in owners:
                owner_key = owner["owner_name"].upper().strip()
                if owner_key not in seen_owners and owner_key != "UNKNOWN":
                    seen_owners.add(owner_key)
                    cluster = get_ownership_cluster(owner["owner_name"])
                    if cluster["facility_count"] > 0:
                        evidence["ownership_clusters"].append(cluster)

        # Shared entities within community
        evidence["shared_entities"] = get_shared_entities(community_id)

        return evidence

    def _format_members_for_prompt(self, members: list) -> str:
        """Format member list for prompt injection."""
        lines = []
        for m in members[:20]:  # Limit to top 20 for prompt size
            status = "EXCLUDED" if m["is_excluded"] else ""
            lines.append(
                f"- NPI {m['npi']}: {m['facility_name'][:40]} "
                f"(risk: {m['fraud_risk_score']:.3f}, {m['provider_type']}) {status}"
            )
        if len(members) > 20:
            lines.append(f"... and {len(members) - 20} more facilities")
        return "\n".join(lines)

    def _format_red_flags_for_prompt(self, red_flags: dict) -> str:
        """Format red flags for prompt injection."""
        lines = []
        for flag_name, flag_data in red_flags["details"].items():
            status = "TRIGGERED" if flag_data["triggered"] else "NOT TRIGGERED"
            lines.append(f"- {flag_name.replace('_', ' ').title()}: {status}")
            lines.append(f"  Detail: {flag_data['detail']}")

        # Add classification note if present
        if red_flags.get("classification_note"):
            lines.append(f"\n**CLASSIFICATION NOTE**: {red_flags['classification_note']}")

        # Add false positive warnings if present
        if red_flags.get("false_positive_warnings"):
            lines.append("\n**IMPORTANT - FALSE POSITIVE WARNINGS:**")
            for warning in red_flags["false_positive_warnings"]:
                lines.append(f"  ⚠️ {warning}")

        # Add legitimacy signals summary
        legitimacy = red_flags.get("legitimacy_signals", {})
        if legitimacy.get("mitigating_factors"):
            lines.append("\n**MITIGATING FACTORS:**")
            for factor in legitimacy["mitigating_factors"]:
                lines.append(f"  ✓ {factor}")

        return "\n".join(lines)

    def _format_ownership_for_prompt(self, evidence: dict) -> str:
        """Format ownership evidence for prompt."""
        lines = []
        for cluster in evidence["ownership_clusters"][:10]:
            lines.append(f"\n### {cluster['owner_name']} ({cluster['facility_count']} facilities)")
            for fac in cluster["facilities"][:5]:
                status = "EXCLUDED" if fac["is_excluded"] else ""
                lines.append(
                    f"- NPI {fac['npi']}: {fac['facility_name'][:30]} "
                    f"(role: {fac['role']}, risk: {fac['fraud_risk_score']:.3f}) {status}"
                )
            if len(cluster["facilities"]) > 5:
                lines.append(f"  ... and {len(cluster['facilities']) - 5} more")

        # Shared entities
        shared = evidence.get("shared_entities", {})
        if shared:
            if shared.get("shared_owners"):
                lines.append("\n### Shared Owners (control multiple facilities)")
                for so in shared["shared_owners"][:5]:
                    lines.append(f"- {so['name']}: {so['facility_count']} facilities")

            if shared.get("shared_addresses"):
                lines.append("\n### Shared Addresses")
                for sa in shared["shared_addresses"][:3]:
                    lines.append(f"- {sa['address']}: {sa['facility_count']} facilities")

            if shared.get("shared_phones"):
                lines.append("\n### Shared Phones")
                for sp in shared["shared_phones"][:3]:
                    lines.append(f"- {sp['phone']}: {sp['facility_count']} facilities")

        return "\n".join(lines) if lines else "No ownership clusters found"

    def _format_facility_evidence(self, evidence: dict) -> str:
        """Format facility profiles for prompt."""
        lines = []
        for profile in evidence["facility_profiles"][:10]:
            if "error" in profile:
                continue
            lines.append(f"\n### {profile.get('facility_name', 'Unknown')} (NPI: {profile['npi']})")
            lines.append(f"- Type: {profile.get('provider_type', 'Unknown')}")
            lines.append(f"- Address: {profile.get('address', 'N/A')}")
            lines.append(f"- Risk Score: {profile.get('fraud_risk_score', 0):.3f}")
            if profile.get("is_excluded"):
                lines.append(f"- EXCLUDED: {profile.get('exclusion_type', 'Unknown')}")
            if profile.get("total_charges"):
                lines.append(f"- Total Charges: ${profile['total_charges']:,.0f}")
            if profile.get("avg_payment_per_beneficiary"):
                lines.append(f"- Avg Payment/Bene: ${profile['avg_payment_per_beneficiary']:,.0f}")
            # Legitimacy indicators
            if profile.get("entity_age_years"):
                lines.append(f"- Entity Age: {profile['entity_age_years']} years")
            if profile.get("is_nonprofit"):
                lines.append(f"- Organization Type: NONPROFIT")
            if profile.get("has_star_rating"):
                lines.append(f"- Has CMS Star Rating: Yes")
            if profile.get("has_quality_data"):
                lines.append(f"- Has Quality Data: Yes")
        return "\n".join(lines) if lines else "No facility profiles available"

    def _format_billing_evidence(self, evidence: dict) -> str:
        """Format billing comparisons for prompt."""
        lines = []
        for comp in evidence["billing_comparisons"]:
            if "error" in comp or comp.get("facility_avg_per_bene") is None:
                continue
            sigma = comp.get("deviation_sigma", 0)
            if abs(sigma) > 1:  # Only show significant deviations
                direction = "above" if sigma > 0 else "below"
                lines.append(
                    f"- NPI {comp['npi']}: ${comp['facility_avg_per_bene']:,.0f}/bene "
                    f"({abs(sigma):.1f}σ {direction} median)"
                )
        return "\n".join(lines) if lines else "No significant billing deviations"

    def _format_leie_evidence(self, evidence: dict) -> str:
        """Format LEIE status for prompt."""
        lines = []
        for profile in evidence["facility_profiles"]:
            if profile.get("is_excluded"):
                lines.append(
                    f"- {profile.get('facility_name', 'Unknown')} (NPI: {profile['npi']}): "
                    f"EXCLUDED - {profile.get('exclusion_type', 'Unknown')}"
                )
        return "\n".join(lines) if lines else "No LEIE exclusions in community"

    def _format_shap_evidence(self, evidence: dict) -> str:
        """Format SHAP explanations for prompt."""
        lines = []
        for item in evidence["shap_explanations"][:5]:
            npi = item["npi"]
            shap = item["shap"]
            if isinstance(shap, list) and shap and "error" not in shap[0]:
                lines.append(f"\nNPI {npi} - Top risk factors:")
                for s in shap[:3]:
                    direction = "+" if s["shap_contribution"] > 0 else ""
                    lines.append(
                        f"  - {s['feature']}: {s['value']:.2f} "
                        f"({direction}{s['shap_contribution']:.3f})"
                    )
        return "\n".join(lines) if lines else "SHAP explanations not available"

    def _llm_generate_hypotheses(self, members: list, stats: dict, red_flags: dict) -> str:
        """Call LLM to generate 3 competing hypotheses."""
        template = _load_prompt("hypothesis_prompt")

        prompt = template.format(
            member_count=stats["member_count"],
            member_list_with_scores=self._format_members_for_prompt(members),
            avg_risk_score=stats["avg_risk_score"],
            max_risk_score=stats["max_risk_score"],
            excluded_count=stats["excluded_count"],
            flags_triggered=red_flags["flags_triggered"],
            red_flag_details=self._format_red_flags_for_prompt(red_flags),
        )

        return self._call_llm(prompt, max_tokens=800)

    def _llm_evaluate_hypotheses(self, hypotheses: str, evidence: dict, red_flags: dict) -> str:
        """Call LLM to evaluate hypotheses against evidence."""
        template = _load_prompt("evaluation_prompt")

        prompt = template.format(
            hypotheses=hypotheses,
            ownership_evidence=self._format_ownership_for_prompt(evidence),
            facility_evidence=self._format_facility_evidence(evidence),
            billing_evidence=self._format_billing_evidence(evidence),
            leie_evidence=self._format_leie_evidence(evidence),
            shap_evidence=self._format_shap_evidence(evidence),
            red_flag_details=self._format_red_flags_for_prompt(red_flags),
        )

        return self._call_llm(prompt, max_tokens=1000)

    def _llm_generate_dossier(
        self,
        community_id: int,
        members: list,
        stats: dict,
        evidence: dict,
        red_flags: dict,
        hypotheses: str,
        evaluation: str,
    ) -> dict:
        """Call LLM to generate narrative sections of the dossier."""
        template = _load_prompt("dossier_prompt")

        # Extract primary hypothesis and confidence from evaluation
        primary_hypothesis = "Unknown"
        confidence = "MEDIUM"
        for line in evaluation.split("\n"):
            if "PRIMARY HYPOTHESIS:" in line:
                primary_hypothesis = line.split(":")[-1].strip()
            if "CONFIDENCE:" in line:
                confidence = line.split(":")[-1].strip()

        prompt = template.format(
            community_id=community_id,
            risk_label=red_flags["risk_label"],
            flags_triggered=red_flags["flags_triggered"],
            primary_hypothesis=primary_hypothesis,
            confidence=confidence,
            member_details=self._format_members_for_prompt(members),
            ownership_details=self._format_ownership_for_prompt(evidence),
            evidence_summary=self._format_facility_evidence(evidence),
            red_flag_summary=self._format_red_flags_for_prompt(red_flags),
        )

        narrative = self._call_llm(prompt, max_tokens=1500)

        return {
            "community_id": community_id,
            "classification": red_flags["risk_label"],
            "flags_triggered": red_flags["flags_triggered"],
            "total_flags": 5,
            "member_count": stats["member_count"],
            "excluded_count": stats["excluded_count"],
            "avg_risk_score": stats["avg_risk_score"],
            "members": members,
            "red_flags": red_flags,
            "hypotheses": hypotheses,
            "evaluation": evaluation,
            "narrative": narrative,
        }

    def _generate_cleared_report(
        self, community_id: int, members: list, stats: dict, red_flags: dict
    ) -> dict:
        """Generate a brief report for communities that don't warrant investigation."""
        return {
            "community_id": community_id,
            "classification": "CLEARED",
            "flags_triggered": 0,
            "total_flags": 5,
            "member_count": stats["member_count"],
            "excluded_count": 0,
            "avg_risk_score": stats["avg_risk_score"],
            "members": members,
            "red_flags": red_flags,
            "narrative": (
                f"## CLEARED\n\n"
                f"Community {community_id} contains {stats['member_count']} facilities "
                f"with average risk score {stats['avg_risk_score']:.3f} and no LEIE connections. "
                f"No red flags triggered (0/5). No investigation warranted.\n\n"
                f"### Members\n"
                + "\n".join(
                    f"- {m['facility_name']} (NPI: {m['npi']}, risk: {m['fraud_risk_score']:.3f})"
                    for m in members[:10]
                )
            ),
        }

    def list_top_communities(
        self,
        n: int = 10,
        min_size: int = 3,
        region: str = None,
        zip_prefix: str = None
    ) -> list:
        """List top risk communities, optionally filtered by region or ZIP."""
        return get_top_risk_communities(
            n=n,
            min_size=min_size,
            region=region,
            zip_prefix=zip_prefix
        )
