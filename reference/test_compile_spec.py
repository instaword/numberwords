"""Tests for compile_spec.py -- the compiler that turns
languages/mizo.yaml into the target package's _mizo.py.

These live in reference/'s suite rather than the package's own, so the
package's tests never need PyYAML (#20). The compiler is developer
tooling; it is not shipped.
"""

import ast
import importlib.util
import re

import pytest

import compile_spec
from engine import _eval_condition, _positional_variables, load


@pytest.fixture(scope="module")
def spec():
    return load(compile_spec.SPEC_PATH)


@pytest.fixture(scope="module")
def artifact():
    """Imports the checked-in _mizo.py from its path. It belongs to the
    package, not to reference/, so it is not importable by name from here.
    """
    module_spec = importlib.util.spec_from_file_location(
        "_mizo", compile_spec.ARTIFACT_PATH
    )
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def test_checked_in_artifact_is_up_to_date(spec, tmp_path):
    """The same drift problem the conformance vectors have: _mizo.py is a
    snapshot, so a spec edit that was never recompiled would go unnoticed.

    This compiles to a temp file rather than the real path. A failing test
    must not rewrite the artifact it is meant to be checking -- otherwise
    running the suite would quietly fix the very thing that should fail.
    """
    generated = tmp_path / "_mizo.py"
    compile_spec.write_module(spec, generated)
    assert generated.read_text(encoding="utf-8") == (
        compile_spec.ARTIFACT_PATH.read_text(encoding="utf-8")
    ), "_mizo.py is stale -- run `python compile_spec.py` and commit it"


def test_compiling_twice_gives_the_same_text(spec):
    """The drift test above is only meaningful if the compiler is
    deterministic. Anything that varied run to run (dictionary ordering,
    a timestamp) would make it fail at random.
    """
    assert compile_spec.render_module(spec) == compile_spec.render_module(spec)


def test_artifact_imports_nothing(artifact):
    """The point of compiling is that the package needs neither PyYAML nor
    ast at runtime (#20). An import appearing in the generated module would
    mean work leaked back into it.
    """
    tree = ast.parse(compile_spec.ARTIFACT_PATH.read_text(encoding="utf-8"))
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert imports == []


def test_compiled_conditions_match_the_engine(spec, artifact):
    """The compiled lambda and engine._eval_condition are two
    implementations of the same condition, which is the risk that made
    ast.unparse the right way to emit them. This checks they agree at every
    input in the supported range.
    """
    low, high = artifact.SUPPORTS
    # zip() stops at the shorter sequence, so without this the test would
    # quietly check fewer rules if the compiler ever dropped one. The name
    # assert below catches a rule dropped from the middle, because
    # everything after it shifts -- but a dropped last rule would just
    # disappear from the comparison and the suite would still pass.
    assert len(spec.rules) == len(artifact.RULES)
    for yaml_rule, compiled_rule in zip(spec.rules, artifact.RULES):
        assert yaml_rule["name"] == compiled_rule["name"]
        condition = yaml_rule.get("condition")
        if condition is None:
            assert compiled_rule["condition"] is None
            continue
        for n in range(low, high + 1):
            variables = _positional_variables(n)
            assert bool(compiled_rule["condition"](variables)) == bool(
                _eval_condition(condition, variables)
            ), f"rule {yaml_rule['name']} disagrees at n={n}"


def test_chained_comparison_keeps_python_semantics():
    """A chained comparison is the case an emitter that pasted strings
    together would get wrong: `0 < d < 5` means `0 < d and d < 5`, not
    `(0 < d) < 5`, which would evaluate a bool against 5 and be true for
    d = 0. No rule in mizo.yaml uses one today, so this guards the
    mechanism rather than the current data.
    """
    condition = eval(compile_spec._compile_condition("0 < ones_digit < 5"))
    results = [
        condition({"ones_digit": n, "tens_digit": 0}) for n in (0, 1, 4, 5)
    ]
    assert results == [False, True, True, False]


