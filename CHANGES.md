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
