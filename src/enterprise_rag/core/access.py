"""Access-control primitives for retrieval-time authorization."""

from __future__ import annotations

from enterprise_rag.core.models import Chunk, Classification, Principal


_CLEARANCE_RANK = {
    Classification.PUBLIC: 0,
    Classification.INTERNAL: 1,
    Classification.CONFIDENTIAL: 2,
    Classification.RESTRICTED: 3,
}


class AccessPolicy:
    """Tenant, group, and classification checks applied before ranking."""

    def can_read(self, principal: Principal, chunk: Chunk) -> bool:
        if principal.tenant_id != chunk.tenant_id:
            return False
        if _CLEARANCE_RANK[principal.clearance] < _CLEARANCE_RANK[chunk.classification]:
            return False
        if chunk.allowed_groups and principal.groups.isdisjoint(chunk.allowed_groups):
            return False
        return True
