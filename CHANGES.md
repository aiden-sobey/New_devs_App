# Improvements

## Property Revenue Dashboard

### 1. Cross-tenant cache key collision

**File:** `backend/app/services/cache.py`

**Customer Impact:** Tenants could see revenue data belonging to other tenants. When two tenants queried the dashboard for the same `property_id`, the first response was cached and served to both, leaking financial data across tenant boundaries.

**Technical Issue:** The Redis cache key was `revenue:{property_id}`, which is only unique per property — not per tenant. In a multi-tenant system where property IDs can overlap or where tenants share a Redis instance, a cache hit for tenant A's request could be returned to tenant B.

**Remediation:** The cache key now includes the tenant ID: `revenue:{tenant_id}:{property_id}`. The `get_revenue_summary()` function accepts `tenant_id` as a required parameter and threads it through to both the cache lookup and the downstream `calculate_total_revenue()` call, ensuring tenant isolation at the cache layer.

---

### 2. Timezone-naive month boundaries

**File:** `backend/app/services/reservations.py`

**Customer Impact:** Properties reported incorrect monthly revenue totals. Reservations near month boundaries (e.g. a check-in at 11 PM local on January 31st) could be attributed to the wrong month, causing discrepancies in monthly reports.

**Technical Issue:** Month-start and month-end boundaries were computed as naive UTC datetimes (`datetime(year, month, 1)`). Because reservation timestamps are stored in UTC but represent events in the property's local timezone, the query window was misaligned for any property not in UTC. For example, a property in `US/Eastern` (UTC-5) had its January window start five hours too early.

**Remediation:** Added a `get_property_timezone()` helper that looks up the property's configured timezone from the `properties` table (falling back to `"UTC"` if unset). `calculate_monthly_revenue()` now localizes month boundaries to the property's timezone using `pytz`, then converts them to UTC before querying. This ensures the query window precisely covers the local calendar month regardless of the property's timezone.

---

### 3. Float precision loss

**File:** `backend/app/api/v1/dashboard.py`

**Customer Impact:** Revenue totals displayed on the dashboard could differ from the actual database values by small amounts (e.g. `$4975.50` appearing as `$4975.4999999999...`), undermining trust in financial reporting and causing reconciliation mismatches.

**Technical Issue:** The dashboard endpoint wrapped the revenue total in `float()` before returning it in the JSON response. Converting a `Decimal` to a Python `float` introduces IEEE 754 floating-point representation errors, which are especially problematic for monetary values that must be exact.

**Remediation:** Removed the `float()` conversion. The service layer now returns revenue totals as `Decimal` values serialized to strings (e.g. `"4975.50"`), and the dashboard endpoint passes these string values through directly in the `total_revenue` field. This preserves exact decimal precision end-to-end from the database to the API consumer.

---

### 4. Dashboard endpoint falls back to "default_tenant"

**File:** `backend/app/api/v1/dashboard.py`

**Customer Impact:** If authentication failed to resolve a tenant for any reason, the user silently received empty data scoped to a non-existent `"default_tenant"` instead of a clear error. This made debugging authentication and tenant-resolution issues much harder and could mask data-access problems.

**Technical Issue:** The dashboard summary endpoint used `getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"` to extract the tenant ID. This double-fallback swallowed missing tenant context entirely, routing the query to a tenant that doesn't exist in the database, which always returns zero results with no indication of failure.

**Remediation:** Replaced the fallback with a direct attribute access (`current_user.tenant_id`) followed by an explicit `403 Forbidden` error if the tenant ID is missing or empty. This surfaces tenant-resolution failures immediately rather than hiding them behind empty responses.

---

### 5. Frontend hardcodes all properties for all tenants

**Files:** `frontend/src/components/Dashboard.tsx`, `backend/app/api/v1/dashboard.py`, `frontend/src/lib/secureApi.ts`

**Customer Impact:** Every user saw the same five-property dropdown regardless of which tenant they belonged to. Client A saw Client B's properties (Lakeside Cottage, Urban Loft Modern) and vice versa. Property `prop-001` was always displayed as "Beach House Alpha" even for Client B, where it should be "Mountain Lodge Beta". This broke tenant isolation at the UI level and confused users.

**Technical Issue:** The `Dashboard.tsx` component contained a static `PROPERTIES` array with all five properties from both tenants hardcoded. There was no backend endpoint to return tenant-scoped properties for the dashboard, so the frontend had no way to know which properties belonged to the authenticated user's tenant.

**Remediation:** Removed the hardcoded `PROPERTIES` array from the frontend. Added a new `GET /api/v1/dashboard/properties` backend endpoint that queries properties filtered by the authenticated user's `tenant_id` (with a tenant-aware mock fallback matching the existing pattern). Added a `getDashboardProperties()` method to the `SecureAPIClient`. The `Dashboard` component now fetches properties via `useEffect` on mount and populates the dropdown from the API response, ensuring each tenant sees only their own properties with correct names.

---

### 6. Frontend rejects valid non-UUID tenant IDs

**File:** `frontend/src/lib/secureApi.ts`

**Customer Impact:** The frontend's client-side cache and request deduplication were completely bypassed for all users. Every API request logged a security warning about an invalid tenant ID, request deduplication didn't work (causing duplicate concurrent requests), and GET responses were never cached, degrading performance across the application.

**Technical Issue:** The `isValidTenantId()` method only accepted UUID format (`/^[0-9a-f]{8}-...-[0-9a-f]{12}$/`), but the actual tenant IDs in the system are slug-format strings like `tenant-a` and `tenant-b`. This caused `getTenantId()` to always return `null`, which disabled cache-key generation, bypassed deduplication, and triggered security warning logs on every request.

**Remediation:** Updated `isValidTenantId()` to accept both UUID format and slug format (`/^[a-z0-9][a-z0-9_-]{0,62}$/i`). The slug regex allows alphanumeric strings with hyphens and underscores up to 63 characters, which covers the current tenant ID scheme while still rejecting empty or malformed values.
