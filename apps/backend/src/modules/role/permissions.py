from enum import StrEnum


class Permission(StrEnum):
    USERS_MANAGE = "users.manage"
    ROLES_MANAGE = "roles.manage"
    SETTINGS_MANAGE = "settings.manage"
    AUDIT_READ = "audit.read"
    MANDATES_CREATE = "mandates.create"
    CONFLICTS_APPROVE = "conflicts.approve"
    CONFLICTS_REGISTER = "conflicts.register"
    DEALS_READ_STAFFED = "deals.read_staffed"
    DEALS_EDIT_STAFFED = "deals.edit_staffed"
    DEALS_READ_SUMMARY = "deals.read_summary"
    DEAL_TEAM_ASSIGN = "deal_team.assign"
    BUYERS_MANAGE = "buyers.manage"
    # Field visibility (AUTHZ-06): without fees.read no fee, retainer, success-fee or invoice field
    # reaches the caller through any route, export or filter.
    FEES_READ = "fees.read"
    FEES_EDIT_OWN_DEALS = "fees.edit_own_deals"
    FEES_EDIT = "fees.edit"
    INVOICES_MANAGE = "invoices.manage"
    KYC_MANAGE = "kyc.manage"
    DASHBOARD_FIRM = "dashboard.firm"
    DASHBOARD_AGGREGATED = "dashboard.aggregated"
    PRIVACY_MANAGE = "privacy.manage"
    EXPORTS_APPROVE = "exports.approve"


class RoleName(StrEnum):
    ADMIN = "Admin"
    PARTNER = "Partner"
    DIRECTOR = "Director / Manager"
    ANALYST = "Analyst / Associate"
    COMPLIANCE = "Compliance / Back-office"
    READ_ONLY = "Read-only"


ALL_PERMISSIONS: tuple[str, ...] = tuple(permission.value for permission in Permission)

# The role table of docs/specs/ma-crm.md. Seeding only fills a role that does not exist yet, so an
# admin's later edits to a seeded role survive every restart.
DEFAULT_ROLES: dict[RoleName, tuple[str, frozenset[Permission]]] = {
    RoleName.ADMIN: (
        "IT / ops configuration",
        frozenset({Permission.USERS_MANAGE, Permission.ROLES_MANAGE, Permission.SETTINGS_MANAGE, Permission.AUDIT_READ}),
    ),
    RoleName.PARTNER: (
        "Owns relationships and mandates",
        frozenset(
            {
                Permission.MANDATES_CREATE,
                Permission.CONFLICTS_APPROVE,
                Permission.FEES_READ,
                Permission.FEES_EDIT_OWN_DEALS,
                Permission.DASHBOARD_FIRM,
                Permission.DASHBOARD_AGGREGATED,
                Permission.DEALS_READ_STAFFED,
                Permission.DEALS_EDIT_STAFFED,
                Permission.EXPORTS_APPROVE,
            }
        ),
    ),
    RoleName.DIRECTOR: (
        "Runs deal execution",
        frozenset(
            {
                Permission.DEALS_READ_STAFFED,
                Permission.DEALS_EDIT_STAFFED,
                Permission.DEAL_TEAM_ASSIGN,
                Permission.BUYERS_MANAGE,
            }
        ),
    ),
    RoleName.ANALYST: (
        "Executes work",
        frozenset({Permission.DEALS_READ_STAFFED, Permission.DEALS_EDIT_STAFFED}),
    ),
    RoleName.COMPLIANCE: (
        "KYC, conflicts, invoicing",
        frozenset(
            {
                Permission.CONFLICTS_REGISTER,
                Permission.KYC_MANAGE,
                Permission.FEES_READ,
                Permission.FEES_EDIT,
                Permission.INVOICES_MANAGE,
                Permission.DEALS_READ_SUMMARY,
                Permission.AUDIT_READ,
                Permission.PRIVACY_MANAGE,
            }
        ),
    ),
    RoleName.READ_ONLY: (
        "Oversight",
        frozenset({Permission.DASHBOARD_AGGREGATED}),
    ),
}
