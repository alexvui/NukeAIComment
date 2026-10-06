"""Résolution des fichiers à traiter."""

import os
import subprocess
from pathlib import Path
from typing import List, Optional

from .languages import spec_for

EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "bower_components", "vendor",
    "dist", "build", "out", "target", ".next", ".nuxt", ".svelte-kit",
    "__pycache__", ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "coverage", ".coverage", "htmlcov", ".idea", ".vscode",
    ".nukeaicomment-backup", ".gradle", "Pods", "DerivedData", ".terraform",
}
EXCLUDE_SUFFIXES = (".min.js", ".min.css", ".bundle.js", ".map", ".lock",
                    ".generated.ts", "_pb2.py", ".pb.go", ".g.dart")
MAX_BYTES = 1_000_000


def git_root(start: Path) -> Optional[Path]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(out.stdout.strip()) if out.returncode == 0 else None


def _git(root: Path, *args) -> List[str]:
    out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        return []
    return [l for l in out.stdout.splitlines() if l.strip()]


def changed_files(root: Path, base: Optional[str] = None) -> List[Path]:
    if base:
        names = _git(root, "diff", "--name-only", "--diff-filter=ACMR", base)
    else:
        names = []
        for line in _git(root, "status", "--porcelain=v1", "-uall"):
            name = line[3:].strip()
            if " -> " in name:
                name = name.split(" -> ", 1)[1]
            names.append(name.strip('"'))
    return [root / n for n in names]


def all_files(root: Path) -> List[Path]:
    tracked = _git(root, "ls-files", "--cached", "--others", "--exclude-standard")
    if tracked:
        return [root / n for n in tracked]
    return walk(root)


def walk(base: Path) -> List[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for f in filenames:
            out.append(Path(dirpath) / f)
    return out


def keep(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    if any(part in EXCLUDE_DIRS for part in path.parts):
        return False
    if path.name.endswith(EXCLUDE_SUFFIXES):
        return False
    if spec_for(path) is None:
        return False
    try:
        if path.stat().st_size > MAX_BYTES:
            return False
    except OSError:
        return False
    return True


def resolve(paths, scope_all=False, base=None, cwd=None):
    """Retourne (fichiers, description de la cible, avertissements)."""
    cwd = Path(cwd or Path.cwd()).resolve()
    root = git_root(cwd)
    notes = []

    if paths:
        found = []
        for p in paths:
            p = Path(p)
            if not p.is_absolute():
                p = cwd / p
            if p.is_dir():
                found.extend(walk(p))
            elif p.exists():
                found.append(p)
            else:
                notes.append(f"chemin introuvable : {p}")
        label = ", ".join(str(p) for p in paths)
    elif scope_all:
        found = all_files(root or cwd)
        label = f"tout le projet ({root or cwd})"
    elif root:
        found = changed_files(root, base)
        label = f"fichiers modifiés selon git{f' depuis {base}' if base else ''}"
        if not found:
            notes.append("aucun fichier modifié — utilisez --all ou donnez un chemin")
    else:
        found = []
        notes.append("hors dépôt git : indiquez un chemin explicite ou --all")
        label = "aucune"

    files, skipped = [], 0
    seen = set()
    for f in found:
        f = f.resolve()
        if f in seen:
            continue
        seen.add(f)
        if keep(f):
            files.append(f)
        elif f.is_file():
            skipped += 1
    if skipped:
        notes.append(f"{skipped} fichier(s) ignoré(s) : langage non géré, généré ou trop gros")
    return sorted(files), label, notes
