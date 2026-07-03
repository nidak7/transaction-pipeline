from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd

from app.utils.csv_contract import REQUIRED_COLUMNS, REQUIRED_NON_EMPTY_COLUMNS

UNCATEGORISED = "Uncategorised"
SUPPORTED_CURRENCIES = {"INR", "USD"}
SUPPORTED_STATUSES = {"SUCCESS", "FAILED", "PENDING"}
DATE_FORMATS = ("%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d")
MONEY_QUANTIZER = Decimal("0.01")


class CleaningError(ValueError):
    pass


@dataclass(slots=True)
class CleanedTransaction:
    txn_id: str
    date: date
    merchant: str
    amount: Decimal
    currency: str
    status: str
    category: str
    account_id: str
    notes: str
    is_anomaly: bool = False
    anomaly_reason: str | None = None
    llm_category: str | None = None
    llm_raw_response: str | None = None
    llm_failed: bool = False


@dataclass(frozen=True, slots=True)
class CleaningResult:
    row_count_raw: int
    row_count_clean: int
    transactions: list[CleanedTransaction]


def clean_csv(path: Path) -> CleaningResult:
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception as exc:
        raise CleaningError("Unable to read uploaded CSV file.") from exc

    return clean_frame(frame)


def clean_frame(frame: pd.DataFrame) -> CleaningResult:
    columns = {str(column).strip() for column in frame.columns}
    missing_columns = REQUIRED_COLUMNS - columns
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise CleaningError(f"CSV is missing required columns: {missing}.")

    normalized = frame.copy()
    normalized.columns = [str(column).strip() for column in normalized.columns]
    normalized = normalized[list(REQUIRED_COLUMNS)]
    normalized = normalized.map(_strip_cell)

    row_count_raw = len(normalized)
    if row_count_raw == 0:
        raise CleaningError("Uploaded CSV must contain at least one transaction.")

    normalized = normalized.drop_duplicates(ignore_index=True)

    transactions = [
        _clean_row(row_number=index + 2, row=row)
        for index, row in normalized.iterrows()
    ]
    return CleaningResult(
        row_count_raw=row_count_raw,
        row_count_clean=len(transactions),
        transactions=transactions,
    )


def parse_transaction_date(value: str) -> date:
    cleaned = value.strip()
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, date_format).date()
        except ValueError:
            continue
    raise CleaningError(f"Invalid transaction date: {value}.")


def parse_amount(value: str) -> Decimal:
    cleaned = value.strip().replace("$", "").replace(",", "")
    if cleaned == "":
        raise CleaningError("Amount cannot be empty.")
    try:
        return Decimal(cleaned).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise CleaningError(f"Invalid amount: {value}.") from exc


def parse_currency(value: str) -> str:
    currency = value.strip().upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise CleaningError(f"Unsupported currency: {value}.")
    return currency


def parse_status(value: str) -> str:
    status = value.strip().upper()
    if status not in SUPPORTED_STATUSES:
        raise CleaningError(f"Unsupported transaction status: {value}.")
    return status


def _clean_row(row_number: int, row: pd.Series[Any]) -> CleanedTransaction:
    missing_values = [
        column for column in REQUIRED_NON_EMPTY_COLUMNS if _cell(row[column]) == ""
    ]
    if missing_values:
        missing = ", ".join(sorted(missing_values))
        raise CleaningError(
            f"CSV row {row_number} is missing required values: {missing}.",
        )

    merchant = _cell(row["merchant"])
    account_id = _cell(row["account_id"])
    category = _cell(row["category"]) or UNCATEGORISED

    return CleanedTransaction(
        txn_id=_cell(row["txn_id"]) or _generated_txn_id(row_number, row),
        date=parse_transaction_date(_cell(row["date"])),
        merchant=merchant,
        amount=parse_amount(_cell(row["amount"])),
        currency=parse_currency(_cell(row["currency"])),
        status=parse_status(_cell(row["status"])),
        category=category,
        account_id=account_id,
        notes=_cell(row["notes"]),
    )


def _strip_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _cell(value: object) -> str:
    return _strip_cell(value)


def _generated_txn_id(row_number: int, row: pd.Series[Any]) -> str:
    fingerprint = "|".join(
        _cell(row[column])
        for column in (
            "date",
            "merchant",
            "amount",
            "currency",
            "status",
            "account_id",
        )
    )
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:12]
    return f"generated-{row_number}-{digest}"
