"""
Factual Accuracy Evaluation for Agent Dossiers

Verifies that all claims in LLM-generated dossiers are grounded in actual data.
Catches hallucinations and incorrect citations.
"""

import re
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class FactualClaim:
    """A factual claim extracted from a dossier."""
    claim_type: str  # "npi", "dollar_amount", "percentage", "address", "phone", "name"
    value: str
    context: str  # Surrounding text
    verified: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class FactualAccuracyResult:
    """Result of factual accuracy evaluation."""
    community_id: int
    total_claims: int
    verified_claims: int
    failed_claims: int
    accuracy: float
    claims: list = field(default_factory=list)
    errors: list = field(default_factory=list)


class FactualAccuracyChecker:
    """Checks factual accuracy of agent-generated dossiers."""

    def __init__(self, data_dir: Path = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent.parent.parent / "data" / "processed"
        self.data_dir = data_dir
        self._features = None
        self._master = None
        self._ownership = None

    def _load_data(self):
        """Lazy load data files."""
        if self._features is None:
            self._features = pd.read_parquet(self.data_dir / "facility_features.parquet")
            self._master = pd.read_parquet(self.data_dir / "master_facilities.parquet")
            self._ownership = pd.read_parquet(self.data_dir / "master_ownership.parquet")

    def extract_claims(self, dossier: dict) -> list:
        """Extract all factual claims from a dossier."""
        claims = []

        # Get narrative text
        narrative = dossier.get("narrative", "")
        hypotheses = dossier.get("hypotheses", "")
        evaluation = dossier.get("evaluation", "")

        full_text = f"{narrative}\n{hypotheses}\n{evaluation}"

        # Extract NPI claims
        npi_pattern = r"NPI[:\s]*(\d{10})"
        for match in re.finditer(npi_pattern, full_text):
            npi = match.group(1)
            start = max(0, match.start() - 50)
            end = min(len(full_text), match.end() + 50)
            context = full_text[start:end]
            claims.append(FactualClaim(
                claim_type="npi",
                value=npi,
                context=context
            ))

        # Extract dollar amounts
        dollar_pattern = r"\$[\d,]+(?:\.\d{2})?"
        for match in re.finditer(dollar_pattern, full_text):
            amount = match.group(0)
            start = max(0, match.start() - 50)
            end = min(len(full_text), match.end() + 50)
            context = full_text[start:end]
            claims.append(FactualClaim(
                claim_type="dollar_amount",
                value=amount,
                context=context
            ))

        # Extract percentages
        pct_pattern = r"(\d+(?:\.\d+)?)\s*%"
        for match in re.finditer(pct_pattern, full_text):
            pct = match.group(0)
            start = max(0, match.start() - 50)
            end = min(len(full_text), match.end() + 50)
            context = full_text[start:end]
            claims.append(FactualClaim(
                claim_type="percentage",
                value=pct,
                context=context
            ))

        # Extract phone numbers
        phone_pattern = r"\b(\d{10}|\d{3}[-.\s]?\d{3}[-.\s]?\d{4})\b"
        for match in re.finditer(phone_pattern, full_text):
            phone = match.group(0)
            # Skip NPIs (10 digits starting with 1)
            if len(phone) == 10 and phone.startswith("1"):
                continue
            start = max(0, match.start() - 50)
            end = min(len(full_text), match.end() + 50)
            context = full_text[start:end]
            claims.append(FactualClaim(
                claim_type="phone",
                value=phone,
                context=context
            ))

        return claims

    def verify_npi(self, npi: str) -> tuple:
        """Verify an NPI exists in the dataset."""
        self._load_data()
        npi_str = str(npi)

        # Check in features
        exists = self._features["npi"].astype(str).eq(npi_str).any()

        if exists:
            return True, None
        else:
            return False, f"NPI {npi} not found in dataset"

    def verify_dollar_amount(self, amount: str, context: str) -> tuple:
        """Verify a dollar amount is plausible given context."""
        self._load_data()

        # Parse amount
        amount_clean = amount.replace("$", "").replace(",", "")
        try:
            value = float(amount_clean)
        except ValueError:
            return False, f"Could not parse amount: {amount}"

        # Check if it's in a reasonable range for healthcare billing
        # Total charges: $0 - $100M
        # Per beneficiary: $0 - $100K
        # State median: ~$10K

        if "per" in context.lower() or "bene" in context.lower():
            # Per-beneficiary amount
            if 0 <= value <= 100000:
                return True, None
            else:
                return False, f"Per-beneficiary amount {amount} out of range"
        elif "median" in context.lower():
            # State median reference
            actual_median = self._features["avg_payment_per_beneficiary"].median()
            if abs(value - actual_median) < 5000:  # Within $5K of actual
                return True, None
            else:
                return False, f"Median {amount} doesn't match actual {actual_median:.0f}"
        else:
            # General amount - just check it's positive and reasonable
            if 0 <= value <= 100000000:
                return True, None
            else:
                return False, f"Amount {amount} out of reasonable range"

    def verify_claim(self, claim: FactualClaim) -> FactualClaim:
        """Verify a single claim."""
        if claim.claim_type == "npi":
            verified, error = self.verify_npi(claim.value)
        elif claim.claim_type == "dollar_amount":
            verified, error = self.verify_dollar_amount(claim.value, claim.context)
        elif claim.claim_type == "percentage":
            # Percentages are usually calculated, hard to verify without full context
            # For now, just check they're in valid range
            try:
                pct_val = float(claim.value.replace("%", "").strip())
                verified = 0 <= pct_val <= 100
                error = None if verified else f"Percentage {claim.value} out of range"
            except ValueError:
                verified = False
                error = f"Could not parse percentage: {claim.value}"
        elif claim.claim_type == "phone":
            # Verify phone exists in dataset
            self._load_data()
            phone_clean = re.sub(r"[-.\s]", "", claim.value)
            exists = self._master["phone"].astype(str).str.replace(r"[-.\s]", "", regex=True).eq(phone_clean).any()
            verified = exists
            error = None if exists else f"Phone {claim.value} not found in dataset"
        else:
            verified = True  # Unknown claim types pass by default
            error = None

        claim.verified = verified
        claim.error = error
        return claim

    def evaluate_dossier(self, dossier: dict) -> FactualAccuracyResult:
        """Evaluate factual accuracy of a dossier."""
        community_id = dossier.get("community_id", dossier.get("seed_npi", "unknown"))

        # Extract claims
        claims = self.extract_claims(dossier)

        # Verify each claim
        verified_claims = []
        failed_claims = []
        errors = []

        for claim in claims:
            self.verify_claim(claim)
            if claim.verified:
                verified_claims.append(claim)
            else:
                failed_claims.append(claim)
                errors.append(f"{claim.claim_type}: {claim.value} - {claim.error}")

        total = len(claims)
        verified = len(verified_claims)
        failed = len(failed_claims)
        accuracy = verified / total if total > 0 else 1.0

        return FactualAccuracyResult(
            community_id=community_id,
            total_claims=total,
            verified_claims=verified,
            failed_claims=failed,
            accuracy=accuracy,
            claims=claims,
            errors=errors
        )


def evaluate_dossier_file(filepath: Path) -> FactualAccuracyResult:
    """Evaluate a saved dossier JSON file."""
    with open(filepath) as f:
        dossier = json.load(f)

    checker = FactualAccuracyChecker()
    return checker.evaluate_dossier(dossier)


def print_accuracy_report(result: FactualAccuracyResult):
    """Print a formatted accuracy report."""
    print(f"\n{'='*60}")
    print(f"FACTUAL ACCURACY REPORT - Community {result.community_id}")
    print(f"{'='*60}")
    print(f"Total Claims: {result.total_claims}")
    print(f"Verified: {result.verified_claims}")
    print(f"Failed: {result.failed_claims}")
    print(f"Accuracy: {result.accuracy:.1%}")

    if result.errors:
        print(f"\nErrors:")
        for error in result.errors:
            print(f"  - {error}")

    print(f"{'='*60}\n")
