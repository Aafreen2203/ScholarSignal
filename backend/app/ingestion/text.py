import hashlib


def embedding_text(title: str | None, abstract: str | None) -> str | None:
    parts = [part.strip() for part in (title, abstract) if isinstance(part, str) and part.strip()]
    return "\n".join(parts) or None


def embedding_text_hash(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()
