"""Provision a private signing key for container startup without logging it."""
import os
from pathlib import Path
import secrets

PLACEHOLDERS = {"dev-only-change-me", "replace-with-a-long-random-secret", "change-me"}


def valid_key(value):
    return isinstance(value, str) and len(value) >= 50 and value not in PLACEHOLDERS


def get_runtime_secret(environment=None, key_path=None):
    environment = os.environ if environment is None else environment
    for name in ("DJANGO_SECRET_KEY", "SECRET_KEY"):
        value = environment.get(name, "").strip()
        if valid_key(value):
            return value
    path = Path(key_path or environment.get("DJANGO_SECRET_KEY_FILE", ".cache/django-secret.key"))
    if path.is_file():
        value = path.read_text(encoding="utf8").strip()
        if valid_key(value):
            return value
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(48)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf8") as target:
        target.write(value)
    temporary.replace(path)
    return value


if __name__ == "__main__":
    print(get_runtime_secret())
