"""Machine à états qui extrait les commentaires réels d'un fichier.

Le seul point qui compte : ne jamais confondre un commentaire avec du contenu de
chaîne, une regex littérale, un heredoc ou un scalaire bloc YAML.
"""

import re
import textwrap
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .languages import BlockTok, LangSpec, LineTok, StringTok, spec_for

WORD = re.compile(r"[A-Za-z_$]")
REGEX_KEYWORDS = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
    "throw", "case", "do", "else", "yield", "await", "if", "while",
}
REGEX_PREV_CHARS = set("(,=:[!&|?{};+-*%~^<>\n")


@dataclass
class Comment:
    start: int
    end: int
    kind: str            # 'line' | 'block' | 'docstring'
    doc: bool = False
    lang: str = ""
    text: str = ""
    open_tok: str = ""
    close_tok: str = ""

    # remplis par annotate()
    file: str = ""
    id: str = ""
    line: int = 0
    end_line: int = 0
    col: int = 0
    indent: str = ""
    own_line: bool = False       # rien d'autre que des espaces avant sur la ligne
    trailing: bool = False       # du code précède sur la même ligne
    inner: str = ""              # texte nu, délimiteurs et décor retirés
    inner_lines: Tuple[str, ...] = ()
    code_before: str = ""
    code_after: str = ""
    code_same_line: str = ""
    jsx_wrapped: bool = False    # {/* ... */} seul sur sa ligne
    sole_statement: bool = False  # docstring seul corps de son bloc : la retirer casse la syntaxe

    protected: Optional[str] = None
    ai_score: float = 0.0
    ai_reasons: Tuple[str, ...] = ()

    @property
    def n_lines(self) -> int:
        return self.end_line - self.line + 1


def _sorted_toks(spec: LangSpec):
    lines = sorted(spec.lines, key=lambda t: -len(t.token))
    blocks = sorted(spec.blocks, key=lambda b: -len(b.open))
    strings = sorted(spec.strings, key=lambda s: -len(s.open))
    return lines, blocks, strings


def _at(text, i, s):
    return s and text.startswith(s, i)


def _ws_before(text, i):
    return i == 0 or text[i - 1] in " \t\n\r\f\v"


