from datetime import date
from decimal import Decimal

from app.services.anomaly import account_median_amounts, detect_anomalies
from app.services.cleaner import CleanedTransaction


def transaction(
    *,
    merchant: str,
    amount: str,
    currency: str = "INR",
    account_id: str = "ACC1",
) -> CleanedTransaction:
    return CleanedTransaction(
        txn_id=f"{merchant}-{amount}",
        date=date(2024, 1, 1),
        merchant=merchant,
        amount=Decimal(amount),
        currency=currency,
        status="SUCCESS",
        category="Shopping",
        account_id=account_id,
        notes="",
    )


def test_account_median_amounts() -> None:
    medians = account_median_amounts(
        [
            transaction(merchant="A", amount="100"),
            transaction(merchant="B", amount="200"),
            transaction(merchant="C", amount="300"),
        ],
    )

    assert medians["ACC1"] == Decimal("200")


def test_detects_statistical_and_domestic_currency_anomalies() -> None:
    transactions = [
        transaction(merchant="A", amount="100"),
        transaction(merchant="B", amount="110"),
        transaction(merchant="C", amount="120"),
        transaction(merchant="Luxury", amount="1000"),
        transaction(merchant="Swiggy", amount="50", currency="USD"),
    ]

    detect_anomalies(transactions)

    assert transactions[3].is_anomaly is True
    assert "3x account median" in transactions[3].anomaly_reason
    assert transactions[4].is_anomaly is True
    assert "domestic merchant" in transactions[4].anomaly_reason
