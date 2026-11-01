from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class OpenAlexDailyUsage(Base):
    """Persistent UTC-day account snapshot and ScholarSignal spend ledger."""

    __tablename__ = "openalex_daily_usage"

    utc_date: Mapped[date] = mapped_column(Date, primary_key=True)
    daily_limit_credits: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    remaining_credits: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    last_credits_used: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    reset_seconds: Mapped[int | None] = mapped_column(Integer)
    project_spend_usd: Mapped[Decimal] = mapped_column(
        Numeric(16, 8), nullable=False, default=Decimal("0")
    )
    reserved_usd: Mapped[Decimal] = mapped_column(
        Numeric(16, 8), nullable=False, default=Decimal("0")
    )
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    budget_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OpenAlexUsageEvent(Base):
    """Auditable request charges, reservations, and manual account reconciliations."""

    __tablename__ = "openalex_usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    utc_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(16, 8), nullable=False)
    actual_cost_known: Mapped[bool] = mapped_column(Boolean, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
