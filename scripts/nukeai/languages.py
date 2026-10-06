"""Table de syntaxe par langage, consommée par le scanner."""

from dataclasses import dataclass, replace
from typing import Optional, Tuple


@dataclass(frozen=True)
class LineTok:
    token: str
    # '#' n'ouvre pas de commentaire au milieu d'un mot en shell/yaml, mais si en python
    needs_ws_before: bool = False
    doc: bool = False


@dataclass(frozen=True)
class BlockTok:
    open: str
    close: str
    doc_prefix: Optional[str] = None
    nestable: bool = False


@dataclass(frozen=True)
class StringTok:
    open: str
    close: str
    escape: str = "\\"
    multiline: bool = False
    doubling_escapes: bool = False  # '' à l'intérieur de '...' (SQL, YAML)
    interpolates: bool = False      # `${...}` revient en mode code (template JS)


@dataclass(frozen=True)
class LangSpec:
    name: str
    lines: Tuple[LineTok, ...] = ()
    blocks: Tuple[BlockTok, ...] = ()
    strings: Tuple[StringTok, ...] = ()
    regex_literals: bool = False
    jsx: bool = False
    py_docstrings: bool = False
    smart_char_literal: bool = False  # Rust : distinguer 'a' de &'static
    heredoc: Optional[str] = None     # 'shell' | 'php'
    yaml_block_scalars: bool = False
    raw_string_hash: bool = False     # Rust : r#"..."#

    @property
    def all_delims(self):
        out = [l.token for l in self.lines]
        for b in self.blocks:
            out.extend((b.open, b.close))
        return out


SQ = StringTok("'", "'")
DQ = StringTok('"', '"')

_C_STRINGS = (SQ, DQ)
_C_BLOCK = BlockTok("/*", "*/", doc_prefix="/**")
_C_LINES = (LineTok("//"),)
_C_DOC_LINES = (LineTok("///", doc=True), LineTok("//!", doc=True), LineTok("//"))

JS = LangSpec(
    name="javascript",
    lines=_C_LINES,
    blocks=(_C_BLOCK,),
    strings=(SQ, DQ, StringTok("`", "`", multiline=True, interpolates=True)),
    regex_literals=True,
    jsx=True,
)

TS = replace(JS, name="typescript")

PYTHON = LangSpec(
    name="python",
    lines=(LineTok("#"),),
    strings=(
        StringTok('"""', '"""', multiline=True),
        StringTok("'''", "'''", multiline=True),
        DQ,
        SQ,
    ),
    py_docstrings=True,
)

CSS = LangSpec(name="css", blocks=(_C_BLOCK,), strings=_C_STRINGS)
SCSS = LangSpec(name="scss", lines=_C_LINES, blocks=(_C_BLOCK,), strings=_C_STRINGS)

HTML = LangSpec(name="html", blocks=(BlockTok("<!--", "-->"),))

C_LIKE = LangSpec(name="c", lines=_C_DOC_LINES, blocks=(_C_BLOCK,), strings=_C_STRINGS)

JAVA = LangSpec(
    name="java",
    lines=_C_LINES,
    blocks=(_C_BLOCK,),
    strings=(StringTok('"""', '"""', multiline=True), DQ, SQ),
)

KOTLIN = replace(JAVA, name="kotlin")
SCALA = replace(JAVA, name="scala")

CSHARP = LangSpec(
    name="csharp",
    lines=_C_DOC_LINES,
    blocks=(_C_BLOCK,),
    strings=(StringTok('"""', '"""', multiline=True), DQ, SQ),
)

GO = LangSpec(
    name="go",
    lines=_C_LINES,
    blocks=(_C_BLOCK,),
    strings=(DQ, SQ, StringTok("`", "`", escape="", multiline=True)),
)

RUST = LangSpec(
    name="rust",
    lines=_C_DOC_LINES,
    blocks=(BlockTok("/*", "*/", doc_prefix="/**", nestable=True),),
    strings=(DQ,),
    smart_char_literal=True,
    raw_string_hash=True,
)

SWIFT = LangSpec(
    name="swift",
    lines=_C_DOC_LINES,
    blocks=(BlockTok("/*", "*/", doc_prefix="/**", nestable=True),),
    strings=(StringTok('"""', '"""', multiline=True), DQ),
)

PHP = LangSpec(
    name="php",
    lines=(LineTok("//"), LineTok("#")),
    blocks=(_C_BLOCK,),
    strings=_C_STRINGS,
    heredoc="php",
)

