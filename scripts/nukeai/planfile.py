"""Plan JSON : le contrat entre le script et le modèle.

Le modèle ne reçoit que du texte de commentaire et un extrait de code en lecture
seule ; il ne renvoie que du texte de commentaire. Toute réponse qui contient des
délimiteurs, dépasse le budget ou vise un fichier modifié entre-temps est rejetée
ou nettoyée avant application.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

from .document import Document
from .reducer import DOC_REASON, Options, budget, eligible
from .rewrite import DELETE, REPLACE, Edit

PLAN_VERSION = 1

INSTRUCTIONS = {
    "synthesize": (
        "Pour chaque item, écris dans new_text UNE seule ligne qui ne garde que "
        "l'information absente du code. Conserve la langue d'origine. "
        "new_text = [] supprime le commentaire, new_text = null le laisse tel quel."
    ),
    "humanize": (
        "Pour chaque item, réécris le commentaire comme un développeur pressé : "
        "minuscule initiale, pas de point final, pas de préambule, on explique le "
        "pourquoi et jamais le quoi. Conserve la langue d'origine. "
        "new_text = [] supprime le commentaire (à privilégier quand il n'apporte "
        "rien), new_text = null le laisse tel quel."
    ),
}

RULES = [
    "N'écris jamais de code dans new_text.",
    "N'inclus jamais de délimiteur de commentaire (// /* */ # <!-- --> \"\"\").",
    "Respecte max_lines et max_chars de chaque item.",
    "Ne modifie aucun autre champ du plan.",
]

DELIMS = re.compile(r"(/\*|\*/|<!--|-->|\"\"\"|'''|^\s*//|^\s*#\s|^\s*\*\s|^\s*--\s)")


def sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def build(docs: List[Document], mode: str, opts: Options, root: Path) -> Dict:
    items = []
    for doc in docs:
        rel = _rel(doc.path, root)
        fh = sha(doc.text)
        for c in doc.comments:
            if not eligible(c, opts):
                continue
            items.append({
                "id": f"{rel}#{c.id}",
                "file": rel,
                "file_sha1": fh,
                "lang": c.lang,
                "kind": c.kind,
                "is_api_doc": c.protected == DOC_REASON,
                "deletable": not c.protected and not c.sole_statement,
                "lines": f"{c.line}-{c.end_line}",
                "span": [c.start, c.end],
                "raw_sha1": sha(c.text),
                "ai_score": round(c.ai_score, 2),
                "ai_reasons": list(c.ai_reasons),
                "max_lines": 1 if mode == "synthesize" else max(1, len(c.inner_lines) // 2 or 1),
                "max_chars": budget(c, opts),
                "current": [l for l in c.inner_lines if l.strip()],
                "code_before": c.code_before,
                "code_after": c.code_after,
                "new_text": None,
            })
    return {
        "version": PLAN_VERSION,
        "mode": mode,
        "root": str(root),
        "_instructions": INSTRUCTIONS[mode],
        "_rules": RULES,
        "items": items,
    }


def _rel(path: Path, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(path)


def clean_text(value, max_lines: int, max_chars: int) -> Tuple[List[str], List[str]]:
    """Nettoie la réponse du modèle. Retourne (lignes, avertissements)."""
    warns = []
    if isinstance(value, str):
        value = [value]
    lines = []
    for raw in value:
        if not isinstance(raw, str):
            warns.append("valeur non textuelle ignorée")
            continue
        for part in raw.splitlines() or [raw]:
            s = part.strip()
            if DELIMS.search(s):
                s = DELIMS.sub("", s).strip()
                warns.append("délimiteur retiré")
            if s:
                lines.append(s)
    if len(lines) > max_lines:
        warns.append(f"tronqué à {max_lines} ligne(s)")
        lines = lines[:max_lines]
    out = []
    for s in lines:
        if len(s) > max_chars * 2:
            warns.append("ligne trop longue, coupée")
            s = s[: max_chars * 2].rsplit(" ", 1)[0]
        out.append(s)
    return out, warns


def load(plan_path: Path) -> Dict:
    data = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    if data.get("version") != PLAN_VERSION:
        raise ValueError(f"version de plan inattendue : {data.get('version')}")
    if not isinstance(data.get("items"), list):
        raise ValueError("plan sans liste 'items'")
    return data


def to_edits(plan: Dict, root: Path) -> Tuple[Dict[Path, List[Edit]], List[str]]:
    """Reconstruit les éditions à partir du plan rempli, fichier par fichier."""
    by_file: Dict[str, List[dict]] = {}
    for item in plan["items"]:
        by_file.setdefault(item["file"], []).append(item)

    edits: Dict[Path, List[Edit]] = {}
    warns: List[str] = []

    for rel, items in by_file.items():
        path = (Path(root) / rel).resolve()
        doc = Document.load(path)
        if doc is None:
            warns.append(f"{rel} : illisible, ignoré")
            continue
        if sha(doc.text) != items[0].get("file_sha1"):
            warns.append(f"{rel} : modifié depuis la création du plan, ignoré")
            continue

        index = {c.id: c for c in doc.comments}
        file_edits = []
        for item in items:
            value = item.get("new_text")
            if value is None:
                continue
            cid = item["id"].split("#")[-1]
            c = index.get(cid)
            if c is None or sha(c.text) != item["raw_sha1"]:
                warns.append(f"{rel} : commentaire {cid} introuvable, ignoré")
                continue
            if isinstance(value, list) and not value:
                if item.get("deletable"):
                    file_edits.append(Edit(c, DELETE, reason="modèle : à supprimer"))
                else:
                    warns.append(f"{rel}#{cid} : doc d'API, suppression refusée")
                continue
            lines, w = clean_text(value, item["max_lines"], item["max_chars"])
            warns.extend(f"{rel}#{cid} : {x}" for x in w)
            if not lines:
                continue
            if tuple(lines) == tuple(item["current"]):
                continue
            file_edits.append(Edit(c, REPLACE, tuple(lines), reason="modèle"))
        if file_edits:
            edits[path] = file_edits
    return edits, warns
