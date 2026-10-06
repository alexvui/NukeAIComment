import unittest

from nukeai import languages as L
from nukeai.document import Document, canonical, scan_text


def comments(text, spec, path="x"):
    return scan_text(text, spec, path)


def inners(text, spec):
    return [c.inner for c in comments(text, spec)]


class TestJavaScript(unittest.TestCase):
    def test_line_and_block(self):
        src = "// un\nconst a = 1; /* deux */\n"
        self.assertEqual(inners(src, L.JS), ["un", "deux"])

    def test_double_slash_inside_string_is_not_a_comment(self):
        src = 'const url = "https://example.com/x";\n'
        self.assertEqual(comments(src, L.JS), [])

    def test_double_slash_inside_template_literal(self):
        src = "const u = `https://a.b/${x}//y`;\n"
        self.assertEqual(comments(src, L.JS), [])

    def test_comment_inside_template_interpolation_is_found(self):
        src = "const u = `a${ /* ici */ x }b`;\n"
        self.assertEqual(inners(src, L.JS), ["ici"])

    def test_regex_literal_with_slashes(self):
        src = "const re = /path\\/to\\/[^/]+/g;\nconst y = 2;\n"
        self.assertEqual(comments(src, L.JS), [])

    def test_division_is_not_a_regex(self):
        src = "const r = a / b; // ok\n"
        self.assertEqual(inners(src, L.JS), ["ok"])

    def test_regex_after_return(self):
        src = "function f() { return /a\\/b/.test(s); } // fin\n"
        self.assertEqual(inners(src, L.JS), ["fin"])

    def test_jsdoc_is_flagged_as_doc(self):
        src = "/**\n * Fait un truc.\n * @param {number} n - Le nombre\n */\nfunction f(n) {}\n"
        c = comments(src, L.JS)[0]
        self.assertTrue(c.doc)
        self.assertEqual(c.open_tok, "/**")

    def test_empty_block_is_not_doc(self):
        self.assertFalse(comments("/**/\n", L.JS)[0].doc)

    def test_jsx_wrapped_detection(self):
        src = "return (\n  <div>\n    {/* note */}\n  </div>\n);\n"
        c = comments(src, L.JS)[0]
        self.assertTrue(c.jsx_wrapped)

    def test_apostrophe_in_block_comment_does_not_leak(self):
        src = "/* l'idée */\nconst a = 1;\nconst b = 2;\n"
        self.assertEqual(inners(src, L.JS), ["l'idée"])

    def test_url_in_line_comment_keeps_one_comment(self):
        src = "// voir https://x.com/a//b\nconst a = 1;\n"
        self.assertEqual(len(comments(src, L.JS)), 1)


class TestPython(unittest.TestCase):
    def test_hash_comment(self):
        self.assertEqual(inners("x = 1  # note\n", L.PYTHON), ["note"])

    def test_hash_inside_string(self):
        self.assertEqual(comments('x = "a # b"\n', L.PYTHON), [])

    def test_hash_without_space_is_a_comment(self):
        self.assertEqual(inners("x=1#c\n", L.PYTHON), ["c"])

    def test_module_docstring(self):
        src = '"""Doc du module."""\nimport os\n'
        c = comments(src, L.PYTHON)[0]
        self.assertEqual(c.kind, "docstring")
        self.assertEqual(c.inner, "Doc du module.")

    def test_function_docstring(self):
        src = 'def f():\n    """Fait un truc."""\n    return 1\n'
        self.assertEqual([c.kind for c in comments(src, L.PYTHON)], ["docstring"])

    def test_assigned_triple_string_is_not_a_docstring(self):
        src = 'TEMPLATE = """\nbonjour\n"""\n'
        self.assertEqual(comments(src, L.PYTHON), [])

    def test_triple_string_argument_is_not_a_docstring(self):
        src = 'run(\n    """\n    requête\n    """\n)\n'
        self.assertEqual(comments(src, L.PYTHON), [])

    def test_hash_inside_triple_quoted_string(self):
        src = 'S = """\n# pas un commentaire\n"""\nx = 1\n'
        self.assertEqual(comments(src, L.PYTHON), [])

    def test_multiline_docstring_lines(self):
        src = 'def f():\n    """Résumé.\n\n    Détail.\n    """\n'
        c = comments(src, L.PYTHON)[0]
        self.assertEqual(c.line, 2)
        self.assertEqual(c.end_line, 5)


