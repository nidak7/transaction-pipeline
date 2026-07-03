from decimal import Decimal

import pandas as pd
import pytest

from app.services.cleaner import (
    UNCATEGORISED,
    CleaningError,
    clean_frame,
    parse_amount,
    parse_currency,
    parse_transaction_date,
)


def test_date_parser_accepts_assignment_formats() -> None:
    assert parse_transaction_date("04-09-2024").isoformat() == "2024-09-04"
    assert parse_transaction_date("2024/02/05").isoformat() == "2024-02-05"


def test_currency_and_amount_parser_normalize_values() -> None:
    assert parse_currency("inr") == "INR"
    assert parse_amount("$1,234.567") == Decimal("1234.57")


def test_clean_frame_removes_duplicates_and_fills_missing_category() -> None:
    frame = pd.DataFrame(
        [
            {
                "txn_id": "",
                "date": "04-09-2024",
                "merchant": "Flipkart",
                "amount": "$100.00",
                "currency": "inr",
                "status": "success",
                "category": "",
                "account_id": "ACC1",
                "notes": "",
            },
            {
                "txn_id": "",
                "date": "04-09-2024",
                "merchant": "Flipkart",
                "amount": "$100.00",
                "currency": "inr",
                "status": "success",
                "category": "",
                "account_id": "ACC1",
                "notes": "",
            },
        ],
    )

    result = clean_frame(frame)

    assert result.row_count_raw == 2
    assert result.row_count_clean == 1
    assert result.transactions[0].category == UNCATEGORISED
    assert result.transactions[0].status == "SUCCESS"
    assert result.transactions[0].txn_id.startswith("generated-")


def test_clean_frame_rejects_invalid_amount() -> None:
    frame = pd.DataFrame(
        [
            {
                "txn_id": "TXN1",
                "date": "04-09-2024",
                "merchant": "Flipkart",
                "amount": "not-money",
                "currency": "INR",
                "status": "SUCCESS",
                "category": "Shopping",
                "account_id": "ACC1",
                "notes": "",
            },
        ],
    )

    with pytest.raises(CleaningError):
        clean_frame(frame)