@pytest.mark.parametrize(
    "expression",
    [
        "ones_digit + 1 == 2",     # arithmetic
        "len(ones_digit) == 1",    # a call
        "ones_digit.real == 1",    # attribute access
        "not_a_variable == 1",     # a name the spec never defines
        "ones_digit == 'zero'",    # a constant that is not an integer
    ],
)
def test_validator_rejects_unsupported_conditions(expression):
    """The compiler only accepts what engine._eval_node accepts. Anything
    else raises here, at build time, instead of being written into the
    package as code.
    """
    with pytest.raises(ValueError):
        compile_spec._compile_condition(expression)


@pytest.mark.parametrize(
    "expression",
    [
        "ones_digit == 0",
        "ones_digit > 0",
        "ones_digit == 0 and tens_digit > 1",
        "ones_digit == 0 or ones_digit == 5",
    ],
)
def test_validator_accepts_the_shapes_the_engine_supports(expression):
    compile_spec._compile_condition(expression)


# The tests below check the rest of the artifact against the spec. The
# drift test only proves the checked-in file matches what the compiler
# produces today, so it cannot notice the compiler itself losing
# something -- both sides would change together. These compare the
# artifact with the spec and the engine instead.


def test_compiled_rules_match_the_spec(spec, artifact):
    """Rule count, names and ranges. Rule selection depends on the range
    as much as on the condition, and nothing else checks it.
    """
    assert len(artifact.RULES) == len(spec.rules)
    for yaml_rule, compiled_rule in zip(spec.rules, artifact.RULES):
        assert compiled_rule["name"] == yaml_rule["name"]
        assert compiled_rule["range"] == tuple(yaml_rule["range"])


def test_compiled_lexicon_matches_the_spec(spec, artifact):
    """The lexicon holds the actual numeral words. A dropped table, entry
    or field would change the output of every number that uses it, so
    compare the whole structure rather than sampling it.
    """
    assert artifact.LEXICON == spec.lexicon


def test_compiled_provenance_matches_the_spec(spec, artifact):
    """The header constants say which spec the artifact came from. If
    SUPPORTS drifted from the spec, the package would accept or reject
    numbers the engine does not.
    """
    meta = spec._data["meta"]
    assert artifact.LANGUAGE == meta["language"]
    assert artifact.CODE == meta["code"]
    assert artifact.SPEC_VERSION == str(meta["version"])
    assert artifact.SUPPORTS == (spec.supports["min"], spec.supports["max"])


def _render_from_artifact(artifact, n):
    """Renders `n` using only the compiled artifact, mirroring
    engine._find_rule and engine._render.

    This is deliberately the smallest thing that can read the artifact,
    not a draft of _render.py. Its job is to prove the compiled data
    still means what the spec meant; the real renderer lands with the
    public API and brings the parse side with it.
    """
    variables = _positional_variables(n)
    for rule in artifact.RULES:
        low, high = rule["range"]
        if not (low <= n <= high):
            continue
        condition = rule["condition"]
        if condition is not None and not condition(variables):
            continue
        rendered = []
        for part in rule["output"]:
            if isinstance(part, str):
                rendered.append(part)
                continue
            table, key, field = part
            if isinstance(key, str):
                key = variables[key]
            rendered.append(artifact.LEXICON[table][key][field])
        return "".join(rendered)
    raise AssertionError(f"no compiled rule matches n={n}")


def test_compiled_output_matches_the_engine(spec, artifact):
    """The end-to-end check: rendering from the artifact agrees with the
    engine at every supported number.

    This is the one that would catch a compiler bug the piecewise tests
    miss, because it exercises rule selection, placeholder keys, field
    names and literal text together, against the oracle.
    """
    low, high = artifact.SUPPORTS
    for n in range(low, high + 1):
        assert _render_from_artifact(artifact, n) == spec.number_to_text(n), (
            f"compiled output disagrees with the engine at n={n}"
        )


def _unparse_template(parts):
    """Rebuilds a template string from the parts _parse_template produced."""
    pieces = []
    for part in parts:
        if isinstance(part, str):
            pieces.append(part)
        else:
            table, key, field = part
            pieces.append(f"{{{table}[{key}].{field}}}")
    return "".join(pieces)


