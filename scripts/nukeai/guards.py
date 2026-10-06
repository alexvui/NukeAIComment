"""Garde-fous : état git, sauvegarde, restauration, vérification syntaxique."""

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .targets import git_root

BACKUP_HOME = Path.home() / ".nukeaicomment" / "backups"


def dirty_files(root: Path) -> List[str]:
    out = subprocess.run(["git", "status", "--porcelain=v1", "-uno"],
                         cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        return []
    return [l[3:].strip() for l in out.stdout.splitlines() if l.strip()]


def check_workspace(cwd: Path, force: bool) -> Tuple[bool, str]:
    """Refuse d'écrire sur un dépôt sale : sans ça, pas de `git checkout` de secours."""
    root = git_root(cwd)
    if root is None:
        return True, "hors dépôt git — la sauvegarde locale est le seul filet"
    dirty = dirty_files(root)
    if not dirty:
        return True, ""
    if force:
        return True, f"{len(dirty)} fichier(s) non commités, --force accepté"
    listing = "\n".join(f"    {f}" for f in dirty[:10])
    more = f"\n    … et {len(dirty) - 10} autres" if len(dirty) > 10 else ""
    return False, (
        f"Le dépôt a {len(dirty)} modification(s) non commitée(s) :\n{listing}{more}\n"
        "  Commitez, mettez de côté (git stash), ou relancez avec --force."
    )


def _project_slot(root: Path) -> Path:
    digest = hashlib.sha1(str(root).encode()).hexdigest()[:8]
    return BACKUP_HOME / f"{root.name}-{digest}"


class Backup:
    def __init__(self, root: Path):
        self.root = root
        self.slot = _project_slot(root)
        self.dir = self.slot / datetime.now().strftime("%Y%m%d-%H%M%S")
        self.entries: Dict[str, str] = {}

    def save(self, path: Path) -> None:
        rel = _rel(path, self.root)
        dest = self.dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        self.entries[str(rel)] = str(path)

    def finalize(self) -> Optional[Path]:
        if not self.entries:
            return None
        (self.dir / "manifest.json").write_text(
            json.dumps({"root": str(self.root), "files": self.entries}, indent=2),
            encoding="utf-8",
        )
        return self.dir

    def rollback(self, only: Optional[List[Path]] = None) -> int:
        wanted = {str(Path(p).resolve()) for p in only} if only is not None else None
        n = 0
        for rel, original in self.entries.items():
            if wanted is not None and str(Path(original).resolve()) not in wanted:
                continue
            src = self.dir / rel
            if src.exists():
                shutil.copy2(src, original)
                n += 1
        return n


def _rel(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return Path(str(path.resolve()).lstrip("/"))


def list_backups(root: Path) -> List[Path]:
    slot = _project_slot(root)
    if not slot.exists():
        return []
    return sorted((d for d in slot.iterdir() if (d / "manifest.json").exists()),
                  reverse=True)


def restore(root: Path, which: Optional[str] = None) -> Tuple[int, Optional[Path]]:
    backups = list_backups(root)
    if not backups:
        return 0, None
    target = backups[0]
    if which:
        match = [b for b in backups if b.name == which]
        if not match:
            return 0, None
        target = match[0]
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    n = 0
    for rel, original in manifest["files"].items():
        src = target / rel
        if src.exists():
            Path(original).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, original)
            n += 1
    return n, target


# --------------------------------------------------------------------------- #
# Vérification syntaxique native, quand l'outil est présent
# --------------------------------------------------------------------------- #

_PY_PARSE = "import ast,sys; ast.parse(open(sys.argv[1], encoding='utf-8').read())"

CHECKERS = {
    ".py": lambda p: [sys.executable, "-c", _PY_PARSE, str(p)],
    ".js": lambda p: ["node", "--check", str(p)],
    ".cjs": lambda p: ["node", "--check", str(p)],
    ".mjs": lambda p: ["node", "--check", str(p)],
    ".php": lambda p: ["php", "-l", str(p)],
    ".rb": lambda p: ["ruby", "-c", str(p)],
    ".sh": lambda p: ["bash", "-n", str(p)],
    ".bash": lambda p: ["bash", "-n", str(p)],
    ".go": lambda p: ["gofmt", "-e", str(p)],
    ".lua": lambda p: ["luac", "-p", str(p)],
    ".rs": lambda p: ["rustc", "--edition", "2021", "--emit", "metadata",
                      "-o", "/dev/null", str(p)],
}
# rustc compile vraiment le module : trop lourd et trop faux-positif hors crate
CHECKERS.pop(".rs")


def syntax_check(path: Path) -> Tuple[Optional[bool], str]:
    """(None, '') si aucun vérificateur n'est disponible pour ce fichier."""
    builder = CHECKERS.get(path.suffix.lower())
    if builder is None:
        return None, ""
    cmd = builder(path)
    if shutil.which(cmd[0]) is None and cmd[0] != sys.executable:
        return None, ""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    if out.returncode == 0:
        return True, ""
    said = [l.strip() for l in (out.stderr or out.stdout).splitlines() if l.strip()]
    return False, (said[-1] if said else "erreur de syntaxe")[:160]
