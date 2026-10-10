from datetime import UTC, datetime

from src.modules.security.totp import totp_code, verify_totp

# RFC 6238 appendix B, SHA-1 seed "12345678901234567890", 8 digits truncated to the last 6.
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


def test_matches_rfc_6238_vectors():
    assert totp_code(RFC_SECRET, datetime.fromtimestamp(59, UTC)) == "287082"
    assert totp_code(RFC_SECRET, datetime.fromtimestamp(1111111109, UTC)) == "081804"
    assert totp_code(RFC_SECRET, datetime.fromtimestamp(2000000000, UTC)) == "279037"


def test_accepts_one_step_of_clock_drift_but_not_two():
    at = datetime.fromtimestamp(1111111109, UTC)
    assert verify_totp(RFC_SECRET, "081804", datetime.fromtimestamp(1111111109 + 30, UTC))
    assert not verify_totp(RFC_SECRET, "081804", datetime.fromtimestamp(1111111109 + 90, UTC))
    assert not verify_totp(RFC_SECRET, "000000", at)
