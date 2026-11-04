import pytest

from src.phone import format_phone


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("67996547821", "(67) 99654-7821"),
        ("(67) 99654-7821", "(67) 99654-7821"),
        ("+55 67 99654-7821", "(67) 99654-7821"),
        ("6733414444", "(67) 3341-4444"),
        ("123", ""),
        ("", ""),
    ],
)
def test_formats_the_phone_from_any_typed_form(typed, expected):
    assert format_phone(typed) == expected
