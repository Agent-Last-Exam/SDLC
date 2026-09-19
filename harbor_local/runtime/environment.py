"""Literal local environment configuration, without shell evaluation."""
import re
import shlex


def load_env(path, environment):
    """Read literal KEY=VALUE entries without executing or expanding shell text."""
    if not path.exists():
        return
    for index, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key):
            raise ValueError(f"Invalid env entry on line {index} in {path}")
        words = shlex.split(value, comments=True)
        if len(words) > 1:
            raise ValueError(f"Quote values containing spaces on line {index} in {path}")
        value = words[0] if words else ""
        # Nonempty file values win; blank template entries preserve exported env.
        if value:
            environment[key] = value

