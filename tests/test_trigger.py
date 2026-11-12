# type: ignore
import pytest

from kisan.services.verification.trigger import parse


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b'[1]',
        b"null",
        b'"x"',
        b"not json",
    ],
)

def test_parse_reject_invalid_payloads(raw:bytes)-> None:
    with pytest.raises(ValueError):
        parse(raw)
