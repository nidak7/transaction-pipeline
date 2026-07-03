from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from statistics import median

from app.services.cleaner import CleanedTransaction

DOMESTIC_ONLY_MERCHANTS = {"SWIGGY", "OLA", "IRCTC"}


def account_median_amounts(
    transactions: list[CleanedTransaction],
) -> dict[str, Decimal]:
    grouped: dict[str, list[Decimal]] = defaultdict(list)
    for transaction in transactions:
        grouped[transaction.account_id].append(transaction.amount)

    return {
        account_id: Decimal(str(median(amounts)))
        for account_id, amounts in grouped.items()
        if amounts
    }


def detect_anomalies(
    transactions: list[CleanedTransaction],
) -> list[CleanedTransaction]:
    medians = account_median_amounts(transactions)
    for transaction in transactions:
        reasons = _anomaly_reasons(transaction, medians)
        if reasons:
            transaction.is_anomaly = True
            transaction.anomaly_reason = "; ".join(reasons)
    return transactions


def _anomaly_reasons(
    transaction: CleanedTransaction,
    medians: dict[str, Decimal],
) -> list[str]:
    reasons: list[str] = []
    account_median = medians.get(transaction.account_id)
    if (
        account_median is not None
        and account_median > 0
        and transaction.amount > account_median * Decimal("3")
    ):
        reasons.append("Amount exceeds 3x account median")

    if transaction.currency == "USD" and _is_domestic_only_merchant(
        transaction.merchant,
    ):
        reasons.append("USD used with domestic merchant")

    return reasons


def _is_domestic_only_merchant(merchant: str) -> bool:
    normalized = merchant.upper()
    return any(name in normalized for name in DOMESTIC_ONLY_MERCHANTS)
