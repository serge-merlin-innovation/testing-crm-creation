from sqlalchemy import inspect

from src.modules.user.models import User
from src.modules.user.schemas import User as UserSchema
from src.modules.user.schemas import UserRead


def _make_user() -> User:
    return User(
        name="Test User",
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
    )


def test_is_active_true_when_not_deleted():
    user = _make_user()
    assert user.is_deleted is False
    assert user.is_active is True


def test_is_active_false_when_soft_deleted():
    user = _make_user()
    user.is_deleted = True
    assert user.is_active is False


def test_role_name_is_a_mapped_expression_not_a_column():
    assert "role_name" not in [column.key for column in User.__table__.columns]
    assert "role_name" in [prop.key for prop in inspect(User).mapper.column_attrs]


def test_role_name_is_read_on_user_read_only():
    assert "role_name" in UserRead.model_fields
    assert "role_name" not in UserSchema.model_fields
