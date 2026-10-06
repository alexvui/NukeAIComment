"""Transformations déterministes : `nuke` et `reduce`.

Aucun appel de modèle. Ce qui ne peut pas être raccourci de façon sûre est laissé
intact plutôt que mutilé.
"""

import re
from dataclasses import dataclass
from typing import List, Sequence

from .classify import (JSDOC_PARAM_RE, JSDOC_RETURN_RE, Protections, _jsdoc_echo,
                       restates_code)
from .document import Document
from .rewrite import DELETE, REPLACE, Edit
from .scanner import Comment

DOC_REASON = "documentation d'API"


@dataclass
class Options:
    max_len: int = 80
    shrink_docs: bool = False
    min_ai_score: float = 0.0
    dedupe: bool = True


PREFIXES = [re.compile(p, re.I) for p in (
    r"^this\s+(?:function|method|class|component|hook|module|file|script|block)\s+"
    r"(?:is\s+)?(?:used\s+to\s+|responsible\s+for\s+|that\s+|which\s+|will\s+)?",
    r"^(?:a|the)\s+(?:helper|utility|simple|small)?\s*(?:function|method|class)\s+"
    r"(?:that|to|which)\s+",
    r"^(?:helper|utility)\s+(?:function|method)\s+(?:that|to)\s+",
    r"^(?:function|method)\s+(?:that|to)\s+",
    r"^(?:cette|ce|cet)\s+(?:fonction|méthode|classe|composant|module|fichier)\s+"
    r"(?:sert\s+à\s+|permet\s+de\s+|qui\s+|qu[ie]\s+va\s+)?",
    r"^(?:basically|essentially|simply|just)\s*,?\s*",
    r"^(?:first|next|then|finally|now)\s*,\s*",
    r"^(?:d'abord|ensuite|puis|enfin)\s*,\s*",
    r"^step\s+\d+\s*[:.\-]\s*",
    r"^(?:we|here we|this will|it will)\s+",
    r"^(?:on|nous)\s+(?:va|allons)\s+",
)]

DROP_SENTENCES = [re.compile(p, re.I) for p in (
    r"^note that\b", r"^notez que\b",
    r"^(?:this|it)\s+is\s+(?:important|worth noting|done|used)\b",
    r"^il\s+(?:est|convient)\b",
    r"^in other words\b", r"^autrement dit\b",
    r"^for example\b", r"^par exemple\b",
    r"^(?:this|the)\s+(?:function|method|class|component|module|hook)\b",
    r"^(?:cette|ce)\s+(?:fonction|méthode|classe|composant|module)\b",
    r"^make sure\b", r"^assurez-vous\b",
    r"^see (?:above|below)\b",
)]

BANNER_ONLY = re.compile(r"^[\s=*\-~_#/+<>|]+$")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def eligible(c: Comment, opts: Options) -> bool:
    if c.protected and not (opts.shrink_docs and c.protected == DOC_REASON):
        return False
    return c.ai_score >= opts.min_ai_score


def can_delete(c: Comment, opts: Options) -> bool:
    """Une doc d'API autorisée au raccourcissement n'est jamais supprimée, et une
    docstring qui tient lieu de corps de bloc laisserait un bloc vide."""
    return not c.protected and not c.sole_statement


def plan_nuke(doc: Document, opts: Options) -> List[Edit]:
    edits = []
    for c in doc.comments:
        if eligible(c, opts) and can_delete(c, opts):
            edits.append(Edit(c, DELETE, reason="nuke"))
    return edits


def banner_group(doc: Document) -> set:
    """Un titre encadré de lignes décoratives part avec son encadrement."""
    ids, run = set(), []

    def flush():
        if len(run) >= 2 and any(is_banner(c) for c in run):
            ids.update(c.id for c in run)
        run.clear()

    prev_end = None
    for c in doc.comments:
        contiguous = prev_end is not None and c.line == prev_end + 1
        if c.own_line and c.kind == "line" and not c.protected:
            if not contiguous:
                flush()
            run.append(c)
        else:
            flush()
        prev_end = c.end_line
    flush()
    return ids


def is_banner(c: Comment) -> bool:
    lines = [l for l in c.inner_lines if l.strip()]
    return bool(lines) and all(BANNER_ONLY.match(l) for l in lines)


