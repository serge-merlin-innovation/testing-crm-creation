from fastapi import APIRouter

from ....infrastructure.auth.routes import router as auth_router
from ....infrastructure.config.settings import EnvironmentOption, settings
from ....infrastructure.testing import router as testing_router
from ....modules.api_access.routes import clients_router as api_clients_router
from ....modules.api_access.routes import oauth_router
from ....modules.api_access.routes import tokens_router as api_tokens_router
from ....modules.audit.routes import router as audit_router
from ....modules.company.routes import router as companies_router
from ....modules.contact.routes import router as contacts_router
from ....modules.mandate.routes import router as mandates_router
from ....modules.notification.routes import router as notifications_router
from ....modules.picklist.routes import router as picklists_router
from ....modules.role.routes import router as roles_router
from ....modules.security.routes import router as security_router
from ....modules.user.routes import router as users_router

router = APIRouter(prefix="/v1")
router.include_router(users_router, prefix="/users")
router.include_router(roles_router, prefix="/roles")
router.include_router(audit_router, prefix="/audit")
router.include_router(companies_router, prefix="/companies")
router.include_router(contacts_router, prefix="/contacts")
router.include_router(picklists_router, prefix="/picklists")
router.include_router(mandates_router, prefix="/mandates")
router.include_router(notifications_router, prefix="/notifications")
router.include_router(auth_router, prefix="/auth")
router.include_router(security_router)
router.include_router(api_tokens_router, prefix="/api-tokens")
router.include_router(api_clients_router, prefix="/api-clients")
router.include_router(oauth_router, prefix="/oauth")

if settings.ENVIRONMENT not in (EnvironmentOption.PRODUCTION, EnvironmentOption.STAGING):
    router.include_router(testing_router, prefix="/test-hooks")
