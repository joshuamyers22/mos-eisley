"""Plain terminal labels without session or picker dependencies."""

import json


def safe_label(value: str) -> str:
    return "".join(
        char if char.isprintable() else json.dumps(char)[1:-1] for char in value
    )
