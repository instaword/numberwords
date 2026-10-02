"""Tests for compile_spec.py -- the compiler that turns
languages/mizo.yaml into the target package's _mizo.py.

These live in reference/'s suite rather than the package's own, so the
package's tests never need PyYAML (#20). The compiler is developer
tooling; it is not shipped.
"""

import ast
import importlib
import importlib.util
import itertools
import re
import sys

import pytest

import compile_spec
import generate_vectors
from engine import _eval_condition, load


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
    (multiplier, remainder) pair a covered number gives the rule's scale.
    Up to 999 that is every input the renderer can hand a condition; above
    it, every multiplier, with the remainders the sampled numbers leave.
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
        condition = yaml_rule.get("condition")
        if condition is None:
            assert compiled_rule["condition"] is None
            continue
        pairs = {divmod(n, yaml_rule["scale"]) for n in covered}
        for multiplier, remainder in sorted(pairs):
            variables = {"multiplier": multiplier, "remainder": remainder}
            assert bool(compiled_rule["condition"](variables)) == bool(
                _eval_condition(condition, variables)
            ), f"rule {yaml_rule['name']} disagrees at {variables}"


def test_chained_comparison_keeps_python_semantics():
    """A chained comparison is the case an emitter that pasted strings
    together would get wrong: `0 < d < 5` means `0 < d and d < 5`, not
    `(0 < d) < 5`, which would evaluate a bool against 5 and be true for
    d = 0. No rule in mizo.yaml uses one today, so this guards the
    mechanism rather than the current data.
    """
    condition = eval(compile_spec._compile_condition("0 < multiplier < 5"))
    results = [
        condition({"multiplier": n, "remainder": 0}) for n in (0, 1, 4, 5)
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
        "multiplier == 1",
        "multiplier > 1",
        "multiplier > 1 and remainder > 0",
        "remainder == 0 or remainder == 5",
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
        "hundred_thousands", "millions", "ten_millions", "hundred_millions", "billions",
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
            if condition is None or condition(
                {"multiplier": multiplier, "remainder": remainder}
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


def _ignorable_table(path):
    """The characters _IGNORABLE is built from, read out of the source.

    Read rather than imported: _render.py belongs to the package and does a
    relative import of _mizo, so it is not importable from here -- the same
    reason test_package_version_is_stated_once reads packages/python/ as
    text. Reading the source is also the right level for this check, since
    a one-sided edit to the table is a source-level edit.

    The shape is checked rather than assumed. Both copies are a dict
    comprehension over one string literal today; if either is rewritten into
    some other form, this says so instead of raising AttributeError from
    inside an attribute chain -- the "a verdict, not a crash from three calls
    down" rule #37 settled for _validate_spec, which applies to a helper that
    reads source just as much.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        targets = getattr(node, "targets", [])
        if not any(isinstance(t, ast.Name) and t.id == "_IGNORABLE" for t in targets):
            continue
        value = node.value
        if not isinstance(value, ast.DictComp) or len(value.generators) != 1:
            raise AssertionError(
                f"{path.name}: _IGNORABLE is no longer a single dict "
                f"comprehension; update this helper to read its new shape"
            )
        try:
            return ast.literal_eval(value.generators[0].iter)
        except ValueError:
            raise AssertionError(
                f"{path.name}: _IGNORABLE is not built from a string literal"
            ) from None
    raise AssertionError(f"no _IGNORABLE assignment in {path.name}")


def test_the_ignorable_table_is_identical_in_both_implementations():
    """_IGNORABLE is duplicated across engine.py and _render.py, and nothing
    else pins it.

    _WHITESPACE is duplicated the same way, but both suites derive it
    independently from str.isspace() minus the four characters that function
    over-matches, so those copies cannot drift without a test failing.
    _IGNORABLE has no external property to check against -- it is six
    characters chosen deliberately on #46 -- so until this, a one-sided edit
    passed both suites silently. That is the divergence #46 exists to
    prevent, in the one table with nothing to derive it from (zoramt, #56).

    Enumerating rather than deriving is defensible against Unicode drift,
    which was the argument on #46. It says nothing about two hand-maintained
    copies, which drift for ordinary reasons.
    """
    reference_table = _ignorable_table(
        compile_spec.REPO_ROOT / "reference" / "engine.py"
    )
    package_table = _ignorable_table(
        compile_spec.REPO_ROOT
        / "packages"
        / "python"
        / "src"
        / "numberwords"
        / "_render.py"
    )
    assert reference_table == package_table
    assert len(set(reference_table)) == 6


@pytest.fixture(scope="module")
def package():
    """The package's own public API, imported from its source tree.

    Everything else in this file reads the artifact or the package source as
    data. This one needs the package's parser running, and the package is
    importable from its src/ directory with no install step -- it depends on
    nothing, which is the point of compiling the spec (#20).
    """
    source = str(compile_spec.REPO_ROOT / "packages" / "python" / "src")
    sys.path.insert(0, source)
    try:
        yield importlib.import_module("numberwords")
    finally:
        sys.path.remove(source)


def test_the_package_parser_agrees_with_the_engine_on_every_short_phrase(spec, package):
    """Since #65 the package carries a real parser, and it is a second copy
    of the engine's -- deliberately, since the package never imports the
    oracle. The vectors hold the two together on every spelling they
    certify, all of which must be accepted, and on nothing that must be
    rejected. This holds them together on everything up to three words the
    lexicon can spell, connectors and alias spellings included: same
    number, or both refuse.

    It is the check that made the prototype for #65 trustworthy -- run then
    over every phrase of up to four words, 245,410 of them, with no
    disagreement -- kept at three so it costs seconds.
    """
    vocabulary = sorted(
        {spec._normalize_word(w) for table in spec.lexicon.values()
         for entry in table.values() for w in entry.values()}
        | {spec._normalize_word(c) for c in spec.parse_config["connectors"]}
        | {spec._normalize_word(a) for a in spec.parse_config["aliases"]}
    )
    disagreements = []
    for length in (1, 2, 3):
        for words in itertools.product(vocabulary, repeat=length):
            text = " ".join(words)
            try:
                expected = spec.text_to_number(text)
            except ValueError:
                expected = None
            try:
                got = package.text_to_number(text)
            except package.NumberWordsError:
                got = None
            if got != expected:
                disagreements.append((text, expected, got))
    assert not disagreements, disagreements[:10]


# The longest slip, in words, that the one-slip test below checks. See its
# docstring for why eight.
SLIP_PHRASE_MAX_WORDS = 8


def _near_misses(text):
    """Every spelling one slip away from `text`: one word deleted, one word
    doubled, or two neighbouring words swapped."""
    words = text.split()
    slips = set()
    for i in range(len(words)):
        slips.add(" ".join(words[:i] + words[i + 1:]))
        slips.add(" ".join(words[:i + 1] + words[i:]))
        if i + 1 < len(words):
            slips.add(" ".join(words[:i] + [words[i + 1], words[i]] + words[i + 2:]))
    slips.discard("")
    return slips


def test_the_package_parser_agrees_with_the_engine_one_slip_from_the_vectors(spec, package):
    """The short-phrase check above stops at three words, and the vectors
    only hold spellings that must be accepted. This covers the gap between:
    longer phrases that are *nearly* right, which is where a second copy of
    a parser is most likely to accept what the first one refuses.

    Every certified spelling of one number per shape (numbers_to_sweep),
    with one word deleted, doubled or swapped with its neighbour: same
    number, or both refuse. One number per shape, so it grows with the
    grammar rather than the range.

    Capped at SLIP_PHRASE_MAX_WORDS, because a parse costs more the longer
    the phrase: with the ladder to 10^10 - 1 (#27) the slips run to 29
    words, 12,525 phrases, about 70 s here. At 0-999 the longest slip was
    eight words (a seven-word spelling with one word doubled), so the cap
    would have dropped nothing there. And the length of a phrase is not
    where the two parsers can differ: a longer one is the same rules reached
    through one more {remainder}. What has to survive the cap is every rule,
    which the last assertion checks.
    """
    sweep = generate_vectors.numbers_to_sweep(spec)
    phrases = set()
    for n in sweep:
        for text in generate_vectors.accepted_inputs(spec, n):
            phrases |= {
                slip for slip in _near_misses(text)
                if len(slip.split()) <= SLIP_PHRASE_MAX_WORDS
            }
    disagreements = []
    accepted = 0
    for text in sorted(phrases):
        try:
            expected = spec.text_to_number(text)
            accepted += 1
        except ValueError:
            expected = None
        try:
            got = package.text_to_number(text)
        except package.NumberWordsError:
            got = None
        if got != expected:
            disagreements.append((text, expected, got))
    assert not disagreements, disagreements[:10]
    # Both halves have to be exercised, or "they agree" means little: some
    # slips still spell a number ("sâwm pakhat" with a word dropped is
    # "sâwm"), and most do not.
    assert 0 < accepted < len(phrases), (accepted, len(phrases))
    # The cap must not cost a rule: every emitting rule heads some number
    # whose canonical spelling, doubled in one word, still fits under it.
    # At 10^10 - 1 each one already does at six words.
    headed = {
        spec._find_rule(n)["name"] for n in sweep
        if len(spec.number_to_text(n).split()) < SLIP_PHRASE_MAX_WORDS
    }
    emitting = {r["name"] for r in spec.rules if r.get("emit") != "never"}
    assert emitting <= headed, sorted(emitting - headed)


@pytest.mark.parametrize(
    "text",
    [
        # Longer than the sweeps above reach, and each one a place where the
        # package's copy of greedy binding has to choose as the engine does
        # (#27 rule 6, Q-E, and the 2026-08-30 / 2026-09-03 decisions).
        "nuai za hnih pakhat sîng li sâng ruk za sarih sâwm leh pathum",
        "nuai sâwm leh sîng kua leh sâng riat leh za sarih leh sawm ruk leh panga",
        "nuai za hnih leh sawm nga",
        "nuai za hnih leh pathum",
        "nuai za pahnih",
        "maktaduai sawm pakhat",
        "vaibêlchhetak khat nuai sawm pakhat",
        "NUAIH-ZA-HNIH",
        # Refused by both, each for its own reason: above the range, below
        # the floor, and a single digit offered as a stacked multiplier.
        "tlûklehdingâwn sawm hnih",
        "sîng za",
        "vaibêlchhe pahnih",
    ],
)
def test_the_package_stacks_and_binds_greedily_as_the_engine_does(spec, package, text):
    try:
        expected = spec.text_to_number(text)
    except ValueError:
        expected = None
    try:
        got = package.text_to_number(text)
    except package.NumberWordsError:
        got = None
    assert got == expected
