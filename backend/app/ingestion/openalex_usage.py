from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import OpenAlexDailyUsage, OpenAlexUsageEvent

USD_PER_CREDIT = Decimal("0.0001")
DEFAULT_DAILY_CEILING_USD = Decimal("0.10")
USAGE_SNAPSHOT_MAX_AGE = timedelta(minutes=10)


def _decimal(value: Any) -> Decimal | None:
    if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and number >= 0 else None


@dataclass(frozen=True)
class OpenAlexRateLimit:
    limit_credits: Decimal | None
    remaining_credits: Decimal | None
    credits_used: Decimal | None
    reset_seconds: int | None
    cost_usd: Decimal | None

    @classmethod
    def from_response(
        cls,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None = None,
        *,
        now: datetime | None = None,
    ) -> "OpenAlexRateLimit":
        """Parse rate-limit headers and both current and legacy JSON envelopes.

        Headers are authoritative when present. If a JSON value disagrees with a
        header, that field is unknown instead of choosing a potentially stale value.
        OpenAlex currently returns USD budget fields in the body and credit counts
        in headers, so USD values are converted to credits at 10,000 credits/USD.
        """
        normalized_headers = {key.casefold(): value for key, value in headers.items()}
        body = payload if isinstance(payload, Mapping) else {}
        meta = body.get("meta")
        meta = meta if isinstance(meta, Mapping) else {}
        current_limit = _decimal(body.get("daily_budget_usd"))
        current_used = _decimal(body.get("daily_used_usd"))
        current_remaining = _decimal(body.get("daily_remaining_usd"))
        current_reset = _reset_seconds(body.get("resets_at"), now=now)
        legacy_limit = _decimal(meta.get("daily_budget_usd", meta.get("daily_limit_usd")))
        legacy_used = _decimal(meta.get("daily_used_usd", meta.get("daily_used")))
        legacy_remaining = _decimal(meta.get("daily_remaining_usd", meta.get("daily_remaining")))
        legacy_reset = _reset_seconds(meta.get("resets_at", meta.get("reset_at")), now=now)

        json_limit_usd = _coalesce(current_limit, legacy_limit)
        json_remaining_usd = _coalesce(current_remaining, legacy_remaining)
        limit = _resolve_value(
            _decimal(normalized_headers.get("x-ratelimit-limit")),
            json_limit_usd * Decimal("10000") if json_limit_usd is not None else None,
        )
        remaining = _resolve_value(
            _decimal(normalized_headers.get("x-ratelimit-remaining")),
            json_remaining_usd * Decimal("10000")
            if json_remaining_usd is not None
            else None,
        )
        credits = _decimal(normalized_headers.get("x-ratelimit-credits-used"))
        reset = _resolve_value(
            _integer(normalized_headers.get("x-ratelimit-reset")),
            _coalesce(current_reset, legacy_reset),
        )
        reset = (
            int(reset) if reset is not None else None
        )
        cost = _resolve_value(
            _decimal(meta.get("cost_usd", meta.get("cost"))),
            _coalesce(_decimal(body.get("request_cost_usd")), _decimal(body.get("cost_usd"))),
        )
        # daily_used is an account running total, not this request's cost.
        # It can validate remaining = limit - used, but never supplies credits_used.
        if current_limit is not None and current_used is not None and current_remaining is not None:
            if current_limit != current_used + current_remaining:
                limit = remaining = None
        if legacy_limit is not None and legacy_used is not None and legacy_remaining is not None:
            if legacy_limit != legacy_used + legacy_remaining:
                limit = remaining = None
        if cost is None and credits is not None:
            cost = credits * USD_PER_CREDIT
        if cost is None:
            legacy_cost = _decimal(meta.get("cost"))
            cost = legacy_cost
        if credits is None and cost is not None:
            credits = cost / USD_PER_CREDIT
        if credits is not None and cost is not None and credits * USD_PER_CREDIT != cost:
            credits = cost = None
        return cls(limit, remaining, credits, reset, cost)

    @property
    def complete(self) -> bool:
        return (
            self.limit_credits is not None
            and self.remaining_credits is not None
            and self.remaining_credits <= self.limit_credits
            and self.credits_used is not None
            and self.reset_seconds is not None
            and self.cost_usd is not None
        )