def scan_region(text: str, spec: LangSpec, start: int = 0, end: Optional[int] = None,
                out: Optional[List[Comment]] = None, brace_stop: bool = False) -> Tuple[List[Comment], int]:
    """Parcourt text[start:end] en état CODE et collecte les commentaires.

    brace_stop=True : utilisé pour l'intérieur d'un `${...}` de template literal,
    on rend la main sur le `}` fermant non apparié.
    """
    if out is None:
        out = []
    if end is None:
        end = len(text)

    lines, blocks, strings = _sorted_toks(spec)
    i = start
    last_sig = "\n"
    last_word = ""
    brace_depth = 0
    bracket_depth = 0

    while i < end:
        c = text[i]

        if c in " \t\r\n\f\v":
            i += 1
            continue

        # --- blocs avant tout : /* prime sur la regex / et sur // ---
        matched = False
        for b in blocks:
            if _at(text, i, b.open):
                j = _close_block(text, i, b, end)
                doc = bool(b.doc_prefix) and text.startswith(b.doc_prefix, i) \
                    and not text.startswith(b.open + b.close, i)
                open_tok = b.doc_prefix if doc else b.open
                out.append(Comment(i, j, "block", doc, spec.name, text[i:j],
                                   open_tok, b.close))
                i = j
                last_sig = " "
                matched = True
                break
        if matched:
            continue

        for lt in lines:
            if _at(text, i, lt.token) and (not lt.needs_ws_before or _ws_before(text, i)):
                j = text.find("\n", i, end)
                if j == -1:
                    j = end
                out.append(Comment(i, j, "line", lt.doc, spec.name, text[i:j], lt.token))
                i = j
                last_sig = "\n"
                matched = True
                break
        if matched:
            continue

        # --- Rust : r"..." et r#"..."# ---
        if spec.raw_string_hash and c == "r":
            j = _rust_raw_string(text, i, end)
            if j is not None:
                i, last_sig, last_word = j, '"', ""
                continue

        # --- Rust : 'a' littéral vs &'static durée de vie ---
        if spec.smart_char_literal and c == "'":
            if not (i + 1 < end and (text[i + 1] == "\\" or (i + 2 < end and text[i + 2] == "'"))):
                i += 1
                last_sig = "'"
                continue

        matched = False
        for st in strings:
            if _at(text, i, st.open):
                i = _scan_string(text, spec, i, st, out, end)
                last_sig = '"'
                last_word = ""
                matched = True
                break
        if matched:
            continue

        # --- heredocs ---
        if spec.heredoc == "shell" and _at(text, i, "<<") and not _at(text, i, "<<<"):
            j = _shell_heredoc(text, i, end)
            if j is not None:
                i = j
                continue
        if spec.heredoc == "php" and _at(text, i, "<<<"):
            j = _php_heredoc(text, i, end)
            if j is not None:
                i = j
                continue

        # --- scalaires bloc YAML : le corps n'est pas du code ---
        if spec.yaml_block_scalars and c in "|>":
            j = _yaml_block_scalar(text, i, end)
            if j is not None:
                i = j
                continue

        # --- regex littérale JS ---
        if spec.regex_literals and c == "/":
            if _regex_can_start(last_sig, last_word):
                j = _scan_js_regex(text, i, end)
                if j is not None:
                    i = j
                    last_sig = "/"
                    last_word = ""
                    continue

        if c in "([":
            bracket_depth += 1
        elif c in ")]":
            bracket_depth -= 1
        elif c == "{":
            brace_depth += 1
        elif c == "}":
            if brace_stop and brace_depth == 0:
                return out, i + 1
            brace_depth -= 1

        if WORD.match(c) or c.isdigit():
            k = i
            while k < end and (WORD.match(text[k]) or text[k].isdigit()):
                k += 1
            last_word = text[i:k]
            last_sig = text[k - 1]
            i = k
            continue

        last_sig = c
        last_word = ""
        i += 1

    return out, i


def _close_block(text, i, b: BlockTok, end):
    if b.nestable:
        depth = 0
        k = i
        while k < end:
            if text.startswith(b.open, k):
                depth += 1
                k += len(b.open)
            elif text.startswith(b.close, k):
                depth -= 1
                k += len(b.close)
                if depth == 0:
                    return k
            else:
                k += 1
        return end
    j = text.find(b.close, i + len(b.open), end)
    return end if j == -1 else j + len(b.close)


def _scan_string(text, spec, i, st: StringTok, out, end):
    """Consomme une chaîne. Peut rappeler le scanner pour un `${...}`."""
    k = i + len(st.open)
    while k < end:
        c = text[k]
        if st.escape and c == st.escape:
            k += 2
            continue
        if st.interpolates and c == "$" and text.startswith("${", k):
            _, k = scan_region(text, spec, k + 2, end, out, brace_stop=True)
            continue
        if text.startswith(st.close, k):
            if st.doubling_escapes and text.startswith(st.close, k + len(st.close)):
                k += 2 * len(st.close)
                continue
            return k + len(st.close)
        if c == "\n" and not st.multiline:
            return k  # chaîne non terminée : on repart en mode code à la ligne suivante
        k += 1
    return end


def _rust_raw_string(text, i, end):
    k = i + 1
    hashes = 0
    while k < end and text[k] == "#":
        hashes += 1
        k += 1
    if k >= end or text[k] != '"':
        return None
    closer = '"' + "#" * hashes
    j = text.find(closer, k + 1, end)
    return end if j == -1 else j + len(closer)


def _regex_can_start(last_sig, last_word):
    if last_word in REGEX_KEYWORDS:
        return True
    if last_word:
        return False
    return last_sig in REGEX_PREV_CHARS


def _scan_js_regex(text, i, end):
    """Retourne la fin d'une regex littérale, ou None si ça n'en est pas une."""
    k = i + 1
    in_class = False
    while k < end:
        c = text[k]
        if c == "\\":
            k += 2
            continue
        if c == "\n":
            return None
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            k += 1
            while k < end and text[k].isalpha():
                k += 1
            return k
        k += 1
    return None


