"""Decide how to answer a question.

Deliberately rule-based: it's free, instant, predictable and testable.
An LLM classifier would handle odd phrasings better; that's a listed
"next step", not a day-one need.
"""

import re

ROUTES = ("endpoints", "dependencies", "overview", "code")

_ENDPOINTS = re.compile(r"\b(endpoints?|routes?|api(s)?\b.*\b(list|expose|available)|http|rest)\b", re.I)
_DEPENDENCIES = re.compile(r"\b(dependenc(y|ies)|packages?|libraries|library|requirements|third[- ]party)\b", re.I)
_OVERVIEW = re.compile(
    r"\b(overview|what does (this|the) (repo|project|codebase|app)|summar(y|ize)|architecture|structure|tech stack)\b",
    re.I,
)


def route(question: str) -> str:
    if _ENDPOINTS.search(question):
        return "endpoints"
    if _DEPENDENCIES.search(question):
        return "dependencies"
    if _OVERVIEW.search(question):
        return "overview"
    return "code"
