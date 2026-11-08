"""Code-aware tokenizer for keyword (BM25) search.

``getUserById`` and ``get_user_by_id`` should both match a question that
says "get user by id", so identifiers are split into their parts while the
full identifier is kept too (for exact-name questions).
"""

import re

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")

STOPWORDS = {
    "the", "a", "an", "is", "are", "of", "to", "in", "and", "or", "for", "on", "it",
    "how", "what", "where", "which", "does", "do", "this", "that", "with", "be", "by",
    "self", "return", "def", "class", "import", "from", "as", "if", "else", "none",
    "true", "false", "i", "me", "my", "we", "code", "there", "can", "you",
}


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for ident in _IDENT.findall(text):
        lower = ident.lower()
        parts = [p.lower() for piece in ident.split("_") for p in _CAMEL.findall(piece)]
        if len(parts) > 1 and lower not in STOPWORDS:
            tokens.append(lower)  # keep the full identifier
        tokens.extend(p for p in parts if p not in STOPWORDS and len(p) > 1)
    return tokens
