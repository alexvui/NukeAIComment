"""Application des éditions : suppression et remplacement par offset.

Aucune édition ne touche à autre chose qu'un span de commentaire déjà localisé
par le scanner. Le texte de remplacement est du texte nu : ce module est le seul
à produire les délimiteurs.
"""

import re
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from .languages import LangSpec
from .scanner import Comment

DELETE = "delete"
REPLACE = "replace"


@dataclass
class Edit:
    comment: Comment
    action: str
    lines: Tuple[str, ...] = ()
    reason: str = ""


def render(c: Comment, lines: Sequence[str]) -> str:
    """Reconstruit un commentaire à partir de texte nu."""
    indent = c.indent if c.own_line else ""

    if c.kind == "docstring":
        # l'indentation relative des lignes porte la structure, on la conserve
        kept = list(lines)
        while kept and not kept[-1].strip():
            kept.pop()
        if not kept:
            return ""
        q = c.open_tok or '"""'
        if len(kept) == 1:
            return f"{q}{kept[0].strip()}{q}"
        body = "\n".join((indent + l).rstrip() if l.strip() else "" for l in kept[1:])
        return f"{q}{kept[0].strip()}\n{body}\n{indent}{q}"

    lines = [l.strip() for l in lines if l.strip()]
    if not lines:
        return ""

    if c.kind == "line":
        tok = c.open_tok or "//"
        return ("\n" + indent).join(f"{tok} {l}" for l in lines)

    open_tok = c.open_tok or "/*"
    close_tok = c.close_tok or "*/"
    if len(lines) == 1:
        return f"{open_tok} {lines[0]} {close_tok}"
    if open_tok == "/**":
        body = "\n".join(f"{indent} * {l}" for l in lines)
        return f"/**\n{body}\n{indent} */"
    body = ("\n" + indent).join(lines)
    return f"{open_tok} {body} {close_tok}"


def _line_bounds(text: str, pos: int) -> Tuple[int, int]:
    start = text.rfind("\n", 0, pos) + 1
    nl = text.find("\n", pos)
    return start, (len(text) if nl == -1 else nl)


def _is_blank(text: str, line_start: int) -> bool:
    _, end = _line_bounds(text, line_start)
    return not text[line_start:end].strip()


def _delete_span(text: str, c: Comment) -> Tuple[int, int, bool]:
    """(début, fin, la suppression emporte-t-elle des lignes entières)"""
    line_start, _ = _line_bounds(text, c.start)
    _, last_end = _line_bounds(text, max(c.start, c.end - 1))
    tail = text[c.end:last_end]

    if c.jsx_wrapped or (c.own_line and not tail.strip()):
        # `{/* … */}` : les accolades n'existent que pour porter le commentaire
        return line_start, min(len(text), last_end + 1), True

    if c.trailing:
        start = c.start
        while start > line_start and text[start - 1] in " \t":
            start -= 1
        return start, c.end, False

    # commentaire en début de ligne suivi de code : on ne retire que le span
    end = c.end
    while end < len(text) and text[end] in " \t":
        end += 1
    return c.start, end, False


def _absorb_blank_line(text: str, groups: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Évite la double ligne vide laissée par un bloc de commentaires supprimé."""
    out = []
    for a, b in groups:
        prev_blank = a == 0 or _is_blank(text, text.rfind("\n", 0, a - 1) + 1)
        next_blank = b < len(text) and _is_blank(text, b)
        if prev_blank and next_blank:
            _, nend = _line_bounds(text, b)
            b = min(len(text), nend + 1)
        out.append((a, b))
    return out


def _merge_contiguous(spans: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    merged = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def apply_edits(text: str, edits: List[Edit]) -> str:
    line_deletes, other = [], []
    for e in edits:
        c = e.comment
        new = render(c, e.lines) if e.action == REPLACE else ""
        if e.action == DELETE or not new:
            a, b, whole = _delete_span(text, c)
            (line_deletes if whole else other).append((a, b, ""))
        else:
            other.append((c.start, c.end, new))

    groups = _absorb_blank_line(text, _merge_contiguous([(a, b) for a, b, _ in line_deletes]))
    spans = [(a, b, "") for a, b in groups] + other
    spans.sort(key=lambda s: s[0], reverse=True)

    out = text
    prev_start = len(text) + 1
    for a, b, repl in spans:
        if b > prev_start:
            continue  # spans qui se chevauchent : on garde le premier vu
        out = out[:a] + repl + out[b:]
        prev_start = a
    return out


def verify_code_unchanged(before: str, after: str, spec: LangSpec) -> Tuple[bool, str]:
    """Invariant central : le code hors commentaires doit être identique."""
    from .document import canonical

    a, b = canonical(before, spec), canonical(after, spec)
    if a == b:
        return True, ""
    return False, _first_difference(a, b)


def _first_difference(a: str, b: str) -> str:
    la, lb = a.splitlines(), b.splitlines()
    for n, (x, y) in enumerate(zip(la, lb), 1):
        if x != y:
            return f"ligne de code {n} : « {x.strip()[:70]} » devient « {y.strip()[:70]} »"
    if len(la) != len(lb):
        extra = la[len(lb):] or lb[len(la):]
        return f"{abs(len(la) - len(lb))} ligne(s) de code en écart : « {extra[0].strip()[:70]} »"
    return "différence non localisée"
