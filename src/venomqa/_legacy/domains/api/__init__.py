"""API testing domain journeys.

Provides journey templates for:
- Generic CRUD operations
- Rate limiting behavior
- API version compatibility
"""

from venomqa.domains.api.journeys.crud import (
    crud_bulk_flow,
    crud_create_flow,
    crud_delete_flow,
    crud_read_flow,
    crud_update_flow,
)
from venomqa.domains.api.journeys.rate_limit import (
    rate_limit_burst_flow,
    rate_limit_headers_flow,
    rate_limit_sustained_flow,
)
from venomqa.domains.api.journeys.versioning import (
    api_v1_flow,
    api_v2_flow,
    api_version_transition_flow,
)

__all__ = [
    "crud_create_flow",
    "crud_read_flow",
    "crud_update_flow",
    "crud_delete_flow",
    "crud_bulk_flow",
    "rate_limit_burst_flow",
    "rate_limit_sustained_flow",
    "rate_limit_headers_flow",
    "api_v1_flow",
    "api_v2_flow",
    "api_version_transition_flow",
]

api_crud_create_flow = crud_create_flow
api_crud_read_flow = crud_read_flow
api_crud_update_flow = crud_update_flow
api_crud_delete_flow = crud_delete_flow
api_crud_bulk_flow = crud_bulk_flow
api_rate_limit_burst_flow = rate_limit_burst_flow
api_rate_limit_sustained_flow = rate_limit_sustained_flow
api_rate_limit_headers_flow = rate_limit_headers_flow
