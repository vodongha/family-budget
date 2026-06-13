"""Phone-number validation and normalisation.

Numbers are stored canonically in E.164 (``+<country><number>``). The client
sends a number with its country code already chosen, so we parse with no default
region and require the result to be a valid number.
"""

import phonenumbers


class PhoneValidationError(Exception):
    """Raised when a supplied phone number is not a valid, parseable number."""


def normalize_phone(raw: str) -> str:
    """Return the E.164 form of ``raw`` or raise [PhoneValidationError]."""
    try:
        parsed = phonenumbers.parse(raw.strip(), None)
    except phonenumbers.NumberParseException:
        raise PhoneValidationError(raw) from None
    if not phonenumbers.is_valid_number(parsed):
        raise PhoneValidationError(raw)
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def try_normalize_phone(raw: str | None) -> str | None:
    """Best-effort normalisation: ``None`` for blank or unparseable input.

    Used when matching an invitation's phone label against existing accounts —
    a label that isn't a valid number simply doesn't match anyone.
    """
    if raw is None or not raw.strip():
        return None
    try:
        return normalize_phone(raw)
    except PhoneValidationError:
        return None
