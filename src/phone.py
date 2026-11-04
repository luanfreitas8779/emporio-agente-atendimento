COUNTRY_CODE = "55"


def normalize_phone(phone: str) -> str | None:
    """Returns the area code and number as digits only, or None if it is not a Brazilian phone number."""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) in (12, 13) and digits.startswith(COUNTRY_CODE):
        digits = digits[len(COUNTRY_CODE) :]
    return digits if len(digits) in (10, 11) else None


def format_phone(phone: str) -> str:
    """"(67) 99654-7821" from any typed form, or empty if it is not a phone number."""
    digits = normalize_phone(phone)
    return f"({digits[:2]}) {digits[2:-4]}-{digits[-4:]}" if digits else ""
