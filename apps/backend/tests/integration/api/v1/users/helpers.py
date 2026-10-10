import random
from datetime import UTC, datetime


def generate_unique_user_data(prefix: str = "user") -> dict:
    timestamp = int(datetime.now(UTC).timestamp())
    random_suffix = random.randint(1000, 9999)

    return {
        "username": f"{prefix}_user_{timestamp}_{random_suffix}",
        "email": f"{prefix}_{timestamp}_{random_suffix}@example.com",
        "oauth_provider": "microsoft",
        "oauth_id": f"oauth_{timestamp}_{random_suffix}",
        "first_name": f"First{random_suffix}",
        "last_name": f"Last{random_suffix}",
        "is_active": True,
        "is_superuser": False,
    }


def generate_superuser_data(prefix: str = "admin") -> dict:
    data = generate_unique_user_data(prefix)
    data.update({"is_superuser": True, "username": f"admin_{data['username']}"})
    return data


def generate_oauth_user_data(provider: str = "microsoft", prefix: str = "oauth") -> dict:
    data = generate_unique_user_data(prefix)
    data.update({"oauth_provider": provider, "oauth_id": f"{provider}_{int(datetime.now(UTC).timestamp())}"})
    return data


def generate_bulk_users(count: int, prefix: str = "bulk") -> list[dict]:
    return [generate_unique_user_data(f"{prefix}_{i}") for i in range(count)]


def generate_test_user_update_data() -> dict:
    timestamp = int(datetime.now(UTC).timestamp())

    return {
        "first_name": f"UpdatedFirst{timestamp}",
        "last_name": f"UpdatedLast{timestamp}",
        "username": f"updated_user_{timestamp}",
    }
