"""Sortie console : diff unifié, tableau de synthèse, couleurs."""

import difflib
import os
import sys
from typing import List, Tuple

_ENABLED = True


def setup_color(force_off: bool = False) -> None:
    global _ENABLED
    _ENABLED = (
        not force_off
        and sys.stdout.isatty()
        and os.environ.get("NO_COLOR") is None
        and os.environ.get("TERM") != "dumb"
    )


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _ENABLED else text


def dim(t): return c(t, "2")
def bold(t): return c(t, "1")
def red(t): return c(t, "31")
def green(t): return c(t, "32")
def yellow(t): return c(t, "33")
def blue(t): return c(t, "36")


def diff(before: str, after: str, label: str, context: int = 2) -> str:
    lines = list(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=label, tofile=label, n=context,
    ))
    out = []
    for line in lines:
        line = line.rstrip("\n")
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("@@"):
            out.append(blue(line))
        elif line.startswith("-"):
            out.append(red(line))
        elif line.startswith("+"):
            out.append(green(line))
        else:
            out.append(dim(line))
    return "\n".join(out)


def header(label: str) -> str:
    return bold(f"\n── {label} " + "─" * max(0, 68 - len(label)))


def summary_table(rows: List[Tuple[str, int, int, int]]) -> str:
    """rows : (fichier, supprimés, raccourcis, protégés)"""
    if not rows:
        return ""
    width = min(52, max(len(r[0]) for r in rows) + 2)
    out = [dim(f"{'fichier'.ljust(width)}{'supprimés':>11}{'raccourcis':>12}{'protégés':>11}")]
    for name, d, s, p in rows:
        short = name if len(name) <= width - 2 else "…" + name[-(width - 3):]
        out.append(short.ljust(width)
                   + red(str(d).rjust(11))
                   + yellow(str(s).rjust(12))
                   + dim(str(p).rjust(11)))
    return "\n".join(out)


def lines_saved(before: str, after: str) -> int:
    return len(before.splitlines()) - len(after.splitlines())
