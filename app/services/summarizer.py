from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.llm.base import LLMClient, LLMError
from app.services.classifier import RetryPolicy, _call_with_retry
from app.services.cleaner import CleanedTransaction

RiskLevel = Literal["low", "medium", "high"]


class LLMSummaryPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    spend_by_currency: dict[str, Decimal] = Field(default_factory=dict)
    top_merchants: list[dict[str, Any]]
    anomaly_count: int
    narrative: str
    risk_level: RiskLevel


@dataclass(frozen=True, slots=True)
class SummaryResult:
    total_spend_inr: Decimal
    total_spend_usd: Decimal
    top_merchants: list[dict[str, Any]]
    anomaly_count: int
    narrative: str
    risk_level: RiskLevel


def generate_summary(
    transactions: list[CleanedTransaction],
    *,
    client: LLMClient,
    retry_policy: RetryPolicy,
    job_id: str | None = None,
) -> SummaryResult:
    deterministic = deterministic_summary(transactions)
    prompt = _summary_prompt(transactions)
    try:
        payload = _call_with_retry(
            lambda: parse_summary_response(client.generate_json(prompt)),
            retry_policy=retry_policy,
            stage="llm_summary",
            job_id=job_id,
        )
        narrative = payload.narrative
        risk_level = payload.risk_level
    except LLMError:
        narrative = _fallback_narrative(deterministic)
        risk_level = _fallback_risk_level(
            deterministic.anomaly_count,
            len(transactions),
        )

    return SummaryResult(
        total_spend_inr=deterministic.total_spend_inr,
        total_spend_usd=deterministic.total_spend_usd,
        top_merchants=deterministic.top_merchants,
        anomaly_count=deterministic.anomaly_count,
        narrative=narrative,
        risk_level=risk_level,
    )


def deterministic_summary(transactions: list[CleanedTransaction]) -> SummaryResult:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    merchant_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for transaction in transactions:
        totals[transaction.currency] += transaction.amount
        merchant_totals[transaction.merchant] += transaction.amount

    top_merchants = [
        {"merchant": merchant, "total": str(total)}
        for merchant, total in sorted(
            merchant_totals.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:3]
    ]
    anomaly_count = sum(1 for transaction in transactions if transaction.is_anomaly)
    risk_level = _fallback_risk_level(anomaly_count, len(transactions))
    return SummaryResult(
        total_spend_inr=totals["INR"],
        total_spend_usd=totals["USD"],
        top_merchants=top_merchants,
        anomaly_count=anomaly_count,
        narrative=_fallback_narrative_from_counts(
            total_inr=totals["INR"],
            total_usd=totals["USD"],
            anomaly_count=anomaly_count,
        ),
        risk_level=risk_level,
    )


def parse_summary_response(raw_response: str) -> LLMSummaryPayload:
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise LLMError("Summary response was not valid JSON.") from exc

    try:
        return LLMSummaryPayload.model_validate(payload)
    except ValidationError as exc:
        raise LLMError("Summary response did not match the expected schema.") from exc


def _summary_prompt(transactions: list[CleanedTransaction]) -> str:
    rows = [
        {
            "txn_id": transaction.txn_id,
            "merchant": transaction.merchant,
            "amount": str(transaction.amount),
            "currency": transaction.currency,
            "category": transaction.category,
            "is_anomaly": transaction.is_anomaly,
            "anomaly_reason": transaction.anomaly_reason,
        }
        for transaction in transactions
    ]
    return (
        "Generate a transaction portfolio summary. Return only JSON with keys "
        "spend_by_currency, top_merchants, anomaly_count, narrative, risk_level. "
        "risk_level must be low, medium, or high. "
        f"Transactions: {json.dumps(rows)}"
    )


def _fallback_risk_level(anomaly_count: int, total_count: int) -> RiskLevel:
    if total_count == 0 or anomaly_count == 0:
        return "low"
    ratio = anomaly_count / total_count
    if ratio >= 0.15:
        return "high"
    if ratio >= 0.05:
        return "medium"
    return "low"


def _fallback_narrative(summary: SummaryResult) -> str:
    return _fallback_narrative_from_counts(
        total_inr=summary.total_spend_inr,
        total_usd=summary.total_spend_usd,
        anomaly_count=summary.anomaly_count,
    )


def _fallback_narrative_from_counts(
    *,
    total_inr: Decimal,
    total_usd: Decimal,
    anomaly_count: int,
) -> str:
    return (
        f"Total spend was INR {total_inr} and USD {total_usd}. "
        f"The pipeline flagged {anomaly_count} anomalous transaction(s)."
    )
