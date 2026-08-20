"""Compiles languages/mizo.yaml into the target package's _mizo.py.

The Python package should not depend on PyYAML or read the spec at import
time (#20). Instead, the spec is compiled here into a plain Python module
that ships with the package. This is similar to generate_vectors.py -- it
uses the same PyYAML dependency and is run the same way.

Run from inside reference/:

    python compile_spec.py

Regenerate and commit the generated file whenever languages/mizo.yaml
changes. test_compile_spec.py fails if the checked-in copy is out of date.

This module intentionally uses a few private names from engine.py. The
compiler is part of the same reference implementation, so sharing the
placeholder pattern and positional variable names avoids keeping duplicate
copies that could drift apart.
"""

import ast
from pathlib import Path

from engine import (
    _BOOL_COMBINERS,
    _COMPARISONS,
    _PLACEHOLDER_RE,
    _positional_variables,
    load,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "languages" / "mizo.yaml"
ARTIFACT_PATH = (
    REPO_ROOT / "packages" / "python" / "src" / "numberwords" / "_mizo.py"
)

# The positional variable names a placeholder key or a condition may use.
# Derived from the engine so the two cannot disagree.
VARIABLE_NAMES = frozenset(_positional_variables(0))

_HEADER = '''"""Compiled from languages/mizo.yaml by reference/compile_spec.py.

Do not edit by hand. Regenerate with `python compile_spec.py` from
reference/ and commit the result.
"""'''


def _placeholder_key(raw_key):
    """A placeholder's key is either a positional variable name, which is
    looked up at runtime, or a fixed integer, which is used directly.
    Matches engine._resolve_key.
    """
    if raw_key in VARIABLE_NAMES:
        return raw_key
    return int(raw_key)


def _parse_template(template):
    """Splits a template into parts. String parts are literal text, and
    three-tuples represent placeholders (table, key, field). The renderer
    works with these parts directly, so it doesn't need to run a regex.
    """
    parts = []
    position = 0
    for match in _PLACEHOLDER_RE.finditer(template):
        if match.start() > position:
            parts.append(template[position:match.start()])
        table, raw_key, field = match.groups()
        parts.append((table, _placeholder_key(raw_key), field))
        position = match.end()
    if position < len(template):
        parts.append(template[position:])
    return tuple(parts)


# Compiling conditions means there are two places that define how a
# condition works: engine._eval_node and the compiled lambda below.
# What keeps them in sync today is vectors/mizo.json. It covers every
# number from 0 to 199, so every compiled condition is tested against
# every possible input. That held before #19 at 0-100 and still holds
# now the range is 0-199. Once the range grows beyond that, the vectors
# will no longer test every case, so this should have its own property
# test instead of relying only on the vectors.


def _validate_condition(node):
    """Raises ValueError if the condition contains anything engine._eval_node
    would not allow. Validation runs before the tree is rewritten, so an
    invalid expression is never turned back into code.
    """
    if isinstance(node, ast.Compare):
        for op in node.ops:
            if type(op) not in _COMPARISONS:
                raise ValueError(
                    f"Unsupported comparison operator: {type(op).__name__}"
                )
        _validate_condition(node.left)
        for comparator in node.comparators:
            _validate_condition(comparator)
        return
    if isinstance(node, ast.BoolOp):
        if type(node.op) not in _BOOL_COMBINERS:
            raise ValueError(
                f"Unsupported boolean operator: {type(node.op).__name__}"
            )
        for value in node.values:
            _validate_condition(value)
        return
    if isinstance(node, ast.Name):
        if node.id not in VARIABLE_NAMES:
            raise ValueError(f"Unknown variable in condition: {node.id!r}")
        return
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return
    raise ValueError(f"Unsupported expression in condition: {ast.dump(node)}")


class _NameToLookup(ast.NodeTransformer):
    """Rewrites a variable name like `ones_digit` into
    `variables['ones_digit']`, so the generated lambda reads values
    from the dictionary provided by the renderer.
    """

    def visit_Name(self, node):
        return ast.Subscript(
            value=ast.Name(id="variables", ctx=ast.Load()),
            slice=ast.Constant(value=node.id),
            ctx=ast.Load(),
        )


def _compile_condition(expression):
    """Turns a condition from the spec into the source code for a lambda.
    The tree is validated first, then rewritten, then converted back into
    code. That way, an invalid expression is never passed to ast.unparse.
    The lambda is created with ast.unparse instead of building the code by
    hand. This lets Python define what the condition means, instead of
    having a second implementation in the compiler. That is especially
    important for chained comparisons like `0 < d < 5`, whose behaviour is
    already defined by engine._eval_node.
    """
    tree = ast.parse(expression, mode="eval").body
    _validate_condition(tree)
    rewritten = ast.fix_missing_locations(_NameToLookup().visit(tree))
    return f"lambda variables: {ast.unparse(rewritten)}"


def _format_condition(condition):
    """A rule without a condition emits None; the renderer treats that as
    "always applies", the same way engine._find_rule does.
    """
    if condition is None:
        return "None"
    return _compile_condition(condition)


def _format_lexicon(lexicon):
    lines = ["LEXICON = {"]
    for table in sorted(lexicon):
        lines.append(f"    {table!r}: {{")
        for key in sorted(lexicon[table]):
            entry = lexicon[table][key]
            fields = ", ".join(
                f"{name!r}: {entry[name]!r}" for name in sorted(entry)
            )
            lines.append(f"        {key!r}: {{{fields}}},")
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines)


