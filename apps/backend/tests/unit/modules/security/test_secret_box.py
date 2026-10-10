from src.modules.security.secret_box import EncryptedString, open_secret, seal_secret


def test_sealed_secret_round_trips_and_hides_the_plaintext():
    sealed = seal_secret("JBSWY3DPEHPK3PXP")
    assert "JBSWY3DPEHPK3PXP" not in sealed
    assert open_secret(sealed) == "JBSWY3DPEHPK3PXP"
    assert seal_secret("JBSWY3DPEHPK3PXP") != sealed


def test_column_type_encrypts_on_bind_and_decrypts_on_read():
    column = EncryptedString()
    stored = column.process_bind_param("ABC", None)  # type: ignore[arg-type]
    assert stored != "ABC"
    assert column.process_result_value(stored, None) == "ABC"  # type: ignore[arg-type]
    assert column.process_bind_param(None, None) is None  # type: ignore[arg-type]
