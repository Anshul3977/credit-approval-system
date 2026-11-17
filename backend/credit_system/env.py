"""Environment helpers that do not read Django settings."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

INSECURE_DEV_SECRET = "dev-only-not-for-production"
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def load_dotenv(path: Path) -> None:
    """Load KEY=value lines into the environment without overriding existing vars."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            os.environ.setdefault(key, value)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default


def env_csv(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def on_render() -> bool:
    return os.environ.get("RENDER", "").strip().lower() == "true"


def resolve_secret_key(secret: str, *, running_on_render: bool) -> str:
    """Return a Django secret key, refusing the dev placeholder on Render."""
    value = (secret or "").strip()
    if running_on_render and (not value or value == INSECURE_DEV_SECRET):
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set to a unique value on Render."
        )
    return value or INSECURE_DEV_SECRET
