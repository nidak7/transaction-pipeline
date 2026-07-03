from datetime import date
from decimal import Decimal

import pytest

from app.llm.base import LLMClient, LLMError
from app.services.classifier import (
    RetryPolicy,
    classify_uncategorized_transactions,
    parse_classification_response,
)
from app.services.cleaner import UNCATEGORISED, CleanedTransaction
from app.services.summarizer import generate_summary, parse_summary_response


class FakeLLM(LLMClient):
    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = responses
        self.calls = 0

    def generate_json(self, prompt: str) -> str:
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def transaction(txn_id: str = "TXN1") -> CleanedTransaction:
    return CleanedTransaction(
        txn_id=txn_id,
        date=date(2024, 1, 1),
        merchant="Swiggy",
        amount=Decimal("100.00"),
        currency="INR",
        status="SUCCESS",
        category=UNCATEGORISED,
        account_id="ACC1",
        notes="",
    )


def test_parse_classification_response_validates_supported_categories() -> None:
    parsed = parse_classification_response(
        '{"classifications":[{"txn_id":"TXN1","category":"Food"}]}',
    )

    assert parsed == {"TXN1": "Food"}


def test_parse_classification_response_rejects_invalid_category() -> None:
    with pytest.raises(LLMError):
        parse_classification_response(
            '{"classifications":[{"txn_id":"TXN1","category":"Crypto"}]}',
        )


def test_classification_retries_then_succeeds() -> None:
    client = FakeLLM(
        [
            LLMError("temporary"),
            LLMError("temporary"),
            '{"classifications":[{"txn_id":"TXN1","category":"Food"}]}',
        ],
    )
    txns = [transaction()]

    classify_uncategorized_transactions(
        txns,
        client=client,
        batch_size=10,
        retry_policy=RetryPolicy(base_delay_seconds=0, sleep=lambda _: None),
    )

    assert client.calls == 3
    assert txns[0].category == "Food"
    assert txns[0].llm_failed is False


def test_classification_marks_batch_failed_after_retries() -> None:
    client = FakeLLM([LLMError("down"), LLMError("down"), LLMError("down")])
    txns = [transaction()]

    classify_uncategorized_transactions(
        txns,
        client=client,
        batch_size=10,
        retry_policy=RetryPolicy(base_delay_seconds=0, sleep=lambda _: None),
    )

    assert txns[0].category == UNCATEGORISED
    assert txns[0].llm_failed is True


def test_parse_summary_response_validates_shape() -> None:
    summary = parse_summary_response(
        """
        {
          "spend_by_currency": {"INR": "100.00"},
          "top_merchants": [{"merchant": "Swiggy", "total": "100.00"}],
          "anomaly_count": 0,
          "narrative": "Small food spend.",
          "risk_level": "low"
        }
        """,
    )

    assert summary.risk_level == "low"


def test_generate_summary_uses_fallback_when_llm_fails() -> None:
    txns = [transaction()]
    client = FakeLLM([LLMError("down"), LLMError("down"), LLMError("down")])

    summary = generate_summary(
        txns,
        client=client,
        retry_policy=RetryPolicy(base_delay_seconds=0, sleep=lambda _: None),
    )

    assert summary.total_spend_inr == Decimal("100.00")
    assert summary.risk_level == "low"
    assert "Total spend" in summary.narrative