RUBY = LangSpec(
    name="ruby",
    lines=(LineTok("#"),),
    blocks=(BlockTok("=begin", "=end"),),
    strings=_C_STRINGS,
)

SQL = LangSpec(
    name="sql",
    lines=(LineTok("--", needs_ws_before=True), LineTok("#", needs_ws_before=True)),
    blocks=(BlockTok("/*", "*/"),),
    strings=(StringTok("'", "'", doubling_escapes=True), DQ),
)

SHELL = LangSpec(
    name="shell",
    lines=(LineTok("#", needs_ws_before=True),),
    strings=(StringTok("'", "'", escape=""), DQ),
    heredoc="shell",
)

YAML = LangSpec(
    name="yaml",
    lines=(LineTok("#", needs_ws_before=True),),
    strings=(StringTok("'", "'", escape="", doubling_escapes=True), DQ),
    yaml_block_scalars=True,
)

TOML = LangSpec(
    name="toml",
    lines=(LineTok("#", needs_ws_before=True),),
    strings=(StringTok('"""', '"""', multiline=True),
             StringTok("'''", "'''", multiline=True, escape=""),
             DQ, StringTok("'", "'", escape="")),
)

INI = LangSpec(
    name="ini",
    lines=(LineTok("#", needs_ws_before=True), LineTok(";", needs_ws_before=True)),
    strings=_C_STRINGS,
)

DOCKERFILE = LangSpec(name="dockerfile", lines=(LineTok("#", needs_ws_before=True),),
                      strings=_C_STRINGS)

MAKEFILE = LangSpec(name="makefile", lines=(LineTok("#", needs_ws_before=True),),
                    strings=_C_STRINGS)

LUA = LangSpec(
    name="lua",
    lines=(LineTok("--"),),
    blocks=(BlockTok("--[[", "]]"),),
    strings=_C_STRINGS,
)

VUE = LangSpec(name="vue")       # multi-région, résolu par regions.py
SVELTE = LangSpec(name="svelte")

EXTENSIONS = {
    ".js": JS, ".mjs": JS, ".cjs": JS, ".jsx": JS,
    ".ts": TS, ".mts": TS, ".cts": TS, ".tsx": TS,
    ".py": PYTHON, ".pyi": PYTHON, ".pyw": PYTHON,
    ".css": CSS, ".scss": SCSS, ".sass": SCSS, ".less": SCSS,
    ".html": HTML, ".htm": HTML, ".xml": HTML, ".svg": HTML, ".xhtml": HTML,
    ".vue": VUE, ".svelte": SVELTE,
    ".php": PHP, ".phtml": PHP,
    ".go": GO,
    ".java": JAVA, ".kt": KOTLIN, ".kts": KOTLIN, ".scala": SCALA, ".sc": SCALA,
    ".cs": CSHARP,
    ".rb": RUBY, ".rake": RUBY, ".gemspec": RUBY,
    ".rs": RUST,
    ".swift": SWIFT,
    ".dart": JAVA,
    ".c": C_LIKE, ".h": C_LIKE, ".cpp": C_LIKE, ".cc": C_LIKE, ".cxx": C_LIKE,
    ".hpp": C_LIKE, ".hh": C_LIKE, ".m": C_LIKE, ".mm": C_LIKE,
    ".sql": SQL,
    ".sh": SHELL, ".bash": SHELL, ".zsh": SHELL, ".ksh": SHELL,
    ".yml": YAML, ".yaml": YAML,
    ".toml": TOML,
    ".ini": INI, ".cfg": INI, ".conf": INI, ".editorconfig": INI,
    ".lua": LUA,
    ".env": SHELL,
}

FILENAMES = {
    "Dockerfile": DOCKERFILE,
    "Containerfile": DOCKERFILE,
    "Makefile": MAKEFILE,
    "GNUmakefile": MAKEFILE,
    "Gemfile": RUBY,
    "Rakefile": RUBY,
    "Vagrantfile": RUBY,
    ".env": SHELL,
    ".bashrc": SHELL,
    ".zshrc": SHELL,
    ".profile": SHELL,
}

MULTI_REGION = {"vue", "svelte", "html", "php"}


def spec_for(path) -> Optional[LangSpec]:
    """Résout la LangSpec d'un chemin, ou None si le langage est inconnu."""
    from pathlib import Path

    p = Path(path)
    if p.name in FILENAMES:
        return FILENAMES[p.name]
    if p.name.startswith("Dockerfile"):
        return DOCKERFILE
    if p.name.startswith(".env"):
        return SHELL
    return EXTENSIONS.get(p.suffix.lower())
