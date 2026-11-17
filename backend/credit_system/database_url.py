"""Parse a postgres:// DATABASE_URL into Django's DATABASES entry."""

from urllib.parse import parse_qs, unquote, urlparse


class DatabaseURLError(ValueError):
    """DATABASE_URL is missing a scheme or database name Django can use."""


def database_config_from_url(url: str) -> dict:
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").split("+", 1)[0]
    if scheme not in {"postgres", "postgresql"}:
        raise DatabaseURLError(
            "DATABASE_URL must start with postgres:// or postgresql://"
        )
    name = unquote((parsed.path or "").lstrip("/"))
    if not name:
        raise DatabaseURLError("DATABASE_URL is missing a database name")
    query = parse_qs(parsed.query)
    options = {}
    if "sslmode" in query and query["sslmode"]:
        options["sslmode"] = query["sslmode"][-1]
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or 5432),
        "OPTIONS": options,
    }
