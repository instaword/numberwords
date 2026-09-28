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
template parser and the variable names avoids keeping duplicate copies that
could drift apart.
"""

import ast
from pathlib import Path

from engine import (
    _VARIABLE_NAMES,
    _parse_template,
    _validate_condition_node,
    load,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "languages" / "mizo.yaml"
ARTIFACT_PATH = (
    REPO_ROOT / "packages" / "python" / "src" / "numberwords" / "_mizo.py"
)

# The variable names a placeholder key or a condition may use. The engine
# builds this set for its own load-time validation (#37); take that one
# rather than building a second, which is the duplication this issue is
# about in miniature.
VARIABLE_NAMES = _VARIABLE_NAMES

_HEADER = '''"""Compiled from languages/mizo.yaml by reference/compile_spec.py.

Do not edit by hand. Regenerate with `python compile_spec.py` from
reference/ and commit the result.
"""'''


# Templates are compiled with the engine's own parser, engine._parse_template,
# into the item tuples it documents: a literal string, ("lex", table, key,
# field), ("remainder",) or ("optional", items). The renderer walks those
# directly, so it needs neither a regex nor a bracket scanner, and there is
# exactly one definition of what a template means. Before #65 the compiler
# split templates with a regex of its own, which was fine while templates
# were flat and would have been a second parser to keep in step once they
# could hold a segment.


# Compiling conditions means there are two places that define how a
# condition works: engine._eval_node and the compiled lambda below.
# What keeps them in sync is vectors/mizo.json. It covers every number
# from 0 to 999, and so every (multiplier, remainder) pair a condition is
# evaluated at while rendering one; above 999 it keeps every multiplier at
# every scale (generate_vectors.numbers_to_cover). test_compile_spec.py
# also evaluates both directly at every pair those numbers give each rule.


# The allowlist moved into engine.py in #37, where it now also runs over the
# whole tree when a spec is loaded. The compiler keeps validating before it
# emits -- docs/architecture.md: "Never emit an unvalidated string" -- it just
# stops being the only place that checks, and stops being a second
# implementation that could drift from the oracle's.
#
# Kept under the local name because _compile_condition and
# test_compile_spec.py both call it.
_validate_condition = _validate_condition_node


class _NameToLookup(ast.NodeTransformer):
    """Rewrites a variable name like `multiplier` into
    `variables['multiplier']`, so the generated lambda reads values
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
    "always applies", the same way engine.Spec._rule_applies does.
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
    """Each rule as a dict of plain literals.

    `emit` and `whole_only` are booleans rather than the spec's strings
    ("never", "whole"): the renderer asks yes-or-no questions of them, and a
    bool cannot be misspelt in a comparison the way a string can.
    """
    lines = ["RULES = ("]
    for rule in rules:
        lines.append("    {")
        lines.append(f"        'name': {rule['name']!r},")
        lines.append(f"        'scale': {rule['scale']!r},")
        lines.append(f"        'multiplier': {rule.get('multiplier')!r},")
        lines.append(
            f"        'condition': "
            f"{_format_condition(rule.get('condition'))},"
        )
        lines.append(f"        'output': {_parse_template(rule['output'])!r},")
        lines.append(f"        'emit': {rule.get('emit') != 'never'!r},")
        lines.append(f"        'whole_only': {rule.get('scope') == 'whole'!r},")
        lines.append("    },")
    lines.append(")")
    return "\n".join(lines)


def _format_connector(spec):
    """grammar.connector, or None for a language that writes none. Only the
    two values the renderer reads: `placement` has one legal value, and the
    schema already refuses any other."""
    connector = spec.connector
    if connector is None:
        return "CONNECTOR = None"
    return (
        f"CONNECTOR = {{'word': {connector['word']!r}, "
        f"'min': {connector['min']!r}}}"
    )


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
        # Default is empty, not [' ']: since #46 whitespace is a separator
        # in every language and the renderer applies it, so a spec that
        # declares nothing here has no *extra* separators rather than one.
        f"    'word_separators': "
        f"{tuple(config.get('word_separators', []))!r},",
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
        _format_connector(spec),
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
