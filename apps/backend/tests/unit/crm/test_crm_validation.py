import pytest
from pydantic import ValidationError

from src.modules.company.enterprise_number import format_enterprise_number, normalize_enterprise_number
from src.modules.company.service import normalize_name
from src.modules.contact.schemas import ContactCreate


@pytest.mark.parametrize("raw", ["BE0403.170.701", "0403170701", "BE 0403 170 701", "403.170.701"])
def test_valid_enterprise_numbers_normalize_to_ten_digits(raw):
    assert normalize_enterprise_number(raw) == "0403170701"
    assert format_enterprise_number("0403170701") == "BE0403.170.701"


@pytest.mark.parametrize("raw", ["BE0403.170.702", "BE2403.170.701", "12345", "BEabc"])
def test_checksum_failures_are_rejected(raw):
    assert normalize_enterprise_number(raw) is None


def test_legal_form_and_accents_do_not_hide_a_similar_name():
    assert normalize_name("Société Générale SA") == normalize_name("societe generale")


def test_phone_is_stored_in_e164_and_garbage_is_rejected():
    contact = ContactCreate(first_name="A", last_name="B", phone="02 511 35 00", source="x")
    assert contact.phone == "+3225113500"
    with pytest.raises(ValidationError):
        ContactCreate(first_name="A", last_name="B", phone="12", source="x")
