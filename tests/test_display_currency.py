"""Display currency: cross-wallet totals (dashboard, stats, budgets) render in a
user-chosen currency via the stored exchange rate, while per-wallet balances stay
in their own currency. Stored money is unchanged — only the presentation is."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.currency import convert_from_base
from app.domains.rates.models import ExchangeRate
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


def test_convert_from_base_math() -> None:
    # Base passes through.
    assert convert_from_base(123, "VND", 1.0) == 123
    # 262500 VND at 25000 VND/USD → $10.50 → 1050 USD-minor.
    assert convert_from_base(262500, "USD", 25000.0) == 1050
    # 165000 VND at 165 VND/JPY → 1000 yen (0 decimals).
    assert convert_from_base(165000, "JPY", 165.0) == 1000


def test_base_to_target(db_session: Session) -> None:
    _seed_rate(db_session, "USD", 25000.0)
    conv = CurrencyConverter(db_session, "USD")
    assert conv.base_to_target(250000) == 1000  # 250000 VND → $10.00
    # Default target is the base currency (pass-through).
    assert CurrencyConverter(db_session).base_to_target(250000) == 250000
    # A target with no stored rate degrades to base rather than mis-scaling.
    assert CurrencyConverter(db_session, "EUR").base_to_target(250000) == 250000


def test_dashboard_totals_in_display_currency(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    _seed_rate(db_session, "USD", 25000.0)
    vnd = _new_wallet(client, auth_headers, name="VND", currency="VND")
    client.post(
        "/transactions",
        json={"wallet_rid": vnd["rid"], "type": "income", "amount": 250000},
        headers=auth_headers,
    )
    # Default: base currency.
    base = client.get("/dashboard/summary", headers=auth_headers).json()
    assert base["total_income"] == 250000
    assert base["currency"] == "VND"
    # Display in USD: 250000 VND / 25000 → $10.00 = 1000 minor.
    usd = client.get(
        "/dashboard/summary?display_currency=USD", headers=auth_headers
    ).json()
    assert usd["total_income"] == 1000
    assert usd["currency"] == "USD"
    # Per-wallet balance stays in the wallet's own currency, untouched.
    assert usd["wallets"][0]["balance"] == 250000
    assert usd["wallets"][0]["currency"] == "VND"


def test_unsupported_display_currency_is_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/dashboard/summary?display_currency=ZZZ", headers=auth_headers)
    assert resp.status_code == 422


def test_stats_monthly_in_display_currency(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    _seed_rate(db_session, "USD", 25000.0)
    vnd = _new_wallet(client, auth_headers, name="VND", currency="VND")
    client.post(
        "/transactions",
        json={"wallet_rid": vnd["rid"], "type": "expense", "amount": 500000},
        headers=auth_headers,
    )
    points = client.get(
        "/stats/monthly?months=1&display_currency=USD", headers=auth_headers
    ).json()
    assert points[-1]["expense"] == 2000  # 500000 VND / 25000 → $20.00 = 2000 minor


def test_calendar_totals_in_display_currency(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    _seed_rate(db_session, "USD", 25000.0)
    usd = _new_wallet(client, auth_headers, name="USD", currency="USD")
    # $20 income + $5 expense on the same day → net rendered in USD.
    client.post(
        "/transactions",
        json={
            "wallet_rid": usd["rid"],
            "type": "income",
            "amount": 2000,
            "occurred_on": "2026-06-10",
        },
        headers=auth_headers,
    )
    client.post(
        "/transactions",
        json={
            "wallet_rid": usd["rid"],
            "type": "expense",
            "amount": 500,
            "occurred_on": "2026-06-10",
        },
        headers=auth_headers,
    )
    days = client.get(
        "/stats/calendar?year=2026&month=6&display_currency=USD", headers=auth_headers
    ).json()
    day = {d["day"]: d for d in days}["2026-06-10"]
    assert day["income"] == 2000  # $20.00 in USD minor
    assert day["expense"] == 500  # $5.00
    # And in the base currency: $20 → 500000 VND, $5 → 125000 VND.
    base = client.get(
        "/stats/calendar?year=2026&month=6", headers=auth_headers
    ).json()
    base_day = {d["day"]: d for d in base}["2026-06-10"]
    assert base_day["income"] == 500_000
    assert base_day["expense"] == 125_000


def test_calendar_rejects_bad_month(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert (
        client.get("/stats/calendar?year=2026&month=13", headers=auth_headers).status_code
        == 422
    )


def test_budget_amount_round_trips_through_display_currency(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    _seed_rate(db_session, "USD", 25000.0)
    category_rid = client.get("/categories", headers=auth_headers).json()[0]["rid"]
    # Create a $100.00 (= 10000 USD-minor) family budget.
    created = client.post(
        "/budgets?scope=family&display_currency=USD",
        json={"category_rid": category_rid, "amount": 10000},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["amount"] == 10000  # echoed back in USD
    # Read back in the base currency: $100 → 2,500,000 VND.
    base = client.get("/budgets?scope=family", headers=auth_headers).json()
    assert base[0]["amount"] == 2_500_000
    # Read back in USD: 2,500,000 VND → $100.00.
    usd = client.get(
        "/budgets?scope=family&display_currency=USD", headers=auth_headers
    ).json()
    assert usd[0]["amount"] == 10000