def _shell_heredoc(text, i, end):
    m = re.compile(r"<<[-~]?\s*(?:(['\"])(\w+)\1|(\w+))").match(text, i, end)
    if not m:
        return None
    word = m.group(2) or m.group(3)
    dash = text[i + 2:i + 3] in ("-", "~")
    nl = text.find("\n", m.end(), end)
    if nl == -1:
        return end
    pat = re.compile(r"^[ \t]*" + re.escape(word) + r"[ \t]*$" if dash
                     else r"^" + re.escape(word) + r"[ \t]*$", re.M)
    m2 = pat.search(text, nl + 1, end)
    return end if not m2 else m2.end()


def _php_heredoc(text, i, end):
    m = re.compile(r"<<<[ \t]*(?:(['\"])(\w+)\1|(\w+))[ \t]*\r?\n").match(text, i, end)
    if not m:
        return None
    word = m.group(2) or m.group(3)
    m2 = re.compile(r"^[ \t]*" + re.escape(word) + r"\b", re.M).search(text, m.end(), end)
    return end if not m2 else m2.end()


def _yaml_block_scalar(text, i, end):
    """`key: |` → le corps indenté qui suit n'est pas scannable."""
    m = re.compile(r"[|>][+-]?\d*[ \t]*(#[^\n]*)?\r?\n").match(text, i, end)
    if not m:
        return None
    line_start = text.rfind("\n", 0, i) + 1
    base = len(text[line_start:i]) - len(text[line_start:i].lstrip())
    k = m.end()
    while k < end:
        nl = text.find("\n", k, end)
        if nl == -1:
            nl = end
        line = text[k:nl]
        if line.strip() and (len(line) - len(line.lstrip())) <= base:
            break
        k = nl + 1
        if nl >= end:
            break
    return k


# --------------------------------------------------------------------------- #


def scan(text: str, spec: LangSpec) -> List[Comment]:
    out, _ = scan_region(text, spec)
    if spec.py_docstrings:
        out = _python_docstrings(text, spec, out)
    out.sort(key=lambda c: c.start)
    return out


_PY_TRIPLE = re.compile(r"(?:[rRbBuUfF]{0,2})('''|\"\"\")")
_PY_DEF = re.compile(r"^\s*(async\s+)?(def|class)\b")


def _python_docstrings(text, spec, comments):
    """Repère les triple-quotes qui servent de docstring, hors parenthèses."""
    covered = [(c.start, c.end) for c in comments]

    def in_comment(pos):
        return any(a <= pos < b for a, b in covered)

    found = []
    for m in _PY_TRIPLE.finditer(text):
        if in_comment(m.start()):
            continue
        q = m.group(1)
        close = text.find(q, m.end())
        endpos = len(text) if close == -1 else close + 3
        if any(a <= m.start() < b for a, b in found):
            continue
        found.append((m.start(), endpos))

    docs = []
    for a, b in found:
        line_start = text.rfind("\n", 0, a) + 1
        prefix = text[line_start:a]
        if prefix.strip():
            continue  # `x = """..."""` : ce n'est pas une docstring
        if not _is_docstring_position(text, line_start, found):
            continue
        quote = '"""' if '"""' in text[a:a + 6] else "'''"
        docs.append(Comment(a, b, "docstring", True, spec.name, text[a:b], quote, quote))
    return comments + docs


def _is_docstring_position(text, line_start, found):
    head = text[:line_start]
    code = _strip_py_code(head)
    if not code:
        return True  # docstring de module
    depth = 0
    for m in re.finditer(r"[()\[\]{}]", _mask_strings(code)):
        depth += 1 if m.group() in "([{" else -1
    if depth > 0:
        return False  # à l'intérieur d'un appel ou d'un littéral
    for raw in reversed(head.splitlines()):
        line = raw.split("#")[0].rstrip()
        if not line.strip():
            continue
        return line.endswith(":")
    return False


def _mask_strings(s):
    return re.sub(r"(\"\"\".*?\"\"\"|'''.*?'''|\"[^\"\n]*\"|'[^'\n]*')", "", s, flags=re.S)


