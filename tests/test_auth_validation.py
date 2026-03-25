from app import is_strong_password, is_valid_email


def test_is_valid_email_accepts_standard_address():
    assert is_valid_email("alice.smith+security@example.ie")


def test_is_valid_email_rejects_invalid_addresses():
    assert not is_valid_email("")
    assert not is_valid_email("alice.example.com")
    assert not is_valid_email("alice@")
    assert not is_valid_email("@example.com")


def test_is_strong_password_accepts_password_with_all_requirements():
    assert is_strong_password("SecurePass1!")


def test_is_strong_password_rejects_missing_requirements():
    assert not is_strong_password("short1!")  # too short
    assert not is_strong_password("alllowercase1!")  # missing uppercase
    assert not is_strong_password("ALLUPPERCASE1!")  # missing lowercase
    assert not is_strong_password("NoNumbers!")  # missing digit
    assert not is_strong_password("NoSpecial1")  # missing symbol