class TestShellAndConfig(unittest.TestCase):
    def test_shell_hash_needs_whitespace(self):
        self.assertEqual(comments("echo foo#bar\n", L.SHELL), [])
        self.assertEqual(inners("echo foo # bar\n", L.SHELL), ["bar"])

    def test_shebang_is_a_comment(self):
        c = comments("#!/usr/bin/env bash\necho ok\n", L.SHELL)[0]
        self.assertTrue(c.text.startswith("#!"))

    def test_heredoc_body_is_not_scanned(self):
        src = "cat <<EOF\n# pas un commentaire\nEOF\n# vrai commentaire\n"
        self.assertEqual(inners(src, L.SHELL), ["vrai commentaire"])

    def test_quoted_heredoc(self):
        src = "cat <<'EOF'\n# rien\nEOF\n"
        self.assertEqual(comments(src, L.SHELL), [])

    def test_yaml_comment(self):
        self.assertEqual(inners("a: 1  # note\n", L.YAML), ["note"])

    def test_yaml_hash_in_plain_scalar(self):
        self.assertEqual(comments("url: http://x.com#frag\n", L.YAML), [])

    def test_yaml_block_scalar_body_ignored(self):
        src = "script: |\n  echo x\n  # pas un commentaire\nkey: 2  # oui\n"
        self.assertEqual(inners(src, L.YAML), ["oui"])


class TestOtherLanguages(unittest.TestCase):
    def test_sql_double_dash(self):
        self.assertEqual(inners("SELECT 1; -- note\n", L.SQL), ["note"])

    def test_sql_doubled_quote_escape(self):
        self.assertEqual(comments("SELECT 'it''s -- ok';\n", L.SQL), [])

    def test_go_raw_string(self):
        self.assertEqual(comments("s := `a // b`\n", L.GO), [])

    def test_rust_lifetime_is_not_a_string(self):
        src = "fn f<'a>(x: &'a str) {} // fin\n"
        self.assertEqual(inners(src, L.RUST), ["fin"])

    def test_rust_nested_block_comment(self):
        src = "/* a /* b */ c */\nfn main() {}\n"
        self.assertEqual(len(comments(src, L.RUST)), 1)

    def test_rust_raw_string_hash(self):
        self.assertEqual(comments('let s = r#"a // b"#;\n', L.RUST), [])

    def test_ruby_begin_end_block(self):
        src = "=begin\nbloc\n=end\nputs 1\n"
        self.assertEqual(len(comments(src, L.RUBY)), 1)

    def test_css_has_no_line_comments(self):
        self.assertEqual(comments("a { background: url(//x); }\n", L.CSS), [])

    def test_scss_has_line_comments(self):
        self.assertEqual(inners("// note\na { color: red; }\n", L.SCSS), ["note"])


class TestRegions(unittest.TestCase):
    def test_html_url_is_not_a_comment(self):
        src = '<a href="https://x.com">y</a>\n<!-- vrai -->\n'
        self.assertEqual(inners(src, L.HTML), ["vrai"])

    def test_html_script_uses_js_rules(self):
        src = "<script>\n// js\nconst a = 1;\n</script>\n<!-- html -->\n"
        self.assertEqual(sorted(inners(src, L.HTML)), ["html", "js"])

    def test_html_json_script_is_skipped(self):
        src = '<script type="application/json">{"a": "//x"}</script>\n'
        self.assertEqual(comments(src, L.HTML), [])

    def test_vue_three_regions(self):
        src = (
            "<template>\n  <!-- tpl -->\n  <div/>\n</template>\n"
            "<script lang=\"ts\">\n// js\nexport default {};\n</script>\n"
            "<style>\n/* css */\na { color: red; }\n</style>\n"
        )
        self.assertEqual(sorted(inners(src, L.VUE)), ["css", "js", "tpl"])

    def test_php_html_outside_tags(self):
        src = '<a href="https://x">y</a>\n<?php // vrai\n$a = 1;\n?>\n'
        self.assertEqual(inners(src, L.PHP), ["vrai"])


class TestCanonical(unittest.TestCase):
    def test_canonical_ignores_comments_and_blank_lines(self):
        a = "// un\nconst a = 1;\n\n\nconst b = 2; // deux\n"
        b = "const a = 1;\nconst b = 2;\n"
        self.assertEqual(canonical(a, L.JS), canonical(b, L.JS))

    def test_canonical_detects_code_change(self):
        a = "const a = 1;\n"
        b = "const a = 2;\n"
        self.assertNotEqual(canonical(a, L.JS), canonical(b, L.JS))

    def test_canonical_indent_sensitive_for_python(self):
        a = "def f():\n    return 1\n"
        b = "def f():\nreturn 1\n"
        self.assertNotEqual(canonical(a, L.PYTHON), canonical(b, L.PYTHON))

    def test_canonical_jsx_braces(self):
        a = "<div>\n  {/* c */}\n</div>\n"
        b = "<div>\n</div>\n"
        self.assertEqual(canonical(a, L.JS), canonical(b, L.JS))


if __name__ == "__main__":
    unittest.main()
