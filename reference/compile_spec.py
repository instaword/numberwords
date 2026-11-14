"""Compiles languages/mizo.yaml into each target package's compiled file:
packages/python's _mizo.py and packages/npm's _mizo.js.

A package should not depend on a YAML parser or read the spec at import
time (#20). Instead, the spec is compiled here, once, into plain data
(compile_data), and each target's writer spells that data out in its own
language (#75). This is similar to generate_vectors.py -- it uses the same
PyYAML dependency and is run the same way.

Run from inside reference/:

    python compile_spec.py

Regenerate and commit both generated files whenever languages/mizo.yaml
changes. test_compile_spec.py fails if either checked-in copy is out of
date.

This module intentionally uses a few private names from engine.py. The
compiler is part of the same reference implementation, so sharing the
template parser, the condition data, the variable names and the text lists
avoids keeping duplicate copies that could drift apart.
"""

import json
from pathlib import Path

from engine import (
    _IGNORABLE,
    _VARIABLE_NAMES,
    _WHITESPACE,
    _parse_template,
    load,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "languages" / "mizo.yaml"
ARTIFACT_PATH = (
    REPO_ROOT / "packages" / "python" / "src" / "numberwords" / "_mizo.py"
)
JS_ARTIFACT_PATH = REPO_ROOT / "packages" / "npm" / "_mizo.js"

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


# Conditions are compiled as the engine already holds them: as data
# (engine._parse_condition), checked against the allowlist when the spec was
# loaded -- a Spec cannot hold a condition that was not. Nothing is written
# as code, so _mizo.py is plain literals from end to end, and there is one
# definition of what a condition means: the data, which the engine's
# evaluator and the package's both read (#75). Until #75 each condition was
# emitted as a lambda through ast.unparse, the one place the compiler wrote
# code rather than data.


def compile_data(spec) -> dict:
    """Everything the compiled module holds, as plain data, decided once.

    A target's writer only spells this out in its own language --
    _write_python below for packages/python, _write_js for packages/npm --
    so every decision about *what* a target ships is made here, and two
    targets cannot come to ship different things (#75).

    `emit` and `whole_only` are booleans rather than the spec's strings
    ("never", "whole"): the renderer asks yes-or-no questions of them, and a
    bool cannot be misspelt in a comparison the way a string can.

    `stacks` is grammar.stacking resolved per rule, by the engine: whether
    this rule's multiplier slot also takes a whole numeral on input. Shipped
    as the answer rather than as `accepted_from` plus the test for a
    multiplier word, so the package holds no second copy of that test.

    The connector is grammar.connector, or None for a language that writes
    none, cut to the two values the renderer reads: `placement` has one legal
    value, and the schema already refuses any other.

    The parse config has its connectors and aliases already normalised, so
    the renderer only compares plain strings instead of normalising them on
    every call. `word_separators` defaults to empty, not [' ']: since #46
    whitespace is a separator in every language and the renderer applies it,
    so a spec that declares nothing has no *extra* separators rather than
    one. Lists become tuples: the renderer only reads them, and a literal
    tuple cannot be mutated by accident once it ships inside the package.

    WHITESPACE and IGNORABLE are not read from the spec: since #46 they are
    properties of text that every language shares, and the engine states
    them once. They ship here so that no target keeps its own copy (#75),
    and beside PARSE rather than inside it, which holds what the spec says.
    Both are strings of the characters themselves; IGNORABLE is the
    engine's translate table turned back into one.

    FOLD is what case_insensitive and strip_diacritics mean for this spec:
    each character that folds, and what it folds to ("" for a mark),
    built by the engine from the spec's words (#75, engine._fold_table).
    A target applies it after removing IGNORABLE and applies nothing else:
    no lowercasing and no Unicode normalisation of its own, which is the
    point of shipping it. The two flags stay in PARSE because they are what
    the spec says, but no target needs to read them.
    """
    meta = spec._data["meta"]
    config = spec.parse_config
    connector = spec.connector
    return {
        "LANGUAGE": meta["language"],
        "CODE": meta["code"],
        "SPEC_VERSION": str(meta["version"]),
        "SUPPORTS": (spec.supports["min"], spec.supports["max"]),
        "LEXICON": spec.lexicon,
        "RULES": tuple(
            {
                "name": rule["name"],
                "scale": rule["scale"],
                "multiplier": rule.get("multiplier"),
                "condition": spec._conditions.get(id(rule)),
                "output": _parse_template(rule["output"]),
                "emit": rule.get("emit") != "never",
                "whole_only": rule.get("scope") == "whole",
                "stacks": id(rule) in spec._stacking_rules,
            }
            for rule in spec.rules
        ),
        "CONNECTOR": (
            None if connector is None
            else {"word": connector["word"], "min": connector["min"]}
        ),
        "PARSE": {
            "case_insensitive": config.get("case_insensitive", False),
            "strip_diacritics": config.get("strip_diacritics", False),
            "word_separators": tuple(config.get("word_separators", [])),
            "accepted_forms": {
                table: tuple(fields)
                for table, fields
                in sorted(config.get("accepted_forms", {}).items())
            },
            "connectors": tuple(sorted(
                spec._normalize_word(c) for c in config.get("connectors", [])
            )),
            "aliases": {
                spec._normalize_word(variant): spec._normalize_word(canonical)
                for variant, canonical
                in sorted(config.get("aliases", {}).items())
            },
        },
        "WHITESPACE": _WHITESPACE,
        "IGNORABLE": "".join(chr(code) for code in _IGNORABLE),
        "FOLD": {
            chr(code): folded for code, folded in sorted(spec._fold.items())
        },
    }


def _python_lexicon(lexicon):
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


def _python_rules(rules):
    lines = ["RULES = ("]
    for rule in rules:
        lines.append("    {")
        lines.extend(
            f"        {field!r}: {value!r}," for field, value in rule.items()
        )
        lines.append("    },")
    lines.append(")")
    return "\n".join(lines)


def _python_parse(parse):
    lines = ["PARSE = {"]
    lines.extend(f"    {field!r}: {value!r}," for field, value in parse.items())
    lines.append("}")
    return "\n".join(lines)


def _python_fold(fold):
    # ascii(), not repr(): most entries are accented letters, and the marks
    # are combining characters, which repr() writes raw -- invisible in a
    # diff, or drawn on top of the quote before them.
    lines = ["FOLD = {"]
    lines.extend(
        f"    {ascii(ch)}: {ascii(folded)}," for ch, folded in fold.items()
    )
    lines.append("}")
    return "\n".join(lines)


def _write_python(data) -> str:
    """compile_data's output as the source text of a Python module."""
    provenance = "\n".join(
        f"{name} = {data[name]!r}"
        for name in ("LANGUAGE", "CODE", "SPEC_VERSION", "SUPPORTS")
    )
    sections = [
        _HEADER,
        provenance,
        _python_lexicon(data["LEXICON"]),
        _python_rules(data["RULES"]),
        f"CONNECTOR = {data['CONNECTOR']!r}",
        _python_parse(data["PARSE"]),
        "\n".join(
            f"{name} = {data[name]!r}" for name in ("WHITESPACE", "IGNORABLE")
        ),
        _python_fold(data["FOLD"]),
    ]
    return "\n\n".join(sections) + "\n"


_JS_HEADER = """\
// Compiled from languages/mizo.yaml by reference/compile_spec.py.
//
// Do not edit by hand. Regenerate with `python compile_spec.py` from
// reference/ and commit the result."""

# The names a compiled file holds, in the order _write_python writes them.
# _write_js follows it, and test_compile_spec.py checks the two files agree.
_NAMES = (
    "LANGUAGE", "CODE", "SPEC_VERSION", "SUPPORTS", "LEXICON", "RULES",
    "CONNECTOR", "PARSE", "WHITESPACE", "IGNORABLE", "FOLD",
)

# Written with \u escapes rather than as the characters themselves, as
# _python_fold does for FOLD: the whitespace and ignorable characters and the
# fold table's combining marks are invisible in a diff, or drawn on top of
# the quote before them.
_JS_ESCAPED = frozenset({"WHITESPACE", "IGNORABLE", "FOLD"})

# Every integer a JavaScript number holds exactly: all of them up to 2^53.
_JS_EXACT = 2 ** 53

# How deep a name's value is laid out one item per line before the rest is
# written on one line, so that, as in _mizo.py, a lexicon entry, a rule's
# field, a parse setting or a fold entry is one line of a diff. Names not
# listed are one line.
_JS_LINES = {"LEXICON": 2, "RULES": 2, "PARSE": 1, "FOLD": 1}


def _js_literal(value, ascii_only: bool, lines_to: int) -> str:
    """`value` as JSON, one item per line down to depth `lines_to` and on
    one line below it. Whatever the layout, it parses as the same JSON."""
    def one_line(v):
        return json.dumps(v, ensure_ascii=ascii_only, separators=(", ", ": "))

    def layout(v, depth):
        if depth >= lines_to or not isinstance(v, (dict, list, tuple)) or not v:
            return one_line(v)
        pad, close = "  " * (depth + 1), "  " * depth
        if isinstance(v, dict):
            items = [
                f"{pad}{one_line(k)}: {layout(x, depth + 1)}" for k, x in v.items()
            ]
            return "{\n" + ",\n".join(items) + "\n" + close + "}"
        items = [f"{pad}{layout(x, depth + 1)}" for x in v]
        return "[\n" + ",\n".join(items) + "\n" + close + "]"

    return layout(value, 0)


def _js_values(data) -> dict:
    """compile_data's output, shaped for JSON: each lexicon table as
    [key, entry] pairs, sorted by key, since a JavaScript object's keys are
    strings, and an interpreter that read a key from one would hold "5"
    where it needs 5 (docs/interpreter-contract.md, "Runtime traps").
    Tuples become arrays, as JSON writes them anyway."""
    values = dict(data)
    values["LEXICON"] = {
        table: [
            [key, {field: entry[field] for field in sorted(entry)}]
            for key, entry in sorted(data["LEXICON"][table].items())
        ]
        for table in sorted(data["LEXICON"])
    }
    return values


def _check_js_integers(value):
    """Refuse any integer, anywhere in `value`, that a JavaScript number
    would not hold exactly: it holds every integer up to 2^53, and not
    all of those above."""
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        if abs(value) > _JS_EXACT:
            raise ValueError(f"the compiled data: {value} is above 2^53, which "
                             f"a JavaScript number does not hold exactly")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _check_js_integers(key)
            _check_js_integers(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _check_js_integers(item)


def _write_js(data) -> str:
    """compile_data's output as the source text of an ES module: one
    `export const` per name, each value a JSON literal. So _mizo.js is plain
    data, as _mizo.py is, and no code is written (#75).

    No reading ever holds more than max + 1 (docs/interpreter-contract.md,
    "Arithmetic"), so that has to be exact too, beside every integer the
    file holds. A spec that outgrows the type fails here, when the file is
    built, rather than in a caller's hands.
    """
    _check_js_integers(data)
    high = data["SUPPORTS"][1]
    if high + 1 > _JS_EXACT:
        raise ValueError(
            f"supports.max is {high}: max + 1 is above 2^53, which a "
            f"JavaScript number does not hold exactly"
        )
    values = _js_values(data)
    sections = [_JS_HEADER]
    for name in _NAMES:
        text = _js_literal(values[name], name in _JS_ESCAPED, _JS_LINES.get(name, 0))
        sections.append(f"export const {name} = {text};")
    return "\n\n".join(sections) + "\n"


def render_module(spec):
    """Returns the full source text of the compiled Python module."""
    return _write_python(compile_data(spec))


def render_js_module(spec):
    """Returns the full source text of the compiled JavaScript module."""
    return _write_js(compile_data(spec))


def write_module(spec, path, render=render_module):
    """Writes a compiled module to `path`, the Python one unless `render`
    says otherwise. Kept separate from main() so the drift tests can write
    to a temporary file instead of the real one. This prevents a failing
    test from changing the working tree.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(spec))


def main():
    spec = load(SPEC_PATH)
    write_module(spec, ARTIFACT_PATH)
    print(f"Wrote {ARTIFACT_PATH.relative_to(REPO_ROOT)}")
    write_module(spec, JS_ARTIFACT_PATH, render_js_module)
    print(f"Wrote {JS_ARTIFACT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
