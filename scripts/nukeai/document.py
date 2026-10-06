"""Un fichier chargé, scanné et annoté."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .languages import LangSpec, spec_for
from .regions import regions
from .scanner import Comment, annotate, scan_region, strip_comments, _python_docstrings


@dataclass
class Document:
    path: Path
    text: str
    spec: LangSpec
    comments: List[Comment] = field(default_factory=list)

    @classmethod
    def load(cls, path) -> Optional["Document"]:
        p = Path(path)
        spec = spec_for(p)
        if spec is None:
            return None
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return None
        return cls.from_text(text, p, spec)

    @classmethod
    def from_text(cls, text, path, spec=None) -> "Document":
        spec = spec or spec_for(path)
        doc = cls(Path(path), text, spec)
        doc.comments = scan_text(text, spec, str(path))
        return doc

    def code_only(self) -> str:
        return strip_comments(self.text, self.comments)


def scan_text(text: str, spec: LangSpec, path: str = "") -> List[Comment]:
    out: List[Comment] = []
    for a, b, sub in regions(text, spec):
        scan_region(text, sub, a, b, out)
        if sub.py_docstrings:
            out = _python_docstrings(text, sub, out)
    out.sort(key=lambda c: c.start)
    return annotate(text, out, path)


_EMPTY_BRACES = re.compile(r"\{\s*\}")


def canonical(text: str, spec: LangSpec) -> str:
    """Forme canonique du code, commentaires retirés.

    Invariant de sécurité : cette valeur doit être identique avant et après
    transformation. Elle tolère les changements d'espaces en fin de ligne et de
    lignes vides — les seuls effets de bord légitimes d'une suppression de
    commentaire — mais rien d'autre.
    """
    stripped = strip_comments(text, scan_text(text, spec))
    if spec.jsx:
        stripped = _EMPTY_BRACES.sub("", stripped)
    return "\n".join(
        line.rstrip() for line in stripped.splitlines() if line.strip()
    )
