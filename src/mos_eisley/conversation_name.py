"""Canonical, bounded user-authored session labels."""

import argparse
import unicodedata
from typing import Annotated

from pydantic import AfterValidator, Field


class SessionSelectionError(ValueError):
    """Fixed, safe guidance for name or picker selection failures."""


def validate_name(value: str) -> str:
    if (
        not value
        or len(value) > 120
        or not all(char.isprintable() for char in value)
        or value != unicodedata.normalize("NFC", value).strip()
    ):
        raise ValueError(
            "Session names require 1–120 printable characters without outer spaces."
        )
    return value


SessionName = Annotated[
    str, Field(strict=True, min_length=1, max_length=120), AfterValidator(validate_name)
]


def parse_name(value: str) -> str:
    try:
        if not value.isprintable():
            raise ValueError("Session names must be printable.")
        return validate_name(unicodedata.normalize("NFC", value).strip())
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Session names require 1–120 printable characters on one line."
        ) from None


def name_key(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip().casefold())
