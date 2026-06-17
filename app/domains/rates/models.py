"""Exchange-rate ORM model.

One row per non-base currency: ``rate_to_base`` is how many BASE-currency (VND)
major units equal one major unit of ``currency`` (e.g. USD → 25000). Refreshed by
a scheduled job; seeded with a static snapshot so conversion works immediately.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), unique=True, index=True)
    # BASE major units per 1 major unit of ``currency``.
    rate_to_base: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