def _strip_py_code(s):
    out = []
    for raw in s.splitlines():
        line = raw.split("#")[0].strip()
        if line:
            out.append(line)
    return "\n".join(out)


# --------------------------------------------------------------------------- #


def annotate(text: str, comments: List[Comment], path: str = "") -> List[Comment]:
    """Complète chaque commentaire : lignes, indentation, texte nu, contexte."""
    starts = _line_starts(text)
    lines = text.splitlines()
    for n, c in enumerate(comments):
        c.file = path
        c.id = f"c{n:04d}"
        c.line = _line_of(starts, c.start)
        c.end_line = _line_of(starts, c.end - 1 if c.end > c.start else c.start)
        ls = starts[c.line - 1]
        c.col = c.start - ls
        prefix = text[ls:c.start]
        c.own_line = not prefix.strip()
        c.indent = prefix if c.own_line else re.match(r"[ \t]*", prefix).group()
        c.jsx_wrapped = _is_jsx_wrapped(text, c, ls)
        if c.jsx_wrapped:
            # `{/* … */}` : la ligne entière appartient au commentaire, accolades comprises
            c.own_line = True
        c.trailing = not c.own_line
        c.inner_lines = tuple(_strip_delims(c))
        c.inner = " ".join(l for l in c.inner_lines if l).strip()
        c.code_before = "\n".join(lines[max(0, c.line - 4):c.line - 1])
        c.code_after = "\n".join(lines[c.end_line:c.end_line + 3])
        c.code_same_line = prefix.strip()
        c.sole_statement = _is_sole_statement(lines, c)
    return comments


def _is_sole_statement(lines, c: Comment) -> bool:
    """Une docstring indentée sans autre instruction dans son bloc n'est pas retirable."""
    if c.kind != "docstring" or not c.indent:
        return False
    depth = len(c.indent.expandtabs(4))
    for raw in lines[c.end_line:]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        return len(raw[: len(raw) - len(raw.lstrip())].expandtabs(4)) < depth
    return True


def _is_jsx_wrapped(text, c, line_start):
    if c.kind != "block":
        return False
    before = text[line_start:c.start]
    if before.strip() != "{":
        return False
    nl = text.find("\n", c.end)
    after = text[c.end:nl if nl != -1 else len(text)].strip()
    return after.startswith("}")


_DECOR = re.compile(r"^[\s*/#\-=~_!<>]+|[\s*/#\-=~_]+$")


def _strip_delims(c: Comment):
    raw = c.text
    if c.kind == "docstring":
        body = raw
        for q in ('"""', "'''"):
            if q in body:
                body = body.split(q, 1)[-1]
                if body.endswith(q):
                    body = body[: -len(q)]
                break
        # l'indentation relative porte la structure (Args:, Returns:) : on la garde
        head, _, rest = body.partition("\n")
        out = [head.strip()]
        out.extend(l.rstrip() for l in textwrap.dedent(rest).splitlines())
        while out and not out[-1].strip():
            out.pop()
        return out
    out = []
    for line in raw.splitlines():
        s = line.strip()
        for d in ("<!--", "-->", "/**", "*/", "/*", "///", "//!", "//", "--[[", "]]",
                  "=begin", "=end", "--", "#", ";"):
            if s.startswith(d):
                s = s[len(d):]
                break
        if s.endswith("-->"):
            s = s[:-3]
        if s.endswith("*/"):
            s = s[:-2]
        if s.endswith("]]"):
            s = s[:-2]
        s = re.sub(r"^\s*\*(?!/)", "", s)
        out.append(s.strip())
    return out


def _line_starts(text):
    starts = [0]
    for m in re.finditer(r"\n", text):
        starts.append(m.end())
    return starts


def _line_of(starts, pos):
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= pos:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def strip_comments(text: str, comments: List[Comment]) -> str:
    """Retire les spans de commentaires. Base de l'invariant de vérification."""
    out = []
    prev = 0
    for c in sorted(comments, key=lambda c: c.start):
        out.append(text[prev:c.start])
        prev = max(prev, c.end)
    out.append(text[prev:])
    return "".join(out)
