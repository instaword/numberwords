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
template parser, the condition data and the variable names avoids keeping
duplicate copies that could drift apart.
"""

from pathlib import Path

from engine import (
    _VARIABLE_NAMES,
    _parse_template,
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

    A target's writer only spells this out in its own language -- _write_python
    below for packages/python -- so every decision about *what* a target
    ships is made here, and two targets cannot come to ship different things
    (#75).

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
    ]
    return "\n\n".join(sections) + "\n"


def render_module(spec):
    """Returns the full source text of the compiled module."""
    return _write_python(compile_data(spec))


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