def _format_rules(rules):
    lines = ["RULES = ("]
    for rule in rules:
        low, high = rule["range"]
        aliases = tuple(
            _parse_template(t) for t in rule.get("parse_aliases", [])
        )
        lines.append("    {")
        lines.append(f"        'name': {rule['name']!r},")
        lines.append(f"        'range': ({low}, {high}),")
        lines.append(
            f"        'condition': "
            f"{_format_condition(rule.get('condition'))},"
        )
        lines.append(f"        'output': {_parse_template(rule['output'])!r},")
        lines.append(f"        'parse_aliases': {aliases!r},")
        lines.append("    },")
    lines.append(")")
    return "\n".join(lines)


def _format_parse(spec):
    """The parse config, with connectors and aliases already normalised.
    Doing this here means the renderer only needs to compare plain strings,
    instead of normalising them on every call.
    """
    config = spec.parse_config
    connectors = tuple(
        sorted(spec._normalize_word(c) for c in config.get("connectors", []))
    )
    aliases = {
        spec._normalize_word(variant): spec._normalize_word(canonical)
        for variant, canonical in sorted(config.get("aliases", {}).items())
    }
    # Field lists become tuples, like connectors and word_separators above:
    # the renderer only reads them, and a literal tuple cannot be mutated by
    # accident once it ships inside the package.
    accepted = {
        table: tuple(fields)
        for table, fields in sorted(config.get("accepted_forms", {}).items())
    }
    lines = [
        "PARSE = {",
        f"    'case_insensitive': {config.get('case_insensitive', False)!r},",
        f"    'strip_diacritics': {config.get('strip_diacritics', False)!r},",
        f"    'word_separators': "
        f"{tuple(config.get('word_separators', [' ']))!r},",
        f"    'accepted_forms': {accepted!r},",
        f"    'connectors': {connectors!r},",
        f"    'aliases': {aliases!r},",
        "}",
    ]
    return "\n".join(lines)


def render_module(spec):
    """Returns the full source text of the compiled module."""
    meta = spec._data["meta"]
    provenance = "\n".join(
        [
            f"LANGUAGE = {meta['language']!r}",
            f"CODE = {meta['code']!r}",
            f"SPEC_VERSION = {str(meta['version'])!r}",
            f"SUPPORTS = ({spec.supports['min']}, {spec.supports['max']})",
        ]
    )
    sections = [
        _HEADER,
        provenance,
        _format_lexicon(spec.lexicon),
        _format_rules(spec.rules),
        _format_parse(spec),
    ]
    return "\n\n".join(sections) + "\n"


def write_module(spec, path):
    """Writes the compiled module to `path`. Kept separate from main() so
    the drift test can write to a temporary file instead of the real one.
    This prevents a failing test from changing the working tree.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_module(spec))


def main():
    spec = load(SPEC_PATH)
    write_module(spec, ARTIFACT_PATH)
    print(f"Wrote {ARTIFACT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
