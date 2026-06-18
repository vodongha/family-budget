"""Multi-currency: conversion math, per-wallet currency, converted totals,
cross-currency transfer guard, and the rate-fetch parser."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.domains.rates.tasks as rates_tasks
from app.core.currency import convert_minor
from app.domains.rates.models import ExchangeRate
from app.domains.rates.repository import RateRepository
from app.domains.rates.service import CurrencyConverter


def _seed_rate(db_session: Session, currency: str, rate_to_base: float) -> None:
    db_session.add(ExchangeRate(currency=currency, rate_to_base=rate_to_base))
    db_session.commit()


def _new_wallet(client: TestClient, headers: dict[str, str], **body: object) -> dict:
    payload = {"name": "W", "visibility": "family"}
    payload.update(body)
    resp = client.post("/wallets", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_supported_currencies_expanded() -> None:
    from app.core.currency import decimals, is_supported

    # A broad world set is supported, with correct ISO-4217 decimals.
    assert is_supported("CAD") and is_supported("CHF") and is_supported("KWD")
    assert decimals("KWD") == 3  # three-decimal Gulf currency
    assert decimals("CLP") == 0  # zero-decimal
    assert decimals("CAD") == 2
    assert not is_supported("ZZZ")


def test_convert_minor_math() -> None:
    # Base currency is unchanged.
    assert convert_minor(123, "VND", 1.0) == 123
    # USD has 2 decimals: 1050 minor = $10.50; at 25000 VND/USD → 262500 VND.
    assert convert_minor(1050, "USD", 25000.0) == 262500
    # JPY has 0 decimals: 1000 yen at 165 VND/JPY → 165000 VND.
    assert convert_minor(1000, "JPY", 165.0) == 165000


def test_converter_uses_stored_rate(db_session: Session) -> None:
    _seed_rate(db_session, "USD", 25000.0)
    conv = CurrencyConverter(db_session)
    assert conv.to_base(1000, "USD") == 250000
    assert conv.to_base(500, "VND") == 500  # base passes through
    # Unknown currency with no rate falls back to as-is (never silently dropped).
    assert conv.to_base(42, "EUR") == 42


def test_create_wallet_with_currency(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    w = _new_wallet(client, auth_headers, name="USD cash", currency="USD")
    assert w["currency"] == "USD"
    # Default is the base currency.
    w2 = _new_wallet(client, auth_headers, name="Đồng")
    assert w2["currency"] == "VND"


def test_create_wallet_rejects_unsupported_currency(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/wallets",
        json={"name": "X", "visibility": "family", "currency": "ZZZ"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_cross_currency_transfer_blocked(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    vnd = _new_wallet(client, auth_headers, name="VND", currency="VND")
    usd = _new_wallet(client, auth_headers, name="USD", currency="USD")
    resp = client.post(
        "/transfers",
        json={
            "from_wallet_rid": vnd["rid"],
            "to_wallet_rid": usd["rid"],
            "amount": 1000,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_dashboard_totals_convert_mixed_currencies(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    _seed_rate(db_session, "USD", 25000.0)
    vnd = _new_wallet(client, auth_headers, name="VND", currency="VND")
    usd = _new_wallet(client, auth_headers, name="USD", currency="USD")
    # 100000 VND income + $10 (1000 cents) income → 100000 + 250000 = 350000 VND.
    client.post(
        "/transactions",
        json={"wallet_rid": vnd["rid"], "type": "income", "amount": 100000},
        headers=auth_headers,
    )
    client.post(
        "/transactions",
        json={"wallet_rid": usd["rid"], "type": "income", "amount": 1000},
        headers=auth_headers,
    )
    summary = client.get("/dashboard/summary", headers=auth_headers).json()
    assert summary["total_income"] == 350000
    # Per-wallet balances stay in their own currency.
    by_rid = {w["rid"]: w for w in summary["wallets"]}
    assert by_rid[usd["rid"]]["balance"] == 1000
    assert by_rid[usd["rid"]]["currency"] == "USD"


def test_fetch_exchange_rates_parses_and_inverts(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # open.er-api.com returns "1 base = N currency"; we store the inverse.
    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"rates": {"USD": 0.00004, "VND": 1}}'

    monkeypatch.setattr(
        rates_tasks.urllib.request, "urlopen", lambda *a, **k: _FakeResp()
    )
    updated = rates_tasks.fetch_exchange_rates(db_session)
    assert updated >= 1
    rates = RateRepository(db_session).all_rates()
    # 1 VND = 0.00004 USD → 1 USD = 25000 VND.
    assert rates["USD"] == pytest.approx(25000.0)
