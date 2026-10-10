from fastapi import APIRouter

from ....infrastructure.auth.routes import router as auth_router
from ....modules.role.routes import router as roles_router
from ....modules.user.routes import router as users_router

router = APIRouter(prefix="/v1")
router.include_router(users_router, prefix="/users")
router.include_router(roles_router, prefix="/roles")
router.include_router(auth_router, prefix="/auth")
