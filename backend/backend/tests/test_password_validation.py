"""
NeuroOncoTrack-AI — Password Validation Unit Tests (SUBTASK 003-A)

Tests for app.core.security.validate_password:
  - Strong password acceptance (12+ chars, uppercase, lowercase, number, special)
  - Rejection of weak/invalid passwords (short, missing classes, empty, None, whitespace)
  - Security check ensuring plaintext passwords are NEVER exposed in error messages
"""

from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.core.security import validate_password


# ── PASS TEST CASES ─────────────────────────────────────────

def test_valid_strong_password_accepted():
    """1. 12+ character strong password accepted."""
    # Should not raise any exception
    validate_password("ComplexPass123!")


def test_valid_password_with_all_character_classes_accepted():
    """2. Uppercase + lowercase + number + special character password accepted."""
    validate_password("A1b2C3d4#$5678")


# ── FAIL TEST CASES ─────────────────────────────────────────

def test_short_password_eleven_chars_rejected():
    """3. 11 character password rejected."""
    with pytest.raises(ValidationError) as exc_info:
        validate_password("Short12345!")
    assert "en az 12 karakter" in exc_info.value.detail


def test_missing_uppercase_rejected():
    """4. Password without uppercase rejected."""
    with pytest.raises(ValidationError) as exc_info:
        validate_password("lowercase123!")
    assert "büyük harf" in exc_info.value.detail


def test_missing_lowercase_rejected():
    """5. Password without lowercase rejected."""
    with pytest.raises(ValidationError) as exc_info:
        validate_password("UPPERCASE123!")
    assert "küçük harf" in exc_info.value.detail


def test_missing_number_rejected():
    """6. Password without number rejected."""
    with pytest.raises(ValidationError) as exc_info:
        validate_password("NoNumberPassword!")
    assert "rakam" in exc_info.value.detail


def test_missing_special_character_rejected():
    """7. Password without special character rejected."""
    with pytest.raises(ValidationError) as exc_info:
        validate_password("NoSpecialChar123")
    assert "özel karakter" in exc_info.value.detail


def test_empty_password_rejected():
    """8. Empty password rejected."""
    with pytest.raises(ValidationError) as exc_info:
        validate_password("")
    assert "boş bırakılamaz" in exc_info.value.detail


def test_none_password_rejected():
    """9. None rejected appropriately."""
    with pytest.raises(ValidationError) as exc_info:
        validate_password(None)  # type: ignore[arg-type]
    assert "boş bırakılamaz" in exc_info.value.detail


def test_whitespace_only_password_rejected():
    """10. Password consisting only of whitespace rejected."""
    with pytest.raises(ValidationError) as exc_info:
        validate_password("            ")
    assert "boşluklardan oluşamaz" in exc_info.value.detail


# ── SECURITY TEST ───────────────────────────────────────────

def test_password_validation_error_does_not_expose_password():
    """11. Password validation error response MUST NOT contain the password itself."""
    secret_test_input = "secretpass123!"  # Missing uppercase, invalid password
    with pytest.raises(ValidationError) as exc_info:
        validate_password(secret_test_input)

    error_message_str = str(exc_info.value)
    error_detail_str = str(exc_info.value.detail)

    assert secret_test_input not in error_message_str
    assert secret_test_input not in error_detail_str
