import re

EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def is_valid_email(email):
    if not email:
        return False
    return bool(EMAIL_PATTERN.fullmatch(email.strip().lower()))


def is_strong_password(password):
    """Require 8+ chars with lower, upper, digit, and special character."""
    if not password or len(password) < 8:
        return False

    has_lower = any(ch.islower() for ch in password)
    has_upper = any(ch.isupper() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    has_special = any(not ch.isalnum() for ch in password)
    return has_lower and has_upper and has_digit and has_special
