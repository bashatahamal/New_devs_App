from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.services.reservations import to_cents
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        # Never fall back to a shared/default tenant for financial data.
        raise HTTPException(status_code=403, detail="No tenant is associated with this account")

    revenue_data = await get_revenue_summary(property_id, tenant_id)
    
    # Keep money in Decimal and round to cents before it becomes a JSON number,
    # so clients never have to round binary floats (e.g. 4975.525 -> 4975.52).
    total_revenue = to_cents(revenue_data['total'])

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": float(total_revenue),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
