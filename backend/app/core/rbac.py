"""
Role-based access control: one permission map instead of role strings checked
inline across routers. Endpoints declare the permission they need
(`Depends(require_permission(P.TICKETS_ASSIGN))`); per-object rules — e.g. a
customer may only see tickets they requested — live in the services that
load those objects.
"""

from enum import StrEnum


class Role(StrEnum):
    PLATFORM_ADMIN = "platform_admin"
    ORG_ADMIN = "org_admin"
    MANAGER = "manager"
    AGENT = "agent"
    CUSTOMER = "customer"
    ANALYST = "analyst"


# Roles that belong to an organization's support staff (see internal notes,
# work any ticket in the org).
STAFF_ROLES = frozenset({Role.ORG_ADMIN, Role.MANAGER, Role.AGENT})
# Roles that can read every ticket in the org (staff + read-only analysts).
ORG_WIDE_READ_ROLES = STAFF_ROLES | {Role.ANALYST}
# Roles a ticket can be assigned to.
ASSIGNABLE_ROLES = frozenset({Role.ORG_ADMIN, Role.MANAGER, Role.AGENT})
# Roles an org admin may grant (platform_admin is never grantable in-app).
GRANTABLE_ROLES = frozenset({Role.ORG_ADMIN, Role.MANAGER, Role.AGENT, Role.CUSTOMER, Role.ANALYST})


class P(StrEnum):
    ORG_READ = "org:read"
    ORG_UPDATE = "org:update"
    USERS_READ = "users:read"
    USERS_MANAGE = "users:manage"
    USERS_INVITE = "users:invite"
    TEAMS_READ = "teams:read"
    TEAMS_MANAGE = "teams:manage"
    CATEGORIES_MANAGE = "categories:manage"
    SLA_MANAGE = "sla:manage"
    TICKETS_CREATE = "tickets:create"
    TICKETS_READ_ALL = "tickets:read_all"
    TICKETS_WORK = "tickets:work"
    TICKETS_ASSIGN = "tickets:assign"
    TICKETS_CLOSE_ANY = "tickets:close_any"
    COMMENTS_INTERNAL = "comments:internal"
    AUDIT_READ = "audit:read"
    ANALYTICS_READ = "analytics:read"
    # Knowledge base: requesters read published articles only (enforced in app/kb).
    KB_READ = "kb:read"
    KB_MANAGE = "kb:manage"
    PLATFORM_ADMIN = "platform:admin"


_CUSTOMER = {P.ORG_READ, P.TICKETS_CREATE, P.KB_READ}
_ANALYST = {P.ORG_READ, P.USERS_READ, P.TEAMS_READ, P.TICKETS_READ_ALL, P.AUDIT_READ, P.ANALYTICS_READ, P.KB_READ}
_AGENT = {
    P.ORG_READ,
    P.USERS_READ,
    P.TEAMS_READ,
    P.TICKETS_CREATE,
    P.TICKETS_READ_ALL,
    P.TICKETS_WORK,
    P.COMMENTS_INTERNAL,
    P.KB_READ,
}
_MANAGER = _AGENT | {
    P.TICKETS_ASSIGN,
    P.TICKETS_CLOSE_ANY,
    P.USERS_INVITE,
    P.AUDIT_READ,
    P.ANALYTICS_READ,
    P.KB_MANAGE,
}
_ORG_ADMIN = _MANAGER | {
    P.ORG_UPDATE,
    P.USERS_MANAGE,
    P.TEAMS_MANAGE,
    P.CATEGORIES_MANAGE,
    P.SLA_MANAGE,
}

ROLE_PERMISSIONS: dict[Role, frozenset[P]] = {
    Role.PLATFORM_ADMIN: frozenset({P.PLATFORM_ADMIN}),
    Role.ORG_ADMIN: frozenset(_ORG_ADMIN),
    Role.MANAGER: frozenset(_MANAGER),
    Role.AGENT: frozenset(_AGENT),
    Role.CUSTOMER: frozenset(_CUSTOMER),
    Role.ANALYST: frozenset(_ANALYST),
}


def permissions_for(role: str) -> frozenset[P]:
    try:
        return ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return frozenset()


def has_permission(role: str, permission: P) -> bool:
    return permission in permissions_for(role)


def is_staff(role: str) -> bool:
    return role in STAFF_ROLES


def can_read_all_tickets(role: str) -> bool:
    return role in ORG_WIDE_READ_ROLES