def test_compiled_templates_round_trip_to_the_spec_text(spec, artifact):
    """Every compiled template rebuilds into the template the spec wrote.

    _parse_template splits a template into literal text and placeholders,
    and a split that dropped or reordered a piece would still look like a
    plausible template. Rebuilding is the cheap way to prove nothing was
    lost. This is the only check that covers parse_aliases at all -- they
    are used for text -> number, which needs the parse side of the
    renderer, so nothing else here can reach them yet.
    """
    for yaml_rule, compiled_rule in zip(spec.rules, artifact.RULES):
        assert _unparse_template(compiled_rule["output"]) == yaml_rule["output"]
        aliases = yaml_rule.get("parse_aliases", [])
        assert len(compiled_rule["parse_aliases"]) == len(aliases)
        for compiled_alias, yaml_alias in zip(
            compiled_rule["parse_aliases"], aliases
        ):
            assert _unparse_template(compiled_alias) == yaml_alias


def test_compiled_parse_config_matches_the_spec(spec, artifact):
    """The parse section is normalised at compile time so the renderer can
    compare plain strings. That only holds if the normalisation really
    happened, and if nothing was dropped on the way through.
    """
    config = spec.parse_config
    parse = artifact.PARSE
    assert parse["case_insensitive"] == config.get("case_insensitive", False)
    assert parse["strip_diacritics"] == config.get("strip_diacritics", False)
    assert parse["word_separators"] == tuple(
        config.get("word_separators", [" "])
    )
    # accepted_forms keeps its tables and the order of each field list --
    # order decides which form a target tries first. The lists become
    # tuples on the way in, so compare contents rather than types.
    declared = config.get("accepted_forms", {})
    assert set(parse["accepted_forms"]) == set(declared)
    for table, fields in declared.items():
        assert isinstance(parse["accepted_forms"][table], tuple)
        assert list(parse["accepted_forms"][table]) == list(fields)

    # Nothing dropped: normalising can collapse two spellings into one, so
    # compare counts against the spec before comparing contents.
    assert len(parse["connectors"]) == len(config.get("connectors", []))
    assert len(parse["aliases"]) == len(config.get("aliases", {}))
    assert set(parse["connectors"]) == {
        spec._normalize_word(c) for c in config.get("connectors", [])
    }

    # Already normalised, so the renderer never has to do it again. If a
    # value still changes under normalisation, the compiler missed it and
    # the renderer would silently fail to match that word.
    #
    # This cannot fail on today's data. Mizo's only connector is "leh",
    # which is already lowercase and diacritic-free, so normalising it
    # changes nothing -- removing the compiler's normalisation step still
    # produces a byte-identical artifact and this still passes. The
    # aliases table is empty, so that loop does not run at all. The
    # assert holds the invariant for the first value that is not already
    # normalised, the way en.yaml holds the engine's rules for a spec
    # that is not Mizo.
    for connector in parse["connectors"]:
        assert spec._normalize_word(connector) == connector
    for variant, canonical in parse["aliases"].items():
        assert spec._normalize_word(variant) == variant
        assert spec._normalize_word(canonical) == canonical


def test_package_version_is_stated_once():
    """pyproject.toml and __init__.py both carry the package version, and
    nothing stops one being bumped without the other.

    Read as text rather than imported: tomllib is 3.11+ and the package
    floor is 3.9, and __init__.py will grow real imports once it exports
    an API. Single-sourcing this properly (hatch's dynamic version) is
    worth doing when the version actually moves.
    """
    package_root = compile_spec.REPO_ROOT / "packages" / "python"
    pyproject = (package_root / "pyproject.toml").read_text(encoding="utf-8")
    init = (
        package_root / "src" / "numberwords" / "__init__.py"
    ).read_text(encoding="utf-8")

    declared = re.findall(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    exported = re.findall(r'^__version__ = "([^"]+)"', init, re.MULTILINE)
    assert len(declared) == 1, "expected exactly one version in pyproject.toml"
    assert len(exported) == 1, "expected exactly one __version__ in __init__.py"
    assert declared[0] == exported[0]
