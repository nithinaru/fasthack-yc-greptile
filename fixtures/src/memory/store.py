"""Long-term memory for Caveman agents (see README §Memory)."""

_MEMORY: dict[str, str] = {}


def remember(key: str, value: str) -> None:
    # TODO: make this persistent
    _MEMORY[key] = value


def recall(key: str) -> str | None:
    return _MEMORY.get(key)
