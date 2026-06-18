"""Exchange-rate routes — status of the stored rates and a manual refresh.

Rates are also refreshed automatically by a Celery-beat job every 12h; this lets
a signed-in user see when they were last updated and pull a fresh set on demand.
"""

from fastapi import APIRouter, HTTPException, status

from app.core.currency import BASE_CURRENCY
from app.core.deps import CurrentUser, SessionDep
from app.domains.rates.repository import RateRepository
from app.domains.rates.schemas import RateItem, RatesInfo
from app.domains.rates.tasks import fetch_exchange_rates

router = APIRouter(prefix="/rates", tags=["rates"])


def _info(repo: RateRepository) -> RatesInfo:
    rates = repo.all_rates()
    return RatesInfo(
        base_currency=BASE_CURRENCY,
        updated_at=repo.latest_updated_at(),
        count=repo.count(),
        rates=[
            RateItem(currency=code, rate_to_base=rate)
            for code, rate in sorted(rates.items())
        ],
    )


@router.get("", response_model=RatesInfo, summary="Exchange-rate status")
def get_rates(session: SessionDep, current_user: CurrentUser) -> RatesInfo:
    """When the stored exchange rates were last refreshed."""
    return _info(RateRepository(session))


@router.post("/refresh", response_model=RatesInfo, summary="Refresh rates now")
def refresh_rates(session: SessionDep, current_user: CurrentUser) -> RatesInfo:
    """Pull the latest rates from the public source right now (the same fetch the
    scheduled job runs). `503` if the source can't be reached."""
    try:
        fetch_exchange_rates(session)
    except (OSError, ValueError) as exc:
        # Network failure (URLError ⊂ OSError) or a bad/untrusted payload.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not reach the exchange-rate source",
        ) from exc
    return _info(RateRepository(session))
