from sqlalchemy import inspect

from src.modules.user.models import User
from src.modules.user.schemas import User as UserSchema
from src.modules.user.schemas import UserRead


def test_is_active_tracks_soft_deletion():
    user = User(name="Test User", email="test@example.com", hashed_password="hashed")
    assert user.is_active is True
    user.is_deleted = True
    assert user.is_active is False


def test_there_is_no_username_superuser_or_entra_column():
    columns = {column.key for column in User.__table__.columns}
    assert not columns & {"username", "is_superuser", "microsoft_id", "oauth_provider"}


def test_role_name_and_permissions_are_mapped_expressions_not_columns():
    columns = [column.key for column in User.__table__.columns]
    attributes = [prop.key for prop in inspect(User).mapper.column_attrs]
    for name in ("role_name", "permissions"):
        assert name not in columns
        assert name in attributes
        assert name in UserRead.model_fields
        assert name not in UserSchema.model_fields