def _coalesce(primary: Decimal | int | None, fallback: Decimal | int | None):
    if primary is not None and fallback is not None:
        return primary if primary == fallback else None
    return primary if primary is not None else fallback


def _resolve_value(header: Decimal | int | None, body: Decimal | int | None):
    if header is not None and body is not None and header != body:
        return None
    return header if header is not None else body


def _integer(value: Any) -> int | None:
    parsed = _decimal(value)
    return int(parsed) if parsed is not None and parsed == parsed.to_integral_value() else None


def _reset_seconds(value: Any, *, now: datetime | None = None) -> int | None:
    if isinstance(value, (str, datetime)):
        try:
            reset_at = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
            if reset_at.tzinfo is None:
                return None
            current = now or datetime.now(UTC)
            if current.tzinfo is None:
                return None
            seconds = int((reset_at.astimezone(UTC) - current.astimezone(UTC)).total_seconds())
            return seconds if seconds >= 0 else None
        except (ValueError, TypeError, OverflowError):
            return None
    return _integer(value)


class OpenAlexBudgetError(RuntimeError):
    """Raised when a safe OpenAlex request cannot be budgeted."""


@dataclass(frozen=True)
class BudgetReservation:
    utc_date: date
    amount_usd: Decimal


class OpenAlexBudgetGuard:
    """Persistent, fail-closed OpenAlex usage guard, keyed by UTC calendar day."""

    def __init__(
        self,
        ceiling_usd: Decimal = DEFAULT_DAILY_CEILING_USD,
        snapshot_max_age: timedelta = USAGE_SNAPSHOT_MAX_AGE,
    ):
        if ceiling_usd <= 0:
            raise ValueError("OpenAlex daily ceiling must be positive")
        self.ceiling_usd = ceiling_usd
        self.snapshot_max_age = snapshot_max_age

    def usage_for_day(self, session: Session, *, now: datetime | None = None) -> Decimal:
        current = self._now(now)
        row = self._get_row(session, current.date(), lock=False)
        return Decimal(row.project_spend_usd or 0) if row is not None else Decimal("0")

    def record_manual_reconciliation(
        self,
        session: Session,
        *,
        daily_budget_usd: Decimal,
        daily_used_usd: Decimal,
        daily_remaining_usd: Decimal,
        reset_at: datetime,
        evidence: str,
        now: datetime | None = None,
    ) -> None:
        """Persist a human-observed dashboard snapshot without rewriting history."""
        current = self._now(now)
        limit = _decimal(daily_budget_usd)
        used = _decimal(daily_used_usd)
        remaining = _decimal(daily_remaining_usd)
        if (
            limit is None
            or used is None
            or remaining is None
            or limit <= 0
            or used + remaining != limit
            or reset_at.tzinfo is None
            or reset_at.astimezone(UTC) <= current
            or not evidence.strip()
        ):
            raise OpenAlexBudgetError("Manual usage evidence is incomplete or inconsistent.")
        row = self._get_row(session, current.date(), lock=True)
        if row is None:
            row = OpenAlexDailyUsage(utc_date=current.date())
            session.add(row)
            session.flush()
        previous_spend = Decimal(row.project_spend_usd or 0)
        # Treat the displayed account usage as a conservative project baseline. The
        # original unknown-cost event remains intact and is offset only by this audit entry.
        row.project_spend_usd = used
        row.daily_limit_credits = limit / USD_PER_CREDIT
        row.remaining_credits = remaining / USD_PER_CREDIT
        row.last_credits_used = None  # Dashboard totals do not reveal prior request cost.
        row.reset_seconds = int((reset_at.astimezone(UTC) - current).total_seconds())
        row.budget_verified = True
        row.checked_at = current
        row.updated_at = current
        session.add(
            OpenAlexUsageEvent(
                utc_date=current.date(),
                event_type="manual_reconciliation",
                amount_usd=used - previous_spend,
                actual_cost_known=False,
                details={
                    "evidence": evidence,
                    "daily_budget_usd": str(limit),
                    "daily_used_usd": str(used),
                    "daily_remaining_usd": str(remaining),
                    "reset_at_utc": reset_at.astimezone(UTC).isoformat(),
                    "prior_project_spend_usd": str(previous_spend),
                    "prior_request_cost": "unknown",
                },
            )
        )
        session.commit()

    @staticmethod
    def _now(now: datetime | None) -> datetime:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            raise ValueError("OpenAlex budget timestamps must include a timezone")
        return current.astimezone(UTC)

    @staticmethod
    def _get_row(session: Session, utc_date: date, *, lock: bool) -> OpenAlexDailyUsage | None:
        statement = select(OpenAlexDailyUsage).where(OpenAlexDailyUsage.utc_date == utc_date)
        if lock:
            statement = statement.with_for_update()
        return session.scalar(statement)

    @staticmethod
    def _deny(session: Session, message: str) -> None:
        session.rollback()
        raise OpenAlexBudgetError(message)

    def reserve(
        self,
        session: Session,
        max_cost_usd: Decimal,
        *,
        now: datetime | None = None,
        allow_initial_budget_check: bool = False,
    ) -> BudgetReservation:
        current = self._now(now)
        amount = _decimal(max_cost_usd)
        if amount is None or amount <= 0:
            raise ValueError("A positive, valid maximum request cost is required")
        day = current.date()
        row = self._get_row(session, day, lock=True)
        if row is None:
            if not allow_initial_budget_check:
                self._deny(session, "OpenAlex budget is unverified; check the rate limit first.")
            row = OpenAlexDailyUsage(utc_date=day)
            session.add(row)
            session.flush()
        elif not allow_initial_budget_check:
            checked_at = row.checked_at
            if checked_at is not None and checked_at.tzinfo is None:
                # SQLite drops timezone metadata on round-trip; stored values are UTC.
                checked_at = checked_at.replace(tzinfo=UTC)
            if (
                not row.budget_verified
                or checked_at is None
                or checked_at.astimezone(UTC) + self.snapshot_max_age < current
            ):
                self._deny(session, "OpenAlex budget is unverified or stale; refresh it first.")

        spent = Decimal(row.project_spend_usd or 0)
        reserved = Decimal(row.reserved_usd or 0)
        if spent + reserved + amount > self.ceiling_usd:
            self._deny(session, "OpenAlex daily project spending ceiling would be exceeded.")
        if row.daily_limit_credits is not None and row.remaining_credits is not None:
            account_used = (
                Decimal(row.daily_limit_credits) - Decimal(row.remaining_credits)
            ) * USD_PER_CREDIT
            account_remaining = Decimal(row.remaining_credits) * USD_PER_CREDIT
            if account_used > self.ceiling_usd:
                self._deny(session, "Current OpenAlex daily usage exceeds the project ceiling.")
            if account_remaining < amount:
                self._deny(session, "OpenAlex account budget is insufficient for this request.")
        elif not allow_initial_budget_check:
            self._deny(session, "OpenAlex account budget is unavailable.")

        row.reserved_usd = reserved + amount
        row.updated_at = current
        session.add(
            OpenAlexUsageEvent(
                utc_date=day,
                event_type="request_reserved",
                amount_usd=amount,
                actual_cost_known=False,
                details={"maximum_reserved_usd": str(amount)},
            )
        )
        session.commit()
        return BudgetReservation(day, amount)

    def reserve_budget_check(
        self, session: Session, *, now: datetime | None = None
    ) -> BudgetReservation:
        """Reserve all remaining daily headroom while bootstrapping/refreshing a snapshot."""
        current = self._now(now)
        row = self._get_row(session, current.date(), lock=True)
        spent = Decimal(row.project_spend_usd or 0) if row is not None else Decimal("0")
        reserved = Decimal(row.reserved_usd or 0) if row is not None else Decimal("0")
        allowance = self.ceiling_usd - spent - reserved
        session.rollback()
        if allowance <= 0:
            raise OpenAlexBudgetError("OpenAlex daily project spending ceiling is exhausted.")
        # A check request is not presumed free; reserve every remaining cent of project headroom.
        return self.reserve(
            session, allowance, now=current, allow_initial_budget_check=True
        )

    def record_response(
        self,
        session: Session,
        reservation: BudgetReservation,
        rate_limit: OpenAlexRateLimit,
        *,
        now: datetime | None = None,
    ) -> None:
        current = self._now(now)
        row = self._get_row(session, reservation.utc_date, lock=True)
        if row is None:
            self._deny(session, "OpenAlex usage reservation was lost.")
        reserved = Decimal(row.reserved_usd or 0)
        row.reserved_usd = max(Decimal("0"), reserved - reservation.amount_usd)
        # Unknown actual cost is charged at the full reservation and invalidates the snapshot.
        actual_cost = rate_limit.cost_usd
        row.project_spend_usd = Decimal(row.project_spend_usd or 0) + (
            actual_cost if actual_cost is not None else reservation.amount_usd
        )
        row.request_count = (row.request_count or 0) + 1
        row.daily_limit_credits = rate_limit.limit_credits
        row.remaining_credits = rate_limit.remaining_credits
        row.last_credits_used = rate_limit.credits_used
        row.reset_seconds = rate_limit.reset_seconds
        row.budget_verified = rate_limit.complete
        row.checked_at = current if rate_limit.complete else None
        row.updated_at = current
        session.add(
            OpenAlexUsageEvent(
                utc_date=reservation.utc_date,
                event_type="request_result",
                amount_usd=(actual_cost if actual_cost is not None else reservation.amount_usd),
                actual_cost_known=actual_cost is not None,
                details={
                    "actual_cost_usd": str(actual_cost) if actual_cost is not None else None,
                    "fallback_charge_usd": str(reservation.amount_usd)
                    if actual_cost is None
                    else None,
                    "limit_credits": str(rate_limit.limit_credits)
                    if rate_limit.limit_credits is not None
                    else None,
                    "remaining_credits": str(rate_limit.remaining_credits)
                    if rate_limit.remaining_credits is not None
                    else None,
                    "credits_used": str(rate_limit.credits_used)
                    if rate_limit.credits_used is not None
                    else None,
                    "reset_seconds": rate_limit.reset_seconds,
                },
            )
        )
        session.commit()

    def record_unknown_result(
        self,
        session: Session,
        reservation: BudgetReservation,
        *,
        now: datetime | None = None,
    ) -> None:
        """Consume the reservation and fail closed when an outcome/cost is unknown."""
        current = self._now(now)
        row = self._get_row(session, reservation.utc_date, lock=True)
        if row is None:
            self._deny(session, "OpenAlex usage reservation was lost.")
        row.reserved_usd = max(
            Decimal("0"), Decimal(row.reserved_usd or 0) - reservation.amount_usd
        )
        row.project_spend_usd = Decimal(row.project_spend_usd or 0) + reservation.amount_usd
        row.budget_verified = False
        row.checked_at = None
        row.request_count = (row.request_count or 0) + 1
        row.updated_at = current
        session.add(
            OpenAlexUsageEvent(
                utc_date=reservation.utc_date,
                event_type="request_result_unknown",
                amount_usd=reservation.amount_usd,
                actual_cost_known=False,
                details={"conservative_charge_usd": str(reservation.amount_usd)},
            )
        )
        session.commit()
