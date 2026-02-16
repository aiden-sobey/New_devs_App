from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, str]]:
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant context available")

    try:
        from app.core.database_pool import db_pool

        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                from sqlalchemy import text

                query = text("""
                    SELECT id, name FROM properties
                    WHERE tenant_id = :tenant_id
                    ORDER BY name
                """)
                result = await session.execute(query, {"tenant_id": tenant_id})
                rows = result.fetchall()
                return [{"id": row.id, "name": row.name} for row in rows]
        else:
            raise Exception("Database pool not available")
    except Exception as e:
        print(f"Database error fetching properties for tenant {tenant_id}: {e}")

        mock_properties = {
            'tenant-a': [
                {'id': 'prop-001', 'name': 'Beach House Alpha'},
            ],
            'tenant-b': [
                {'id': 'prop-001', 'name': 'Mountain Lodge Beta'},
            ],
        }
        return mock_properties.get(tenant_id, [])


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant context available")
    
    revenue_data = await get_revenue_summary(property_id, tenant_id)
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": revenue_data['total'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
