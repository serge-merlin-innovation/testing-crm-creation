from fastapi import APIRouter

from ....infrastructure.auth.routes import router as auth_router
from ....infrastructure.config.settings import EnvironmentOption, settings
from ....infrastructure.testing import router as testing_router
from ....modules.account.routes import auth_router as account_auth_router
from ....modules.account.routes import policy_router as password_policy_router
from ....modules.account.routes import users_router as account_users_router
from ....modules.activity.routes import notes_router, timeline_router
from ....modules.activity.routes import router as activities_router
from ....modules.api_access.routes import clients_router as api_clients_router
from ....modules.api_access.routes import oauth_router
from ....modules.api_access.routes import tokens_router as api_tokens_router
from ....modules.audit.routes import router as audit_router
from ....modules.calendar_feed.routes import router as calendar_feed_router
from ....modules.company.routes import router as companies_router
from ....modules.compliance.routes import reviews_router as conflict_reviews_router
from ....modules.compliance.routes import router as compliance_router
from ....modules.contact.routes import router as contacts_router
from ....modules.data_export.routes import router as data_export_router
from ....modules.data_import.routes import router as imports_router
from ....modules.email_logging.routes import interactions_router
from ....modules.email_logging.routes import router as email_logging_router
from ....modules.mandate.routes import criteria_router
from ....modules.mandate.routes import router as mandates_router
from ....modules.merge.routes import router as merges_router
from ....modules.notification.routes import router as notifications_router
from ....modules.offboarding.routes import router as offboarding_router
from ....modules.picklist.routes import router as picklists_router
from ....modules.privacy.routes import router as privacy_router
from ....modules.role.routes import router as roles_router
from ....modules.search.routes import filters_router as saved_filters_router
from ....modules.search.routes import router as search_router
from ....modules.security.routes import router as security_router
from ....modules.session.routes import router as session_router
from ....modules.task.routes import router as tasks_router
from ....modules.user.routes import router as users_router

router = APIRouter(prefix="/v1")
router.include_router(account_users_router, prefix="/users")
router.include_router(users_router, prefix="/users")
router.include_router(offboarding_router, prefix="/users")
router.include_router(roles_router, prefix="/roles")
router.include_router(audit_router, prefix="/audit")
router.include_router(companies_router, prefix="/companies")
router.include_router(contacts_router, prefix="/contacts")
router.include_router(picklists_router, prefix="/picklists")
router.include_router(mandates_router, prefix="/mandates")
router.include_router(compliance_router, prefix="/mandates")
router.include_router(conflict_reviews_router, prefix="/conflict-reviews")
router.include_router(criteria_router, prefix="/stage-criteria")
router.include_router(notifications_router, prefix="/notifications")
router.include_router(activities_router, prefix="/activities")
router.include_router(notes_router, prefix="/notes")
router.include_router(timeline_router, prefix="/timeline")
router.include_router(tasks_router, prefix="/tasks")
router.include_router(search_router, prefix="/search")
router.include_router(saved_filters_router, prefix="/saved-filters")
router.include_router(merges_router, prefix="/merges")
router.include_router(imports_router, prefix="/imports")
router.include_router(email_logging_router, prefix="/email-logging")
router.include_router(interactions_router, prefix="/contacts")
router.include_router(calendar_feed_router, prefix="/calendar-feed")
router.include_router(auth_router, prefix="/auth")
router.include_router(account_auth_router, prefix="/auth")
router.include_router(security_router)
router.include_router(privacy_router)
router.include_router(data_export_router)
router.include_router(session_router)
router.include_router(password_policy_router)
router.include_router(api_tokens_router, prefix="/api-tokens")
router.include_router(api_clients_router, prefix="/api-clients")
router.include_router(oauth_router, prefix="/oauth")

if settings.ENVIRONMENT not in (EnvironmentOption.PRODUCTION, EnvironmentOption.STAGING):
    router.include_router(testing_router, prefix="/test-hooks")
