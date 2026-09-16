from secrets import token_urlsafe


def new_id(prefix: str) -> str:
    return f"{prefix}_{token_urlsafe(16)}"
