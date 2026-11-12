"""Tests for compile_spec.py -- the compiler that turns
languages/mizo.yaml into the target package's _mizo.py.

These live in reference/'s suite rather than the package's own, so the
package's tests never need PyYAML (#20). The compiler is developer
tooling; it is not shipped.
"""

import ast
import importlib
import importlib.util
import re
import sys

import pytest

import compile_spec
import generate_vectors
from engine import _IGNORABLE, _WHITESPACE, _eval_tree, _parse_condition, load


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


def test_artifact_is_data_only():
    """Since #75 the compiled module holds no code at all: every name it
    defines is a literal. Conditions were compiled as lambdas until then,
    and a lambda creeping back in would put a second definition of what a
    condition means into the package -- in Python, which no other target
    can read.
    """
    tree = ast.parse(compile_spec.ARTIFACT_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue    # the module docstring
        assert isinstance(node, ast.Assign), ast.dump(node)[:120]
        # literal_eval refuses anything but a literal: a lambda, a call, a
        # name.
        ast.literal_eval(node.value)


def test_compiled_conditions_match_the_engine(spec, artifact, package):
    """The compiler writes each condition as the engine's own data, and the
    package evaluates that data with a second copy of the engine's
    evaluator. This checks the data is the engine's, unchanged, and that the
    two evaluators agree at every (multiplier, remainder) pair a covered
    number gives the rule's scale. Up to 999 that is every input the
    renderer can hand a condition; above it, every multiplier, with the
    remainders the sampled numbers leave.
    """
    # zip() stops at the shorter sequence, so without this the test would
    # quietly check fewer rules if the compiler ever dropped one. The name
    # assert below catches a rule dropped from the middle, because
    # everything after it shifts -- but a dropped last rule would just
    # disappear from the comparison and the suite would still pass.
    assert len(spec.rules) == len(artifact.RULES)
    # The numbers whose (multiplier, remainder) pairs are checked: every
    # covered number, which is every number up to 999 and, above it, every
    # multiplier at every scale plus the remainders the sample leaves.
    covered = generate_vectors.numbers_to_cover(spec)
    for yaml_rule, compiled_rule in zip(spec.rules, artifact.RULES):
        assert yaml_rule["name"] == compiled_rule["name"]
        tree = spec._conditions.get(id(yaml_rule))
        assert compiled_rule["condition"] == tree, yaml_rule["name"]
        if tree is None:
            continue
        pairs = {divmod(n, yaml_rule["scale"]) for n in covered}
        for multiplier, remainder in sorted(pairs):
            variables = {"multiplier": multiplier, "remainder": remainder}
            assert package._render._eval_tree(compiled_rule["condition"], variables) == (
                _eval_tree(tree, variables)
            ), f"rule {yaml_rule['name']} disagrees at {variables}"


# One row per thing condition data can hold (engine._condition_tree), named
# after it, so an evaluator that mishandles one fails the row that says
# which. mizo.yaml uses only `>` and `and` today; these guard the mechanism
# for the next spec, and for the next target's evaluator.
@pytest.mark.parametrize(
    "what, expression",
    [
        ("==", "multiplier == 3"),
        ("!=", "multiplier != 3"),
        (">", "multiplier > 3"),
        (">=", "multiplier >= 3"),
        ("<", "multiplier < 3"),
        ("<=", "multiplier <= 3"),
        ("and", "multiplier > 1 and remainder > 0"),
        ("or", "multiplier == 0 or remainder == 5"),
        ("and inside or", "remainder != 0 or multiplier >= 3 and multiplier <= 7"),
        ("the remainder variable", "remainder > 4"),
        ("a constant on the left", "5 < multiplier"),
        ("a chained comparison", "0 < multiplier < 5"),
    ],
)
def test_both_evaluators_read_condition_data_as_python_reads_the_condition(
    package, what, expression
):
    # The meaning a spec author wrote is Python's reading of the string, so
    # Python is the oracle here: eval() on these fixed test strings, never
    # on a spec. The package gets the data as the compiler writes it --
    # repr(), read back as a literal -- not the engine's object.
    tree = _parse_condition(expression)
    compiled = ast.literal_eval(repr(tree))
    for multiplier in range(11):
        for remainder in range(11):
            variables = {"multiplier": multiplier, "remainder": remainder}
            expected = eval(expression, {"__builtins__": {}}, dict(variables))
            assert _eval_tree(tree, variables) == expected, (what, variables)
            assert package._render._eval_tree(compiled, variables) == expected, (what, variables)


def test_a_chained_comparison_becomes_an_explicit_and():
    """A chained comparison is the case another language gets wrong:
    `0 < d < 5` means `0 < d and d < 5` in Python, and `(0 < d) < 5` in
    JavaScript, which is true for every d. The engine spells the `and` out
    when it converts the condition to data, so no evaluator -- the engine's,
    the package's, or a future target's -- ever sees a chain (#75). No rule
    in mizo.yaml uses one today, so this guards the mechanism rather than
    the current data.
    """
    tree = _parse_condition("0 < multiplier < 5")
    assert tree == (
        "and",
        ("cmp", "<", ("int", 0), ("var", "multiplier")),
        ("cmp", "<", ("var", "multiplier"), ("int", 5)),
    )
    results = [
        _eval_tree(tree, {"multiplier": n, "remainder": 0}) for n in (0, 1, 4, 5)
    ]
    assert results == [False, True, True, False]


@pytest.mark.parametrize(
    "expression",
    [
        "multiplier + 1 == 2",     # arithmetic
        "len(multiplier) == 1",    # a call
        "multiplier.real == 1",    # attribute access
        "ones_digit == 1",         # a name the format no longer defines
        "multiplier == 'zero'",    # a constant that is not an integer
        "multiplier > -1",         # minus applied to 1, not one number
    ],
)
def test_validator_rejects_unsupported_conditions(expression):
    """Only what the allowlist accepts becomes condition data. Anything else
    raises when the spec loads, so it can never reach the compiler or be
    written into a package.
    """
    with pytest.raises(ValueError):
        _parse_condition(expression)


# The grammar has two kinds of position. Where a condition goes -- the
# whole expression, or inside an and/or -- it holds a comparison or an
# and/or; a comparison's operand holds a variable or a non-negative
# integer. Keyed by position, then by what wrongly sits there, so a missing
# cell reads as a missing row. The five forms named on #75 are here, with
# the four that complete the grid. Each is checked against its own message,
# so it is refused for the reason the row says.
WRONG_VALUE_IN_A_POSITION = {
    ("the whole condition", "a bool"): ("True", "Not a condition"),
    ("the whole condition", "a variable"): ("remainder", "Not a condition"),
    ("the whole condition", "an integer"): ("1", "Not a condition"),
    ("inside and/or", "a bool"): ("multiplier > 1 and True", "Not a condition"),
    ("inside and/or", "a variable"): (
        "multiplier > 1 and remainder", "Not a condition"
    ),
    ("inside and/or", "an integer"): ("multiplier > 1 or 0", "Not a condition"),
    ("a comparison operand", "a bool"): (
        "multiplier == True", "True is not a number"
    ),
    ("a comparison operand", "a comparison"): (
        "(multiplier > 1) == 1", "Not a comparison operand"
    ),
    ("a comparison operand", "an and/or"): (
        "(multiplier > 1 and remainder > 0) == 1", "Not a comparison operand"
    ),
}


@pytest.mark.parametrize("position, value", sorted(WRONG_VALUE_IN_A_POSITION))
def test_a_value_python_would_coerce_is_not_a_condition(position, value):
    """Every row is valid Python, which counts True as 1 and any integer as
    true or false, so each one evaluates there -- the eval() call checks
    that, so a row cannot pass by being rejected for a typo. The allowlist
    refuses them anyway (zoramt, #75): no spec uses them, and other
    languages coerce differently, so every target would otherwise have to
    copy Python's rules.
    """
    expression, reason = WRONG_VALUE_IN_A_POSITION[position, value]
    eval(expression, {"__builtins__": {}}, {"multiplier": 2, "remainder": 1})
    with pytest.raises(ValueError, match=reason):
        _parse_condition(expression)


# Python has ten comparison operators, and a condition may use six. These
# are the other four, each in a comparison that is wrong in nothing else.
REFUSED_OPERATORS = {
    "in": "multiplier in 1",
    "not in": "multiplier not in 1",
    "is": "multiplier is 1",
    "is not": "multiplier is not 1",
}


def test_the_refused_operators_are_all_the_others():
    """So the test below cannot miss one: with the six a condition may use,
    written out, the four rows above are every operator Python has."""
    used = {
        type(ast.parse(expression, mode="eval").body.ops[0])
        for expression in REFUSED_OPERATORS.values()
    }
    allowed = {ast.Eq, ast.NotEq, ast.Gt, ast.GtE, ast.Lt, ast.LtE}
    assert len(used) == len(REFUSED_OPERATORS)
    assert used | allowed == set(ast.cmpop.__subclasses__())


# Where a refused operator can stand: alone, or as either link of a chain.
POSITIONS_IN_A_COMPARISON = {
    "alone": "{}",
    "first of a chain": "{} < 5",
    "second of a chain": "0 < {}",
}


@pytest.mark.parametrize("position", sorted(POSITIONS_IN_A_COMPARISON))
@pytest.mark.parametrize("operator", sorted(REFUSED_OPERATORS))
def test_a_comparison_operator_outside_the_six_is_refused(operator, position):
    """Each refused operator in each position, since every link of a chain
    has to be checked, not only the first or the last. The message lists
    the six, as the grammar's other refusals say what is allowed (zoramt,
    #89).
    """
    expression = POSITIONS_IN_A_COMPARISON[position].format(
        REFUSED_OPERATORS[operator]
    )
    with pytest.raises(ValueError) as refused:
        _parse_condition(expression)
    assert str(refused.value) == (
        f"Unsupported comparison operator in {expression!r}. "
        "A comparison uses ==, !=, >, >=, < or <="
    )


# Where an operand can stand: either side of a comparison, or further along
# a chain. Every operand has to be checked.
OPERAND_POSITIONS = {
    "left": "{} == 1",
    "right": "1 == {}",
    "third of a chain": "0 < multiplier < {}",
}


@pytest.mark.parametrize("position", sorted(OPERAND_POSITIONS))
def test_an_unknown_variable_is_refused_naming_the_two_there_are(position):
    """The message names multiplier and remainder, as the grammar's other
    refusals say what is allowed."""
    expression = OPERAND_POSITIONS[position].format("ones_digit")
    with pytest.raises(ValueError) as refused:
        _parse_condition(expression)
    assert str(refused.value) == (
        "Unknown variable in condition: 'ones_digit'. A condition's "
        "variables are multiplier and remainder"
    )


@pytest.mark.parametrize(
    "expression",
    [
        "multiplier == 1",
        "multiplier > 1",
        "multiplier > 1 and remainder > 0",
        "remainder == 0 or remainder == 5",
        "5 < multiplier",
        "0 < multiplier < 5",
        "remainder != 0 or multiplier >= 3 and multiplier <= 7",
        "(multiplier > 1 or remainder > 0) and remainder < 9",
    ],
)
def test_validator_accepts_the_shapes_the_engine_supports(expression):
    _parse_condition(expression)


# The tests below check the rest of the artifact against the spec. The
# drift test only proves the checked-in file matches what the compiler
# produces today, so it cannot notice the compiler itself losing
# something -- both sides would change together. These compare the
# artifact with the spec and the engine instead.


def test_compiled_rules_match_the_spec(spec, artifact):
    """Rule count, names, and everything rule selection reads besides the
    condition: the scale, the fixed multiplier, whether the rule is emitted
    or whole-input-only, and whether it stacks. Nothing else checks those
    field by field.
    """
    assert len(artifact.RULES) == len(spec.rules)
    for yaml_rule, compiled_rule in zip(spec.rules, artifact.RULES):
        assert compiled_rule["name"] == yaml_rule["name"]
        assert compiled_rule["scale"] == yaml_rule["scale"]
        assert compiled_rule["multiplier"] == yaml_rule.get("multiplier")
        assert compiled_rule["emit"] == (yaml_rule.get("emit") != "never")
        assert compiled_rule["whole_only"] == (yaml_rule.get("scope") == "whole")
        assert compiled_rule["stacks"] == (id(yaml_rule) in spec._stacking_rules)
    # And which rules those are, written out rather than asked of the engine
    # the compiler reads it from: every rule from 10^5 up (#27 rule 6, the
    # floor from Q-K), and none below it.
    assert {r["name"] for r in artifact.RULES if r["stacks"]} == {
        "hundred_thousands", "millions", "ten_millions", "hundred_millions",
        "billions", "ten_billions", "hundred_billions", "trillions",
    }


def test_compiled_connector_matches_the_spec(spec, artifact):
    """grammar.connector decides where "leh" goes in every number from 100
    up, and the renderer reads it from nowhere else."""
    declared = spec.connector
    assert declared is not None
    assert artifact.CONNECTOR == {"word": declared["word"], "min": declared["min"]}


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
    Spec._find_rule, Spec._render_rule and Spec._with_connector.

    This is deliberately the smallest thing that can read the artifact,
    not a copy of _render.py. Its job is to prove the compiled data still
    means what the spec meant, independently of the package's renderer --
    if both read the artifact the same wrong way, the package's own
    conformance tests would not notice, and this would.
    """
    def find(n):
        scales = sorted({r["scale"] for r in artifact.RULES if r["emit"]}, reverse=True)
        scale = next(s for s in scales if s <= max(n, 1))
        multiplier, remainder = divmod(n, scale)
        for rule in artifact.RULES:
            if rule["scale"] != scale or not rule["emit"]:
                continue
            if rule["multiplier"] not in (None, multiplier):
                continue
            condition = rule["condition"]
            if condition is None or _eval_tree(
                condition, {"multiplier": multiplier, "remainder": remainder}
            ):
                return rule
        raise AssertionError(f"no compiled rule matches n={n}")

    def render(rule, n):
        multiplier, remainder = divmod(n, rule["scale"])
        values = {"multiplier": multiplier, "remainder": remainder}
        out, starts = [], []

        def walk(items):
            for item in items:
                if isinstance(item, str):
                    out.append(item)
                elif item[0] == "lex":
                    _, table, key, field = item
                    out.append(artifact.LEXICON[table][values.get(key, key)][field])
                elif item[0] == "remainder":
                    start = len("".join(out))
                    text, inner = render(find(remainder), remainder)
                    starts.append(start)
                    starts.extend(start + i for i in inner)
                    out.append(text)
                elif remainder:
                    walk(item[1])

        walk(rule["output"])
        return "".join(out), starts

    text, starts = render(find(n), n)
    connector = artifact.CONNECTOR
    if connector and n >= connector["min"] and starts:
        text = text[:starts[-1]] + connector["word"] + " " + text[starts[-1]:]
    return text


def test_compiled_output_matches_the_engine(spec, artifact):
    """The end-to-end check: rendering from the artifact agrees with the
    engine at every covered number -- all of 0-999, and one of each shape
    above it (generate_vectors.numbers_to_cover).

    This is the one that would catch a compiler bug the piecewise tests
    miss, because it exercises rule selection, placeholder keys, field
    names, literal text, segments and the connector together, against the
    oracle.
    """
    for n in generate_vectors.numbers_to_cover(spec):
        assert _render_from_artifact(artifact, n) == spec.number_to_text(n), (
            f"compiled output disagrees with the engine at n={n}"
        )


def _unparse_template(items):
    """Rebuilds a template string from the items _parse_template produced."""
    pieces = []
    for item in items:
        if isinstance(item, str):
            pieces.append(item)
        elif item[0] == "lex":
            _, table, key, field = item
            pieces.append(f"{{{table}[{key}].{field}}}")
        elif item[0] == "remainder":
            pieces.append("{remainder}")
        else:
            pieces.append(f"[{_unparse_template(item[1])}]")
    return "".join(pieces)


def test_compiled_templates_round_trip_to_the_spec_text(spec, artifact):
    """Every compiled template rebuilds into the template the spec wrote.

    _parse_template splits a template into literal text, placeholders and
    segments, and a split that dropped or reordered a piece would still look
    like a plausible template. Rebuilding is the cheap way to prove nothing
    was lost -- including in an `emit: never` rule, which the output check
    above never renders.
    """
    for yaml_rule, compiled_rule in zip(spec.rules, artifact.RULES):
        assert _unparse_template(compiled_rule["output"]) == yaml_rule["output"]


def test_compiled_parse_config_matches_the_spec(spec, artifact):
    """The parse section is normalised at compile time so the renderer can
    compare plain strings. That only holds if the normalisation really
    happened, and if nothing was dropped on the way through.
    """
    config = spec.parse_config
    parse = artifact.PARSE
    assert parse["case_insensitive"] == config.get("case_insensitive", False)
    assert parse["strip_diacritics"] == config.get("strip_diacritics", False)
    assert parse["word_separators"] == tuple(config.get("word_separators", []))
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
    # and its aliases (nuaih -> nuai, maktaduaih -> maktaduai) are all
    # already lowercase and diacritic-free, so normalising them changes
    # nothing -- removing the compiler's normalisation step still produces a
    # byte-identical artifact and this still passes. The assert holds the
    # invariant for the first value that is not already normalised, the way
    # en.yaml holds the engine's rules for a spec that is not Mizo.
    for connector in parse["connectors"]:
        assert spec._normalize_word(connector) == connector
    for variant, canonical in parse["aliases"].items():
        assert spec._normalize_word(variant) == variant
        assert spec._normalize_word(canonical) == canonical


def test_compiled_text_lists_match_the_engine(artifact):
    """WHITESPACE and IGNORABLE are the engine's own lists, shipped whole.

    Until #75 _render.py kept a second copy of each, and the ignorable one
    had nothing outside itself to be checked against, so a one-sided edit
    passed both suites (zoramt, #56). Now there is one copy, the package
    reads it from _mizo.py, and what is left to check here is that the
    compiler shipped all of it. Whether the list holds the right characters
    is test_engine.py's job: test_the_ignorable_list_is_the_one_decided_on_46
    states them. IGNORABLE is compared as the translate table the package
    builds from it, so this is not the compiler's own expression run a
    second time.
    """
    assert artifact.WHITESPACE == _WHITESPACE
    assert {ord(ch): None for ch in artifact.IGNORABLE} == _IGNORABLE
    assert len(set(artifact.WHITESPACE)) == len(artifact.WHITESPACE) == 25
    assert len(set(artifact.IGNORABLE)) == len(artifact.IGNORABLE) == 6


def test_compiled_fold_is_the_engines(artifact, spec):
    """FOLD is the engine's fold table for the spec, shipped whole (#75).

    Compared as the translate table the package builds from it, as
    IGNORABLE is above. Which characters belong in it is test_engine.py's
    job (test_the_mizo_fold_table_is_its_letters_and_the_marks_inside_them).
    """
    assert {ord(ch): folded for ch, folded in artifact.FOLD.items()} == spec._fold
    assert len(artifact.FOLD) == 439


def test_the_compiled_fold_is_written_in_ascii(spec):
    # Its marks are combining characters. Written raw, as repr() would, each
    # would be invisible in a diff or drawn over the quote before it, so a
    # reviewer could not see what the table holds.
    fold = compile_spec.compile_data(spec)["FOLD"]
    assert compile_spec._python_fold(fold).isascii()


def test_package_version_is_stated_once():
    """pyproject.toml and __init__.py both carry the package version, and
    nothing stops one being bumped without the other.

    Read as text rather than imported: tomllib is 3.11+ and the package
    floor is 3.10, and __init__.py will grow real imports once it exports
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


@pytest.fixture(scope="module")
def package():
    """The package's own public API, imported from its source tree.

    Everything else in this file reads the artifact or the package source as
    data. This one needs the package's own code running, and the package is
    importable from its src/ directory with no install step -- it depends on
    nothing, which is the point of compiling the spec (#20).
    """
    source = str(compile_spec.REPO_ROOT / "packages" / "python" / "src")
    sys.path.insert(0, source)
    try:
        yield importlib.import_module("numberwords")
    finally:
        sys.path.remove(source)
