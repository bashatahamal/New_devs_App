from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List

CENTS = Decimal("0.01")


def to_cents(amount: Any) -> Decimal:
    """Round a monetary amount to cents once, half-up, using exact decimal arithmetic."""
    return Decimal(str(amount)).quantize(CENTS, rounding=ROUND_HALF_UP)


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int, db_session=None) -> Decimal:
    """
    Calculates revenue for a calendar month in the property's local timezone.

    Month boundaries are midnight on the 1st in properties.timezone, not UTC:
    a check-in at 2024-02-29 23:30 UTC is 2024-03-01 00:30 in Europe/Paris and
    belongs to March. PostgreSQL applies the zone rules (including DST).
    """
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1-12, got {month}")

    from sqlalchemy import text

    query = text("""
        SELECT COALESCE(SUM(r.total_amount), 0) AS total
        FROM reservations r
        JOIN properties p
          ON p.id = r.property_id AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id
          AND r.tenant_id = :tenant_id
          AND r.check_in_date >= (make_timestamp(:year, :month, 1, 0, 0, 0) AT TIME ZONE p.timezone)
          AND r.check_in_date <  ((make_timestamp(:year, :month, 1, 0, 0, 0) + INTERVAL '1 month') AT TIME ZONE p.timezone)
    """)
    params = {"property_id": property_id, "tenant_id": tenant_id, "month": month, "year": year}

    if db_session is not None:
        total = (await db_session.execute(query, params)).scalar_one()
    else:
        from app.core.database_pool import db_pool

        await db_pool.initialize()
        if not db_pool.session_factory:
            raise RuntimeError("Database pool not available")
        async with db_pool.get_session() as session:
            total = (await session.execute(query, params)).scalar_one()

    return to_cents(total)

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.

    Raises if the database is unavailable: callers must surface an error rather
    than show figures that did not come from the tenant's own reservations.
    """
    from sqlalchemy import text
    from app.core.database_pool import db_pool

    # Shared, process-wide pool (initialised once on first use).
    await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    async with db_pool.get_session() as session:
        query = text("""
            SELECT 
                property_id,
                SUM(total_amount) as total_revenue,
                COUNT(*) as reservation_count
            FROM reservations 
            WHERE property_id = :property_id AND tenant_id = :tenant_id
            GROUP BY property_id
        """)

        result = await session.execute(query, {
            "property_id": property_id, 
            "tenant_id": tenant_id
        })
        row = result.fetchone()

    if row:
        # SUM over NUMERIC(10,3) is exact; round to cents once, here.
        total_revenue = to_cents(row.total_revenue)
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(total_revenue),
            "currency": "USD", 
            "count": row.reservation_count
        }

    # No reservations found for this property
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": "0.00",
        "currency": "USD",
        "count": 0
    }
