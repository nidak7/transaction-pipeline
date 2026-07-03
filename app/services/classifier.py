from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import TypeVar

from app.llm.base import LLMClient, LLMError
from app.services.cleaner import UNCATEGORISED, CleanedTransaction

logger = logging.getLogger(__name__)

SUPPORTED_CATEGORIES = {
    "Food",
    "Shopping",
    "Travel",
    "Transport",
    "Utilities",
    "Entertainment",
    "Cash Withdrawal",
    "Other",
}
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    sleep: Callable[[float], None] = time.sleep


def classify_uncategorized_transactions(
    transactions: list[CleanedTransaction],
    *,
    client: LLMClient,
    batch_size: int,
    retry_policy: RetryPolicy,
    job_id: str | None = None,
) -> list[CleanedTransaction]:
    uncategorized = [
        transaction
        for transaction in transactions
        if transaction.category == UNCATEGORISED
    ]
    for batch in _batches(uncategorized, batch_size):
        prompt = _classification_prompt(batch)
        try:
            operation = partial(_request_classification, client, prompt)
            classifications = _call_with_retry(
                operation,
                retry_policy=retry_policy,
                stage="llm_classification",
                job_id=job_id,
            )
        except LLMError:
            logger.error(
                "LLM classification failed for batch.",
                extra={"job_id": job_id, "stage": "llm_classification"},
                exc_info=True,
            )
            for transaction in batch:
                transaction.llm_failed = True
            continue

        for transaction in batch:
            category = classifications.get(transaction.txn_id)
            if category is None:
                transaction.llm_failed = True
                continue
            transaction.category = category
            transaction.llm_category = category

    return transactions


def parse_classification_response(raw_response: str) -> dict[str, str]:
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise LLMError("Classification response was not valid JSON.") from exc

    records = payload.get("classifications")
    if not isinstance(records, list):
        raise LLMError("Classification response must contain a classifications list.")

    parsed: dict[str, str] = {}
    for item in records:
        if not isinstance(item, dict):
            raise LLMError("Classification item must be an object.")
        txn_id = item.get("txn_id")
        category = item.get("category")
        if not isinstance(txn_id, str) or not isinstance(category, str):
            raise LLMError("Classification item is missing txn_id or category.")
        if category not in SUPPORTED_CATEGORIES:
            raise LLMError(f"Unsupported LLM category: {category}.")
        parsed[txn_id] = category
    return parsed


def _request_classification(client: LLMClient, prompt: str) -> dict[str, str]:
    return parse_classification_response(client.generate_json(prompt))


def _call_with_retry(
    operation: Callable[[], T],
    *,
    retry_policy: RetryPolicy,
    stage: str,
    job_id: str | None,
) -> T:
    last_error: LLMError | None = None
    for attempt in range(1, retry_policy.max_attempts + 1):
        try:
            return operation()
        except LLMError as exc:
            last_error = exc
            logger.warning(
                "LLM call failed.",
                extra={"job_id": job_id, "stage": stage, "attempt": attempt},
                exc_info=exc,
            )
            if attempt < retry_policy.max_attempts:
                retry_policy.sleep(
                    retry_policy.base_delay_seconds * (2 ** (attempt - 1)),
                )

    raise last_error or LLMError("LLM call failed.")


def _classification_prompt(batch: list[CleanedTransaction]) -> str:
    rows = [
        {
            "txn_id": transaction.txn_id,
            "merchant": transaction.merchant,
            "amount": str(transaction.amount),
            "currency": transaction.currency,
            "notes": transaction.notes,
        }
        for transaction in batch
    ]
    categories = ", ".join(sorted(SUPPORTED_CATEGORIES))
    return (
        "Classify each transaction into exactly one supported category. "
        f"Supported categories: {categories}. "
        "Return only JSON in this shape: "
        '{"classifications":[{"txn_id":"...","category":"Food"}]}. '
        f"Transactions: {json.dumps(rows)}"
    )


def _batches(items: list[T], batch_size: int) -> list[list[T]]:
    size = max(batch_size, 1)
    return [items[index : index + size] for index in range(0, len(items), size)]
