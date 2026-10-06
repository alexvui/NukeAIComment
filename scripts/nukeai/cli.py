"""Interface en ligne de commande."""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from . import __version__, planfile, report
from .classify import Protections, classify
from .document import Document
from .guards import Backup, check_workspace, list_backups, restore, syntax_check
from .reducer import DOC_REASON, Options, plan_nuke, plan_reduce
from .rewrite import DELETE, apply_edits, verify_code_unchanged
from .targets import git_root, resolve

MODES = ("scan", "nuke", "reduce", "synthesize", "humanize")


def disp(path) -> str:
    """Chemin lisible : relatif au répertoire courant quand c'est possible."""
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nukeaicomment",
        description="Réduit, synthétise, supprime ou humanise les commentaires "
                    "générés par IA — sans jamais toucher au code.",
    )
    p.add_argument("--version", action="version", version=f"nukeaicomment {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp, apply_flag=True):
        sp.add_argument("paths", nargs="*", help="fichiers ou dossiers (défaut : git diff)")
        sp.add_argument("--all", action="store_true", dest="scope_all",
                        help="tout le projet au lieu des fichiers modifiés")
        sp.add_argument("--diff-base", metavar="REF",
                        help="fichiers modifiés depuis cette référence git")
        sp.add_argument("--min-ai-score", type=float, default=0.0, metavar="N",
                        help="ne traiter que les commentaires au-dessus de ce score (0-1)")
        sp.add_argument("--include-docstrings", action="store_true",
                        help="autoriser la suppression des docstrings et JSDoc")
        sp.add_argument("--shrink-docs", action="store_true",
                        help="raccourcir les docs d'API sans jamais les supprimer")
        sp.add_argument("--no-keep-todo", action="store_true",
                        help="ne plus protéger TODO/FIXME/HACK/…")
        sp.add_argument("--include-headers", action="store_true",
                        help="ne plus protéger les en-têtes licence/copyright")
        sp.add_argument("--include-directives", action="store_true",
                        help="ne plus protéger eslint-disable, @ts-ignore… (casse les builds)")
        sp.add_argument("--max-len", type=int, default=80, metavar="N",
                        help="largeur de ligne visée (défaut 80)")
        sp.add_argument("--no-color", action="store_true")
        sp.add_argument("--json", action="store_true", dest="as_json",
                        help="sortie machine")
        sp.add_argument("--quiet", "-q", action="store_true", help="pas de diff")
        if apply_flag:
            sp.add_argument("--apply", action="store_true", help="écrire les modifications")
            sp.add_argument("--force", action="store_true",
                            help="accepter un dépôt git non propre")
            sp.add_argument("--no-backup", action="store_true")

    common(sub.add_parser("scan", help="rapport seul, aucune écriture"), apply_flag=False)
    common(sub.add_parser("nuke", help="supprimer les commentaires non protégés"))
    common(sub.add_parser("reduce", help="raccourcir sans reformuler"))

    for mode in ("synthesize", "humanize"):
        sp = sub.add_parser(mode, help=f"préparer un plan {mode} à remplir par le modèle")
        common(sp, apply_flag=False)
        sp.add_argument("--out", "-o", default="-", metavar="FICHIER",
                        help="où écrire le plan JSON (défaut : stdout)")

    ap = sub.add_parser("apply-plan", help="appliquer un plan rempli")
    ap.add_argument("plan", help="chemin du plan JSON")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--quiet", "-q", action="store_true")
    ap.add_argument("--json", "--as-json", action="store_true", dest="as_json")

    rp = sub.add_parser("restore", help="restaurer la dernière sauvegarde")
    rp.add_argument("--list", action="store_true", dest="list_only")
    rp.add_argument("--which", metavar="HORODATAGE")
    rp.add_argument("--no-color", action="store_true")
    return p


# --------------------------------------------------------------------------- #


def load_documents(files: List[Path], prot: Protections) -> List[Document]:
    docs = []
    for f in files:
        doc = Document.load(f)
        if doc is None:
            continue
        classify(doc.comments, prot)
        docs.append(doc)
    return docs


def cmd_scan(args) -> int:
    prot = Protections.from_args(args)
    files, label, notes = resolve(args.paths, args.scope_all, args.diff_base)
    docs = load_documents(files, prot)

    stats = {"files": len(docs), "comments": 0, "protected": 0, "ai_like": 0,
             "comment_lines": 0, "code_lines": 0}
    rows, details = [], []
    for doc in docs:
        prot_n = sum(1 for c in doc.comments if c.protected)
        ai_n = sum(1 for c in doc.comments if c.ai_score >= 0.5 and not c.protected)
        clines = sum(c.n_lines for c in doc.comments)
        stats["comments"] += len(doc.comments)
        stats["protected"] += prot_n
        stats["ai_like"] += ai_n
        stats["comment_lines"] += clines
        stats["code_lines"] += len(doc.text.splitlines())
        if doc.comments:
            rows.append((disp(doc.path), len(doc.comments) - prot_n, ai_n, prot_n))
        for c in doc.comments:
            if c.ai_score >= 0.5 and not c.protected:
                details.append({
                    "file": disp(doc.path), "line": c.line, "score": round(c.ai_score, 2),
                    "reasons": list(c.ai_reasons), "text": c.inner[:100],
                })

    if args.as_json:
        print(json.dumps({"target": label, "notes": notes, "stats": stats,
                          "ai_like": details[:200]}, ensure_ascii=False, indent=2))
        return 0

    print(report.header(f"scan — {label}"))
    for n in notes:
        print(report.yellow(f"  ! {n}"))
    if not docs:
        print(report.dim("  aucun fichier à analyser"))
        return 0
    print(report.summary_table([(f, a, b, c) for f, a, b, c in rows][:40])
          .replace("supprimés", "modifiables").replace("raccourcis", "style IA"))
    print()
    pct = 100 * stats["comment_lines"] / max(1, stats["code_lines"])
    print(f"  {stats['comments']} commentaires sur {stats['files']} fichiers "
          f"({stats['comment_lines']} lignes, {pct:.0f}% du volume)")
    print(f"  {report.yellow(str(stats['ai_like']))} au style IA marqué, "
          f"{report.dim(str(stats['protected']) + ' protégés')}")
    _hint_docs(docs)
    return 0


def _hint_docs(docs) -> None:
    hidden = [c for d in docs for c in d.comments
              if c.protected == DOC_REASON and c.ai_score >= 0.5]
    if hidden:
        print(report.dim(
            f"  {len(hidden)} doc(s) d'API au style IA sont protégées : "
            f"--shrink-docs les raccourcit sans les supprimer"))


# --------------------------------------------------------------------------- #


def cmd_transform(args, mode: str) -> int:
    prot = Protections.from_args(args)
    opts = Options(max_len=args.max_len, shrink_docs=args.shrink_docs,
                   min_ai_score=args.min_ai_score)
    files, label, notes = resolve(args.paths, args.scope_all, args.diff_base)
    docs = load_documents(files, prot)

    planner = plan_nuke if mode == "nuke" else plan_reduce
    changes: List[Tuple[Document, list, str]] = []
    failures = []
    for doc in docs:
        edits = planner(doc, opts)
        if not edits:
            continue
        new_text = apply_edits(doc.text, edits)
        ok, why = verify_code_unchanged(doc.text, new_text, doc.spec)
        if not ok:
            failures.append((doc.path, why))
            continue
        changes.append((doc, edits, new_text))

    return _finish(args, mode, label, notes, changes, failures, docs)


def _finish(args, mode, label, notes, changes, failures, docs) -> int:
    report.setup_color(getattr(args, "no_color", False))

    rows = []
    for doc, edits, new_text in changes:
        deleted = sum(1 for e in edits if e.action == DELETE)
        rows.append((disp(doc.path), deleted, len(edits) - deleted,
                     sum(1 for c in doc.comments if c.protected)))

    if getattr(args, "as_json", False):
        print(json.dumps({
            "mode": mode, "target": label, "notes": notes,
            "applied": bool(getattr(args, "apply", False)),
            "files": [{"file": disp(d.path), "deleted": r[1], "shortened": r[2],
                       "protected": r[3],
                       "lines_saved": report.lines_saved(d.text, t)}
                      for (d, _, t), r in zip(changes, rows)],
            "verification_failures": [{"file": disp(f), "why": w} for f, w in failures],
        }, ensure_ascii=False, indent=2))
        return 1 if failures else 0

    print(report.header(f"{mode} — {label}"))
    for n in notes:
        print(report.yellow(f"  ! {n}"))
    for f, why in failures:
        print(report.red(f"  ✗ {disp(f)} : transformation abandonnée ({why})"))

    if not changes:
        print(report.dim("  rien à modifier"))
        _hint_docs(docs)
        return 1 if failures else 0

    if not getattr(args, "quiet", False):
        for doc, _, new_text in changes:
            print()
            print(report.diff(doc.text, new_text, disp(doc.path)))

    print()
    print(report.summary_table(rows))
    saved = sum(report.lines_saved(d.text, t) for d, _, t in changes)
    total = sum(r[1] + r[2] for r in rows)
    print()
    print(f"  {total} commentaires touchés sur {len(changes)} fichiers, "
          f"{report.green(str(saved))} lignes en moins")
    _hint_docs(docs)

    if not getattr(args, "apply", False):
        print(report.dim("\n  simulation — relancez avec --apply pour écrire"))
        return 1 if failures else 0

    return _write(args, changes)


def _write(args, changes) -> int:
    cwd = Path.cwd()
    ok, msg = check_workspace(cwd, args.force)
    if not ok:
        print(report.red(f"\n  ✗ {msg}"))
        return 1
    if msg:
        print(report.yellow(f"  ! {msg}"))

    root = git_root(cwd) or cwd
    backup = None if args.no_backup else Backup(root)
    if backup is None and git_root(cwd) is None:
        print(report.red("  ✗ hors dépôt git, --no-backup est refusé"))
        return 1

    written = []
    for doc, _, new_text in changes:
        if backup:
            backup.save(doc.path)
        doc.path.write_text(new_text, encoding="utf-8")
        written.append(doc)

    bad = []
    for doc in written:
        result, detail = syntax_check(doc.path)
        if result is False:
            bad.append((doc.path, detail))

    if bad:
        print(report.red(f"\n  ✗ {len(bad)} fichier(s) ne compilent plus :"))
        for path, detail in bad:
            print(report.red(f"      {disp(path)} — {detail}"))
        if backup:
            n = backup.rollback([p for p, _ in bad])
            print(report.yellow(f"  ↩ {n} fichier(s) restaurés, les autres sont conservés"))
        else:
            print(report.red("  ! aucune sauvegarde : corrigez à la main"))
        written = [d for d in written if d.path not in {p for p, _ in bad}]

    where = backup.finalize() if backup else None
    if not written:
        return 1
    print(report.green(f"\n  ✓ {len(written)} fichier(s) écrits"))
    if where:
        print(report.dim(f"  sauvegarde : {where}"))
        print(report.dim("  annuler : nukeaicomment restore"))
    return 1 if bad else 0


# --------------------------------------------------------------------------- #


def cmd_plan(args, mode: str) -> int:
    report.setup_color(args.no_color)
    prot = Protections.from_args(args)
    opts = Options(max_len=args.max_len, shrink_docs=args.shrink_docs,
                   min_ai_score=args.min_ai_score)
    files, label, notes = resolve(args.paths, args.scope_all, args.diff_base)
    docs = load_documents(files, prot)
    root = git_root(Path.cwd()) or Path.cwd()

    plan = planfile.build(docs, mode, opts, root)
    body = json.dumps(plan, ensure_ascii=False, indent=2)

    if args.out == "-":
        print(body)
    else:
        Path(args.out).write_text(body, encoding="utf-8")
        print(report.header(f"{mode} — {label}"))
        for n in notes:
            print(report.yellow(f"  ! {n}"))
        print(f"  {len(plan['items'])} commentaires à réécrire → {args.out}")
        if not plan["items"]:
            print(report.dim("  rien à faire"))
        else:
            print(report.dim(f"  remplir new_text puis : "
                             f"nukeaicomment apply-plan {args.out} --apply"))
        _hint_docs(docs)
    return 0


def cmd_apply_plan(args) -> int:
    report.setup_color(args.no_color)
    plan = planfile.load(Path(args.plan))
    root = Path(plan["root"])
    edits_by_file, warns = planfile.to_edits(plan, root)

    changes, failures = [], []
    for path, edits in edits_by_file.items():
        doc = Document.load(path)
        new_text = apply_edits(doc.text, edits)
        ok, why = verify_code_unchanged(doc.text, new_text, doc.spec)
        if not ok:
            failures.append((path, why))
            continue
        changes.append((doc, edits, new_text))

    args.paths = []
    return _finish(args, plan["mode"], f"plan {args.plan}", warns, changes, failures, [])


def cmd_restore(args) -> int:
    report.setup_color(args.no_color)
    cwd = Path.cwd()
    root = git_root(cwd) or cwd
    if args.list_only:
        backups = list_backups(root)
        if not backups:
            print(report.dim("  aucune sauvegarde pour ce projet"))
            return 0
        for b in backups:
            manifest = json.loads((b / "manifest.json").read_text(encoding="utf-8"))
            print(f"  {b.name}  {len(manifest['files'])} fichier(s)")
        return 0
    n, where = restore(root, args.which)
    if not n:
        print(report.red("  ✗ aucune sauvegarde restaurable"))
        return 1
    print(report.green(f"  ✓ {n} fichier(s) restaurés depuis {where.name}"))
    return 0


# --------------------------------------------------------------------------- #


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    report.setup_color(getattr(args, "no_color", False))
    cmd = args.command
    if cmd == "scan":
        return cmd_scan(args)
    if cmd in ("nuke", "reduce"):
        return cmd_transform(args, cmd)
    if cmd in ("synthesize", "humanize"):
        return cmd_plan(args, cmd)
    if cmd == "apply-plan":
        return cmd_apply_plan(args)
    if cmd == "restore":
        return cmd_restore(args)
    return 1