def plan_reduce(doc: Document, opts: Options) -> List[Edit]:
    edits = []
    seen = {}
    banners = banner_group(doc)
    for c in doc.comments:
        if not eligible(c, opts):
            continue

        if can_delete(c, opts):
            if c.id in banners:
                edits.append(Edit(c, DELETE, reason="bloc décoratif"))
                continue
            if not c.inner.strip() or is_banner(c):
                edits.append(Edit(c, DELETE, reason="bannière ou commentaire vide"))
                continue
            if restates_code(c) >= 0.7:
                edits.append(Edit(c, DELETE, reason="reformule la ligne voisine"))
                continue
            if opts.dedupe:
                key = c.inner.lower()
                prev = seen.get(key)
                if prev is not None and c.line - prev <= 3:
                    edits.append(Edit(c, DELETE, reason="doublon"))
                    continue
                seen[key] = c.end_line

        lines = shorten(c, opts)
        if not lines:
            if can_delete(c, opts):
                edits.append(Edit(c, DELETE, reason="plus rien à dire"))
            continue
        if _trim(lines) != _trim(c.inner_lines):
            edits.append(Edit(c, REPLACE, tuple(lines), reason="raccourci"))
    return edits


def _trim(lines: Sequence[str]) -> tuple:
    out = [l.rstrip() for l in lines]
    while out and not out[-1].strip():
        out.pop()
    while out and not out[0].strip():
        out.pop(0)
    return tuple(out)


PY_SECTION = re.compile(
    r"^\s*(Args|Arguments|Parameters|Returns|Yields|Raises|Attributes|Examples?|"
    r"Notes?|Warnings?|See Also|Paramètres|Retourne|Renvoie|Exemples?)\s*:", re.I)


def shorten(c: Comment, opts: Options) -> List[str]:
    if c.kind == "docstring":
        return shorten_docstring(c, opts)
    if c.doc:
        return shorten_doc(c, opts)
    return [t for t in [fit(clean_prose(c.inner), budget(c, opts))] if t]


def shorten_docstring(c: Comment, opts: Options) -> List[str]:
    """Garde le résumé et les sections structurées ; jette la prose intermédiaire."""
    lines = list(c.inner_lines)
    head = []
    i = 0
    while i < len(lines) and lines[i].strip():
        head.append(lines[i].strip())
        i += 1
    summary = fit(clean_prose(" ".join(head)), budget(c, opts))

    start = next((j for j in range(i, len(lines)) if PY_SECTION.match(lines[j])), None)
    if start is None:
        return [summary] if summary else []

    body = lines[start:]
    while body and not body[-1].strip():
        body.pop()
    return ([summary] if summary else []) + [""] + body


def shorten_doc(c: Comment, opts: Options) -> List[str]:
    desc, tags = [], []
    for line in c.inner_lines:
        s = line.strip()
        if not s:
            continue
        (tags if s.startswith("@") else desc).append(s)

    summary = fit(clean_prose(" ".join(desc)), budget(c, opts))
    kept = [truncate(t, budget(c, opts)) for t in tags if _tag_carries_info(t)]
    return ([summary] if summary else []) + kept


TYPE_NOISE = {
    "array", "list", "string", "number", "boolean", "object", "value", "values",
    "param", "parameter", "argument", "optional", "given", "provided", "instance",
    "tableau", "liste", "chaîne", "chaine", "nombre", "objet", "valeur", "facultatif",
}


def _tag_carries_info(tag: str) -> bool:
    m = JSDOC_PARAM_RE.search(tag)
    if m:
        desc = re.sub(r"\b(" + "|".join(TYPE_NOISE) + r")\b", "", m.group(2), flags=re.I)
        fake = Comment(0, 0, "block", inner_lines=(f"@param {m.group(1)} - {desc}",),
                       inner=tag)
        return _jsdoc_echo(fake) == 0
    m = JSDOC_RETURN_RE.search(tag)
    if m:
        return len(m.group(1).split()) > 3
    return True


def clean_prose(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    for _ in range(3):
        for rx in PREFIXES:
            new = rx.sub("", text, count=1).lstrip()
            if new and new != text:
                text = new
                break
        else:
            break

    sentences = [s for s in SENTENCE_SPLIT.split(text) if s.strip()]
    kept = [s for s in sentences if not any(rx.search(s) for rx in DROP_SENTENCES)]
    if not kept:
        kept = sentences[:1]
    return " ".join(kept).strip()


def budget(c: Comment, opts: Options) -> int:
    overhead = len(c.indent) + len(c.open_tok or "//") + 1
    if c.kind == "block":
        overhead += len(c.close_tok or "*/") + 1
    return max(24, opts.max_len - overhead)


def fit(text: str, limit: int) -> str:
    """Garde le maximum de phrases entières qui tiennent dans la limite."""
    text = text.strip()
    if len(text) <= limit:
        return text
    out = ""
    for s in SENTENCE_SPLIT.split(text):
        candidate = f"{out} {s}".strip()
        if out and len(candidate) > limit:
            break
        out = candidate
    return truncate(out or text, limit)


def truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit + 1]
    space = cut.rfind(" ")
    out = (cut[:space] if space > limit // 2 else text[:limit]).rstrip(" ,;:-")
    return out
