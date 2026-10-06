"""Découpage des fichiers multi-syntaxe.

Sans ça, `<a href="https://x">` dans un .html serait lu comme un commentaire `//`,
et un `<style>` d'un .vue serait scanné avec les règles de JavaScript.
"""

import re
from typing import List, Tuple

from . import languages as L
from .languages import LangSpec

Region = Tuple[int, int, LangSpec]

_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.S | re.I)
_STYLE = re.compile(r"<style\b([^>]*)>(.*?)</style\s*>", re.S | re.I)
_PHP_OPEN = re.compile(r"<\?(?:php\b|=)?", re.I)
_PHP_CLOSE = re.compile(r"\?>")


def regions(text: str, spec: LangSpec) -> List[Region]:
    """Découpe le texte en zones homogènes. Une seule zone pour un fichier normal."""
    if spec.name == "php":
        return _php_regions(text)
    if spec.name in ("html", "vue", "svelte"):
        return _markup_regions(text)
    return [(0, len(text), spec)]


def _markup_regions(text):
    marked = []
    for rx, lang in ((_SCRIPT, None), (_STYLE, L.CSS)):
        for m in rx.finditer(text):
            attrs = m.group(1) or ""
            sub = lang or _script_lang(attrs)
            if sub is None:
                continue
            marked.append((m.start(2), m.end(2), sub))
    marked.sort()
    return _fill_gaps(marked, len(text), L.HTML)


def _script_lang(attrs):
    typ = re.search(r'type\s*=\s*["\']?([^"\'\s>]+)', attrs, re.I)
    if typ and not re.search(r"(javascript|module|ts|jsx?|babel)", typ.group(1), re.I):
        return None  # <script type="application/json"> et compagnie
    return L.TS if re.search(r'lang\s*=\s*["\']?ts', attrs, re.I) else L.JS


def _php_regions(text):
    marked = []
    pos = 0
    while True:
        m = _PHP_OPEN.search(text, pos)
        if not m:
            break
        close = _PHP_CLOSE.search(text, m.end())
        end = close.start() if close else len(text)
        marked.append((m.end(), end, L.PHP))
        pos = close.end() if close else len(text)
    return _fill_gaps(marked, len(text), L.HTML)


def _fill_gaps(marked, total, outer):
    out = []
    prev = 0
    for a, b, sub in marked:
        if a > prev:
            out.append((prev, a, outer))
        out.append((a, b, sub))
        prev = b
    if prev < total:
        out.append((prev, total, outer))
    return out or [(0, total, outer)]
