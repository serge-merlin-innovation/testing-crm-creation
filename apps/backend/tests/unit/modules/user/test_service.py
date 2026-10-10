from unittest.mock import AsyncMock, patch

import pytest

from src.modules.common.exceptions import PermissionDeniedError, UserNotFoundError
from src.modules.user import service as user_service_module
from src.modules.user.service import UserService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def user_service() -> UserService:
    return UserService()


async def test_update_superuser_status_promotes_another_user(user_service: UserService):
    with (
        patch.object(user_service_module.crud_users, "get", new=AsyncMock(return_value={"id": 2})),
        patch.object(
            user_service_module.crud_users, "update", new=AsyncMock(return_value={"id": 2, "is_superuser": True})
        ) as mock_update,
    ):
        result = await user_service.update_superuser_status(2, True, db=AsyncMock())

    assert result == {"id": 2, "is_superuser": True}
    mock_update.assert_awaited_once()


async def test_update_superuser_status_user_not_found(user_service: UserService):
    with patch.object(user_service_module.crud_users, "get", new=AsyncMock(return_value=None)):
        with pytest.raises(UserNotFoundError):
            await user_service.update_superuser_status(2, True, db=AsyncMock())


async def test_update_superuser_status_blocks_last_superuser_demotion(user_service: UserService):
    with (
        patch.object(user_service_module.crud_users, "get", new=AsyncMock(return_value={"id": 1, "is_superuser": True})),
        patch.object(user_service_module.crud_users, "count", new=AsyncMock(return_value=1)),
    ):
        with pytest.raises(PermissionDeniedError):
            await user_service.update_superuser_status(1, False, db=AsyncMock())


async def test_update_superuser_status_allows_demotion_when_another_superuser_remains(user_service: UserService):
    with (
        patch.object(user_service_module.crud_users, "get", new=AsyncMock(return_value={"id": 1, "is_superuser": True})),
        patch.object(user_service_module.crud_users, "count", new=AsyncMock(return_value=2)),
        patch.object(user_service_module.crud_users, "update", new=AsyncMock(return_value={"id": 1, "is_superuser": False})),
    ):
        result = await user_service.update_superuser_status(1, False, db=AsyncMock())

    assert result == {"id": 1, "is_superuser": False}


async def test_update_superuser_status_promotion_noop_skips_count_check(user_service: UserService):
    with (
        patch.object(user_service_module.crud_users, "get", new=AsyncMock(return_value={"id": 1, "is_superuser": True})),
        patch.object(user_service_module.crud_users, "count", new=AsyncMock()) as mock_count,
        patch.object(user_service_module.crud_users, "update", new=AsyncMock(return_value={"id": 1, "is_superuser": True})),
    ):
        result = await user_service.update_superuser_status(1, True, db=AsyncMock())

    assert result == {"id": 1, "is_superuser": True}
    mock_count.assert_not_awaited()


async def test_delete_blocks_last_superuser(user_service: UserService):
    with (
        patch.object(user_service_module.crud_users, "get", new=AsyncMock(return_value={"id": 1, "is_superuser": True})),
        patch.object(user_service_module.crud_users, "count", new=AsyncMock(return_value=1)),
    ):
        with pytest.raises(PermissionDeniedError):
            await user_service.delete(1, db=AsyncMock())


async def test_delete_allows_superuser_when_another_remains(user_service: UserService):
    with (
        patch.object(user_service_module.crud_users, "get", new=AsyncMock(return_value={"id": 1, "is_superuser": True})),
        patch.object(user_service_module.crud_users, "count", new=AsyncMock(return_value=2)),
        patch.object(user_service_module.crud_users, "delete", new=AsyncMock()) as mock_delete,
    ):
        await user_service.delete(1, db=AsyncMock())

    mock_delete.assert_awaited_once()


async def test_delete_regular_user_skips_count_check(user_service: UserService):
    with (
        patch.object(user_service_module.crud_users, "get", new=AsyncMock(return_value={"id": 1, "is_superuser": False})),
        patch.object(user_service_module.crud_users, "count", new=AsyncMock()) as mock_count,
        patch.object(user_service_module.crud_users, "delete", new=AsyncMock()),
    ):
        await user_service.delete(1, db=AsyncMock())

    mock_count.assert_not_awaited()


async def test_delete_user_not_found(user_service: UserService):
    with patch.object(user_service_module.crud_users, "get", new=AsyncMock(return_value=None)):
        with pytest.raises(UserNotFoundError):
            await user_service.delete(1, db=AsyncMock())


async def test_anonymize_user_blocks_last_superuser(user_service: UserService):
    with (
        patch.object(user_service_module.crud_users, "get", new=AsyncMock(return_value={"id": 1, "is_superuser": True})),
        patch.object(user_service_module.crud_users, "count", new=AsyncMock(return_value=1)),
    ):
        with pytest.raises(PermissionDeniedError):
            await user_service.anonymize_user(1, db=AsyncMock())


async def test_anonymize_user_allows_superuser_when_another_remains(user_service: UserService):
    with (
        patch.object(user_service_module.crud_users, "get", new=AsyncMock(return_value={"id": 1, "is_superuser": True})),
        patch.object(user_service_module.crud_users, "count", new=AsyncMock(return_value=2)),
        patch.object(user_service_module.crud_users, "update", new=AsyncMock()),
        patch.object(user_service_module.crud_users, "delete", new=AsyncMock()) as mock_delete,
    ):
        await user_service.anonymize_user(1, db=AsyncMock())

    mock_delete.assert_awaited_once()


async def test_count_active_superusers_queries_active_non_deleted_only(user_service: UserService):
    db = AsyncMock()
    with patch.object(user_service_module.crud_users, "count", new=AsyncMock(return_value=3)) as mock_count:
        result = await user_service.count_active_superusers(db=db)

    assert result == 3
    mock_count.assert_awaited_once_with(db=db, is_superuser=True, is_deleted=False)
