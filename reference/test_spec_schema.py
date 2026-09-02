"""Validates language specs against spec/spec.schema.json.

Why this exists: until now the real definition of the spec format was
"whatever engine.py happens to accept". A malformed spec surfaced as a
KeyError from deep inside the engine, which is fine while Mizo is the only
language and every edit is hand-reviewed, and much less fine once someone
writes a second spec without the format in their head.

Two kinds of test here, and the second matters more than the first:

- Positive: languages/mizo.yaml validates. Proves the schema describes the
  format we actually use.
- Negative: specific mutations of a valid spec are REJECTED. Proves the
  schema constrains anything at all. A schema that accepts every document
  would pass the positive test and be worthless -- so each negative case
  names the mistake it is there to catch.

Since #37 there are two layers, and they check different things. The schema
constrains the *shape* of a document -- that `accepted_forms` maps names to
lists of names. engine._validate_spec constrains what those names *mean* --
that they refer to something in this file's lexicon. JSON Schema cannot
express a cross-reference, so anything of that kind is tested against the
loader below rather than against the schema.

Validation runs against the JSON normalisation of the YAML, per
docs/spec-format.md ("YAML for authoring; it normalises to JSON as the IR").
That is not incidental: YAML gives integer lexicon keys, JSON object keys are
always strings, and the schema's key patterns are written for the JSON form.

Both checked-in specs are validated. That matters more than it looks: until
#29 the only spec in the current format was Mizo, so nothing could tell the
difference between "the schema describes the format" and "the schema
describes Mizo". en.yaml is the control.
"""

import copy
import json
from pathlib import Path

import jsonschema
import pytest
import yaml

# Placeholder syntax is defined once, in the engine. The cross-reference
# tests below read templates, so they borrow that definition rather than
# restating the pattern and drifting from it. Spec is imported because the
# cross-reference checks now live in the loader (#37), so the tests exercise
# it instead of reimplementing what it does.
import engine
from engine import _PLACEHOLDER_RE, _find_rule, _positional_variables, _render, Spec

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "spec" / "spec.schema.json"
MIZO_SPEC_PATH = REPO_ROOT / "languages" / "mizo.yaml"
ALL_SPEC_PATHS = sorted((REPO_ROOT / "languages").glob("*.yaml"))


def _spec_data(path: Path) -> dict:
    """The spec as the *engine* loads it: plain YAML, integer lexicon keys.

    Deliberately not _as_ir. The schema targets the JSON normalisation, where
    keys are strings; the engine indexes the lexicon with real integers. A
    loader test written against the IR would pass for the wrong reason.
    """
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _as_ir(path: Path) -> dict:
    """Load a YAML spec and normalise it to the JSON IR the schema targets."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    # json.dumps stringifies integer keys, which is exactly the normalisation
    # docs/spec-format.md describes -- do it explicitly rather than relying on
    # the validator to coerce.
    return json.loads(json.dumps(data))


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def mizo_ir():
    return _as_ir(MIZO_SPEC_PATH)


def test_schema_is_itself_a_valid_json_schema(schema):
    # Catches a typo in the schema that would otherwise make every validation
    # below silently vacuous.
    jsonschema.Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("path", ALL_SPEC_PATHS, ids=lambda p: p.name)
def test_checked_in_spec_validates(schema, path):
    # Globbed rather than listed: a new languages/*.yaml is validated the
    # moment it lands, instead of when someone remembers to add it here.
    jsonschema.validate(instance=_as_ir(path), schema=schema)


def test_every_checked_in_spec_is_covered():
    # Guards the glob above: if languages/ is ever emptied or renamed, the
    # parametrised test would silently pass zero cases.
    assert len(ALL_SPEC_PATHS) >= 2, ALL_SPEC_PATHS


@pytest.mark.parametrize("path", ALL_SPEC_PATHS, ids=lambda p: p.name)
def test_every_checked_in_spec_loads(path):
    # Constructing a Spec runs engine._validate_spec (#37), so this is the
    # positive half of every cross-reference case below: both checked-in
    # specs name tables, fields and lexicon keys that exist, every condition
    # is inside the allowlist, and every template literal is something
    # _tokenize removes.
    #
    # This replaces two tests that reimplemented those checks over the same
    # two files. Reimplementing them meant the checked-in specs were covered
    # and a spec loaded from anywhere else was not -- which is the gap #37
    # was filed about, present in the test file as well as in the engine.
    Spec(_spec_data(path))


@pytest.mark.parametrize("path", ALL_SPEC_PATHS, ids=lambda p: p.name)
def test_accepted_forms_lists_only_fields_no_template_already_names(path):
    # accepted_forms holds the *extra* fields, per the schema: the field a
    # template names is accepted anyway, so listing it adds nothing -- and
    # adds nothing harmfully, because it hides the mistake where a target
    # reads only the list and drops the always-accept half of the rule.
    # Mizo lists `units: [bound]` and not `standalone` for exactly that
    # reason: a target with that mistake then fails on "pakhat", which every
    # vector's accepted_inputs contains.
    #
    # This test is what keeps that property from decaying silently. If a
    # canonical form ever moves -- say the units template came to name
    # `bound` -- the list would quietly become a no-op, and leniency would
    # disappear with every test still green. Here it fails instead.
    #
    # Only single-placeholder templates count: leniency applies nowhere else,
    # so a field named solely by a multi-word template (units.bound, in
    # exact_tens) is still a legitimate extra. Scanning parse_aliases as well
    # as output is inert on today's data -- neither spec has a
    # single-placeholder alias -- but one would fall into the same trap, so
    # it is scanned rather than left for later.
    spec = _as_ir(path)
    accepted = spec.get("parse", {}).get("accepted_forms", {})
    named = {}
    for rule in spec["grammar"]["rules"]:
        for template in [rule["output"], *rule.get("parse_aliases", [])]:
            placeholders = _PLACEHOLDER_RE.findall(template)
            if len(placeholders) == 1:
                table, _key, field = placeholders[0]
                named.setdefault(table, set()).add(field)
    for table, fields in accepted.items():
        redundant = sorted(set(fields) & named.get(table, set()))
        assert not redundant, (
            f"{table}: {redundant} is already accepted as the field a "
            f"single-placeholder template names -- list only the extras"
        )


# --- Negative cases -------------------------------------------------------
#
# Each entry mutates a valid spec in one specific way and must be rejected.
# The id names the authoring mistake being guarded against.


def _without(d: dict, *keys):
    out = copy.deepcopy(d)
    for k in keys:
        out.pop(k, None)
    return out


def _mutate(d: dict, path: list, value):
    out = copy.deepcopy(d)
    cursor = out
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    return out


MUTATIONS = {
    "missing meta": lambda s: _without(s, "meta"),
    "missing lexicon": lambda s: _without(s, "lexicon"),
    "missing grammar": lambda s: _without(s, "grammar"),
    "typo in top-level key": lambda s: {**s, "lexicons": {}},
    "two-letter language code": lambda s: _mutate(s, ["meta", "code"], "mz"),
    "non-semver spec version": lambda s: _mutate(s, ["meta", "version"], "0.1"),
    "supports missing max": lambda s: _mutate(
        s, ["meta", "supports"], {"min": 0}
    ),
    "empty sources list": lambda s: _mutate(s, ["meta", "sources"], []),
    "unsourced spec": lambda s: _mutate(s, ["meta"], _without(s["meta"], "sources")),
    "lexicon key that isn't numeric": lambda s: _mutate(
        s, ["lexicon", "units"], {"one": {"standalone": "pakhat"}}
    ),
    "lexicon entry holding a bare string": lambda s: _mutate(
        s, ["lexicon", "units"], {"1": "pakhat"}
    ),
    "rule with no output": lambda s: _mutate(
        s, ["grammar", "rules"], [{"name": "units", "range": [0, 9]}]
    ),
    "rule with no name": lambda s: _mutate(
        s,
        ["grammar", "rules"],
        [{"range": [0, 9], "output": "{units[ones_digit].standalone}"}],
    ),
    "range with three bounds": lambda s: _mutate(
        s,
        ["grammar", "rules"],
        [
            {
                "name": "units",
                "range": [0, 9, 99],
                "output": "{units[ones_digit].standalone}",
            }
        ],
    ),
    "empty rules list": lambda s: _mutate(s, ["grammar", "rules"], []),
    "placeholder missing its field": lambda s: _mutate(
        s,
        ["grammar", "rules"],
        [{"name": "units", "range": [0, 9], "output": "{units[ones_digit]}"}],
    ),
    "unclosed placeholder brace": lambda s: _mutate(
        s,
        ["grammar", "rules"],
        [
            {
                "name": "units",
                "range": [0, 9],
                "output": "{units[ones_digit].standalone",
            }
        ],
    ),
    "parse_aliases with the same brace typo": lambda s: _mutate(
        s,
        ["grammar", "rules"],
        [
            {
                "name": "units",
                "range": [0, 9],
                "output": "{units[ones_digit].standalone}",
                "parse_aliases": ["{units[ones_digit]}"],
            }
        ],
    ),
    "typo in a parse flag name": lambda s: _mutate(
        s, ["parse"], {**s["parse"], "case_insensitve": True}
    ),
    "non-boolean parse flag": lambda s: _mutate(
        s, ["parse"], {**s["parse"], "case_insensitive": "yes"}
    ),
    "example missing its text": lambda s: _mutate(s, ["examples"], [{"number": 7}]),
    # accepted_forms maps a lexicon table to field names (#31). The boolean
    # flags are the shape it had before that, so a spec written against the
    # old format should fail loudly rather than be silently ignored.
    "accepted_forms using the old boolean flags": lambda s: _mutate(
        s,
        ["parse"],
        {**s["parse"], "accepted_forms": {"standalone_units": True}},
    ),
    "accepted_forms listing an empty field list": lambda s: _mutate(
        s, ["parse"], {**s["parse"], "accepted_forms": {"units": []}}
    ),
    "accepted_forms repeating a field": lambda s: _mutate(
        s,
        ["parse"],
        {
            **s["parse"],
            "accepted_forms": {"units": ["standalone", "standalone"]},
        },
    ),
    "accepted_forms holding a bare string": lambda s: _mutate(
        s, ["parse"], {**s["parse"], "accepted_forms": {"units": "standalone"}}
    ),
}


@pytest.mark.parametrize("description", sorted(MUTATIONS))
def test_invalid_spec_is_rejected(schema, mizo_ir, description):
    broken = MUTATIONS[description](mizo_ir)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=broken, schema=schema)


def test_schema_is_not_accidentally_mizo_specific(schema):
    # The negative cases prove the schema constrains something. This proves it
    # doesn't constrain too much -- that a different language, with different
    # lexicon tables and different form names, still validates. Without this,
    # the schema could quietly require Mizo's shape (a `scales` table, a
    # `bound` field, an `orthography`) and nobody would find out until the
    # second language was written.
    other_language = {
        "meta": {
            "language": "Testish",
            "code": "zxx",
            "version": "0.1.0",
            "supports": {"min": 0, "max": 9},
            "sources": ["Invented for this test; not a real language."],
        },
        "lexicon": {
            # Neither table name nor field name matches Mizo's.
            "digits": {"0": {"citation": "nul"}, "1": {"citation": "un"}}
        },
        "grammar": {
            "rules": [
                {
                    "name": "digits",
                    "range": [0, 9],
                    "output": "{digits[ones_digit].citation}",
                }
            ]
        },
        # parse and examples omitted entirely -- both are optional.
    }
    jsonschema.validate(instance=other_language, schema=schema)


def test_mizo_spec_is_unchanged_by_the_negative_cases(schema, mizo_ir):
    # The mutations deep-copy, but a shallow slip in one of them would corrupt
    # the module-scoped fixture and make every later test meaningless.
    jsonschema.validate(instance=mizo_ir, schema=schema)


# --- The loader's cross-reference checks (#37) -----------------------------
#
# Everything below is a mistake the schema structurally cannot catch, because
# it is about whether a name refers to something rather than whether it is a
# name. Each mutation changes one declared thing at a time: dropping a whole
# key can fail for the wrong reason, and #50 showed a coarse mutation hiding a
# gap inside the thing it mutates.


@pytest.fixture
def mizo_data():
    return _spec_data(MIZO_SPEC_PATH)


def _rule(data: dict, name: str) -> dict:
    return next(r for r in data["grammar"]["rules"] if r["name"] == name)


def _with_rule(data: dict, name: str, **changes) -> dict:
    out = copy.deepcopy(data)
    _rule(out, name).update(changes)
    return out


def _with_parse(data: dict, **changes) -> dict:
    out = copy.deepcopy(data)
    out["parse"].update(changes)
    return out


# The shape from #37. Accepted by the old engine when ones_digit was 0 and
# rejected when it was 1 -- the same spec valid or not depending on the number
# being converted.
#
# A call is the unsupported node here, and len() is deliberately a dull one.
# #37 demonstrated the bug with __import__("os").system(...), which reads as a
# sandbox escape and is not one: _eval_node raises on ast.Call, it never
# evaluates it, so the short-circuited subtree was not executed either. What
# was broken is only that validity depended on the input, and any unsupported
# node shows that.
_UNSUPPORTED_NODE_BEHIND_OR = 'ones_digit == 0 or len("x") == 0'
_UNSUPPORTED_NODE_BEHIND_AND = 'ones_digit == 99 and len("x") == 0'

LOAD_REJECTS = {
    "condition hiding an unsupported node behind or": lambda s: _with_rule(
        s, "exact_tens", condition=_UNSUPPORTED_NODE_BEHIND_OR
    ),
    "condition hiding an unsupported node behind and": lambda s: _with_rule(
        s, "exact_tens", condition=_UNSUPPORTED_NODE_BEHIND_AND
    ),
    "condition naming a variable that does not exist": lambda s: _with_rule(
        s, "exact_tens", condition="hundreds_digit == 0"
    ),
    "condition using an operator outside the allowlist": lambda s: _with_rule(
        s, "exact_tens", condition="ones_digit + 1 == 1"
    ),
    "accepted_forms naming a table that does not exist": lambda s: _with_parse(
        s, accepted_forms={"unitz": ["bound"]}
    ),
    "accepted_forms naming a field no entry has": lambda s: _with_parse(
        s, accepted_forms={"units": ["bnud"]}
    ),
    "connector_precedes naming a table that does not exist": lambda s: _with_parse(
        s, connector_precedes={"scalez": ["standalone"]}
    ),
    "connector_precedes naming a field no entry has": lambda s: _with_parse(
        s, connector_precedes={"scales": ["multiplyed"]}
    ),
    "placeholder naming a table that does not exist": lambda s: _with_rule(
        s, "units", output="{unitz[ones_digit].standalone}"
    ),
    "placeholder naming a field no entry has": lambda s: _with_rule(
        s, "units", output="{units[ones_digit].stanalone}"
    ),
    "placeholder naming a lexicon key that does not exist": lambda s: _with_rule(
        s, "ten", output="{scales[1000].standalone}"
    ),
    # Khasi in miniature (#48, #53): a morpheme bound to the placeholder
    # rather than a separator between placeholders.
    "template literal that is a bound morpheme": lambda s: _with_rule(
        s, "exact_tens", output="{scales[10].multiplied}phew {units[tens_digit].bound}"
    ),
    "parse_alias literal that is a bound morpheme": lambda s: _with_rule(
        s,
        "compound_tens",
        parse_aliases=["{units[tens_digit].bound}phew {units[ones_digit].bound}"],
    ),
    # A free-standing word literal, which is the #53 clock case: the rule
    # renders "dar pathum" and then cannot parse it back, because the arity
    # check sees two tokens against one placeholder.
    "template literal that is a free word": lambda s: _with_rule(
        s, "units", output="dar {units[ones_digit].standalone}"
    ),
    # Two placeholders with nothing between them: the concatenation shape
    # from #48. Renders as one token, so the arity check can never match it.
    "placeholders written adjacent": lambda s: _with_rule(
        s, "teens", output="{scales[10].standalone}{units[ones_digit].standalone}"
    ),
    # Being a connector is not enough on its own -- it also has to separate.
    # This renders "sawmlehpakhat" as a single token.
    "placeholders joined by a connector with no separator": lambda s: _with_rule(
        s, "teens", output="{scales[10].standalone}leh{units[ones_digit].standalone}"
    ),
    # The four below are the boundary cases, and they are the reason the check
    # asks each side separately instead of asking whether the literal contains
    # a separator anywhere. The first two sit at an edge, which a
    # "between two placeholders" test never looks at. The second two sit
    # squarely between two placeholders and still satisfy a `re.search`, on
    # the strength of the separator at the end that is not the boundary in
    # question. All four render a token that the arity check cannot match, so
    # the rule fails to parse its own output -- the #53 symptom exactly.
    "connector before the first placeholder, unseparated": lambda s: _with_rule(
        s, "units", output="leh{units[ones_digit].standalone}"
    ),
    "connector after the last placeholder, unseparated": lambda s: _with_rule(
        s, "units", output="{units[ones_digit].standalone}leh"
    ),
    "joining connector separated on its left only": lambda s: _with_rule(
        s, "teens", output="{scales[10].standalone} leh{units[ones_digit].standalone}"
    ),
    "joining connector separated on its right only": lambda s: _with_rule(
        s, "teens", output="{scales[10].standalone}leh {units[ones_digit].standalone}"
    ),
    # The schema can require two integers, not that the first is the smaller.
    # _find_rule tests low <= n <= high, so this rule can never fire, and the
    # symptom is an error naming the number rather than the rule.
    "range that is inverted, so the rule can never match": lambda s: _with_rule(
        s, "exact_tens", range=[99, 20]
    ),
}


@pytest.mark.parametrize("description", sorted(LOAD_REJECTS))
def test_load_rejects_what_the_schema_cannot_express(description, mizo_data):
    broken = LOAD_REJECTS[description](mizo_data)
    with pytest.raises(ValueError):
        Spec(broken)


@pytest.mark.parametrize("description", sorted(LOAD_REJECTS))
def test_the_schema_alone_would_accept_all_of_them(schema, description, mizo_data):
    # This is what makes the loader pass worth having rather than schema work.
    # Every case above is a well-formed document by the schema's rules and a
    # broken spec by the engine's. If one of these ever starts failing schema
    # validation, the schema has grown the ability to express it and the
    # loader check became redundant -- worth finding out deliberately.
    broken = LOAD_REJECTS[description](mizo_data)
    jsonschema.validate(instance=json.loads(json.dumps(broken)), schema=schema)


def test_a_separated_edge_connector_is_still_accepted(mizo_data):
    # The counterpart to the four boundary cases in LOAD_REJECTS, and the
    # reason the rule is stated per boundary rather than "an edge literal is
    # forbidden". A trailing connector that IS separated from the placeholder
    # renders as two tokens, the connector is one _tokenize removes, and the
    # rule parses its own output. Rejecting this would be over-tightening.
    ok = _with_rule(mizo_data, "units", output="{units[ones_digit].standalone} leh")
    spec = Spec(ok)
    assert spec.number_to_text(3) == "pathum leh"
    assert spec.text_to_number("pathum leh") == 3


# _validate_spec walks the rules in three separate loops, and each one has to
# default the name the same way. One case per loop, because a rule that is
# broken in two ways only ever reaches the first loop that rejects it -- which
# is how the placeholder loop's default came to be uncovered while a test
# named "an unnamed rule gets a verdict" was passing.
UNNAMED_RULE_BREAKAGE = {
    "condition loop": {"condition": "hundreds_digit == 0"},
    "placeholder loop": {"output": "{unitz[ones_digit].standalone}"},
    "literal loop": {"output": "dar {units[ones_digit].standalone}"},
}


@pytest.mark.parametrize("loop", sorted(UNNAMED_RULE_BREAKAGE))
def test_an_unnamed_rule_gets_a_verdict_not_a_key_error(loop, mizo_data):
    # A rule with no name is a schema violation, but a function called
    # "validate" has to survive one long enough to say so: reporting
    # KeyError('name') from inside the check reads as a crash, and the
    # docstring promises a verdict rather than a TypeError from three calls
    # down. The type-check loop already defaulted the name; these are the two
    # that indexed it.
    broken = copy.deepcopy(mizo_data)
    rule = _rule(broken, "exact_tens" if loop == "condition loop" else "units")
    del rule["name"]
    rule.update(UNNAMED_RULE_BREAKAGE[loop])
    with pytest.raises(ValueError, match="unnamed rule"):
        Spec(broken)


def test_a_condition_is_rejected_before_any_number_is_converted(mizo_data):
    # The shape of #37, stated directly. The old engine checked nodes as it
    # reached them, so this spec was accepted for numbers whose ones digit was
    # 0 -- the short-circuit meant the offending subtree was never visited --
    # and rejected for the rest. Validity depended on the input, which is not
    # a property a spec is allowed to have.
    broken = _with_rule(mizo_data, "exact_tens", condition=_UNSUPPORTED_NODE_BEHIND_OR)
    with pytest.raises(ValueError, match="exact_tens"):
        Spec(broken)


@pytest.mark.parametrize("section", ["lexicon", "grammar"])
def test_a_spec_missing_a_whole_section_is_named_not_crashed(mizo_data, section):
    # Deliberately NOT in LOAD_REJECTS: the schema has `required` and catches
    # both of these, so the companion test's claim -- that the schema accepts
    # every case in that list -- would be false for them. It said so on the
    # first run, which is the check working.
    #
    # Kept anyway, because _validate_spec reaches data["lexicon"] before
    # anything else, and a function called "validate" reporting
    # KeyError: 'lexicon' reads as a crash rather than a verdict.
    broken = {k: v for k, v in mizo_data.items() if k != section}
    with pytest.raises(ValueError, match=section):
        Spec(broken)


# Same reasoning as the missing-section test above, and not in LOAD_REJECTS
# for the same reason: output and condition are both `type: string` in the
# schema, so these are schema-catchable too. Found auditing this PR, not in
# #37 as filed -- a wrong-typed output or condition used to reach ast.parse
# or a regex three calls down and surface as TypeError, which nothing else
# here does.
TYPE_MISMATCHES = {
    "output is not a string": lambda s: _with_rule(s, "units", output=5),
    "output is missing": lambda s: {
        **s,
        "grammar": {
            "rules": [
                {k: v for k, v in r.items() if k != "output"}
                if r["name"] == "units" else r
                for r in s["grammar"]["rules"]
            ]
        },
    },
    "condition is not a string": lambda s: _with_rule(s, "exact_tens", condition=True),
    "a parse_aliases entry is not a string": lambda s: _with_rule(
        s, "compound_tens", parse_aliases=[5]
    ),
}


@pytest.mark.parametrize("description", sorted(TYPE_MISMATCHES))
def test_a_wrong_typed_rule_field_is_named_not_crashed(description, mizo_data):
    broken = TYPE_MISMATCHES[description](mizo_data)
    with pytest.raises(ValueError, match="must be a string"):
        Spec(broken)


def test_connector_precedes_without_connectors_is_rejected():
    # Built on English rather than Mizo, and that is the whole point of the
    # test. Stripping `connectors` from mizo.yaml also strips the meaning of
    # the "leh" literal in the hundreds templates, so the literal check fires
    # first and the case passes without the connectors-required check existing
    # at all -- found by mutating that check away and watching nothing fail.
    #
    # English has connectors but no rule in 0-99 emits one, so removing them
    # leaves every template still valid and isolates the case.
    data = _spec_data(REPO_ROOT / "languages" / "en.yaml")
    data["parse"]["connector_precedes"] = {"units": ["word"]}
    Spec(data)  # with connectors present, this is a fine spec

    data["parse"]["connectors"] = []
    with pytest.raises(ValueError, match="without any connectors"):
        Spec(data)


def test_the_checked_in_spec_survives_the_loader_mutations(mizo_data):
    # Same guard as the schema block above: a shallow slip in any mutation
    # would corrupt the spec every other test in this module reads.
    Spec(mizo_data)


# The property behind the literal check, stated directly rather than by proxy.
#
# Every check in _validate_spec stands in for something. This one's something
# is: a rule must be able to parse the text it renders. Stating the property
# on its own is worth more than the proxy, because a proxy can be weaker than
# the thing it claims to enforce -- which is exactly how the four boundary
# cases in LOAD_REJECTS got past a check written to stop them.
#
# Mutation testing cannot find that gap. It perturbs the checks that exist and
# asks whether a test notices; it is blind to a check that was never written,
# and to one that is weaker than its own description. A property is the
# complement: it does not care which check catches the violation, only that
# something does.
#
# This does not replace the loader check. It runs over the specs in
# languages/, and the loader check exists for specs nobody has written yet --
# which is the whole point of moving those checks out of this file in #37.


def _first_round_trip_failure(spec):
    """The first n whose canonical output does not parse back to n.

    Returns (n, rendered, reason), or None if the property holds across the
    whole supported range.
    """
    for n in range(spec.supports["min"], spec.supports["max"] + 1):
        rendered = spec.number_to_text(n)
        try:
            parsed = spec.text_to_number(rendered)
        except ValueError as exc:
            return n, rendered, str(exc)
        if parsed != n:
            return n, rendered, f"parsed back to {parsed}"
    return None


@pytest.mark.parametrize("path", ALL_SPEC_PATHS, ids=lambda p: p.name)
def test_every_rule_parses_its_own_output(path):
    spec = Spec(_spec_data(path))
    failure = _first_round_trip_failure(spec)
    assert failure is None, (
        f"{path.name}: {failure[0]} renders {failure[1]!r}, which {failure[2]}"
    )
    # Named rules, not just numbers: the property is about rules, and a rule
    # no number reaches is one this test silently says nothing about.
    exercised = {
        _find_rule(spec.rules, n, _positional_variables(n))["name"]
        for n in range(spec.supports["min"], spec.supports["max"] + 1)
    }
    unreachable = {rule["name"] for rule in spec.rules} - exercised
    assert not unreachable, f"{path.name}: no number reaches {sorted(unreachable)}"


def _first_alias_failure(spec):
    """The first declared alias spelling that does not parse to its own number.

    The alias counterpart to _first_round_trip_failure, and a deliberately
    different property. `number_to_text` never emits an alias, so breaking one
    cannot break the canonical round trip -- which is why the alias case is
    excluded from TEMPLATE_REJECTS. What it can break is the property CLAUDE.md
    names alongside it, `text -> number -> text` being stable: a spelling a
    rule declares as acceptable has to parse to the number whose rule declares
    it.

    Returns (n, spelling, reason), or None if every declared alias holds across
    the whole supported range.
    """
    for n in range(spec.supports["min"], spec.supports["max"] + 1):
        variables = _positional_variables(n)
        rule = _find_rule(spec.rules, n, variables)
        for template in rule.get("parse_aliases", []):
            spelling = _render(template, spec.lexicon, variables)
            try:
                parsed = spec.text_to_number(spelling)
            except ValueError as exc:
                return n, spelling, str(exc)
            if parsed != n:
                return n, spelling, f"parsed back to {parsed}"
    return None


@pytest.mark.parametrize("path", ALL_SPEC_PATHS, ids=lambda p: p.name)
def test_every_declared_alias_parses_to_its_own_number(path):
    # This is the vacuity guard on _first_alias_failure as much as it is a
    # property test. The negative test below asserts that the helper *finds* a
    # failure for the rejected alias; a helper broken so that it always
    # reported one would make that pass for exactly the wrong reason. Running
    # it over the real specs and requiring None is what rules that out.
    #
    # As coverage on its own it is close to redundant, and narrower than the
    # name suggests. The property is self-referential -- the spelling is
    # rendered from the very template it is then parsed back through -- so it
    # can only catch a template that breaks the matcher, never one that is
    # merely wrong. Mutating mizo's alias to take the standalone tens form,
    # which renders "pahnih thum" for 23, passes here; four tests in
    # test_engine.py catch that instead. It is redundant in a second way too:
    # generate_vectors.py emits alias spellings into accepted_inputs, so
    # test_vectors_parse_back already exercises them. Stating the property
    # directly still beats relying on the generator having happened to emit it.
    #
    # Inert on en.yaml, which declares no parse_aliases at all -- today only
    # compound_tens in mizo.yaml has one. Said here rather than left for a
    # reader to discover.
    spec = Spec(_spec_data(path))
    failure = _first_alias_failure(spec)
    assert failure is None, (
        f"{path.name}: {failure[0]} declares the alias spelling {failure[1]!r}, "
        f"which {failure[2]}"
    )


# Every template case in LOAD_REJECTS, except the parse_aliases one: an alias
# is an extra spelling to accept, so breaking it cannot break the round trip
# of the canonical output. It is demonstrated against its own property
# instead -- see ALIAS_REJECTS below.
TEMPLATE_REJECTS = (
    "template literal that is a bound morpheme",
    "template literal that is a free word",
    "placeholders written adjacent",
    "placeholders joined by a connector with no separator",
    "connector before the first placeholder, unseparated",
    "connector after the last placeholder, unseparated",
    "joining connector separated on its left only",
    "joining connector separated on its right only",
)


@pytest.mark.parametrize("description", TEMPLATE_REJECTS)
def test_each_rejected_template_really_does_break_the_round_trip(
    description, mizo_data, monkeypatch
):
    # This is what turns the literal check from a house rule into an enforced
    # property. With validation switched off, each rejected template has to
    # actually fail to parse its own output -- otherwise the loader is
    # rejecting a spec for a reason that is not true, and the check should
    # be narrowed rather than defended.
    monkeypatch.setattr(engine, "_validate_spec", lambda data: None)
    spec = Spec(LOAD_REJECTS[description](mizo_data))
    assert _first_round_trip_failure(spec) is not None, (
        f"{description!r} is rejected at load but round-trips fine, so the "
        f"check is stricter than the property it cites"
    )


# The alias case from LOAD_REJECTS, kept in its own list because the property
# it violates is a different one -- not because it is a weaker case.
#
# One entry, and one is the right number. _validate_literals runs over `output`
# and over `parse_aliases` through the same loop with the same arguments (see
# "for template in [rule['output'], *rule.get('parse_aliases', [])]" in
# engine.py), so every boundary shape enumerated in TEMPLATE_REJECTS is already
# the same code on both slots. Duplicating those eight here would add rows that
# cannot fail independently of the ones above -- the inert-invariant trap. The
# dimension this list covers is the *slot*: that the loop visits parse_aliases
# at all.
#
# The entry is load-bearing, and measurably so: deleting the parse_aliases
# half of that loop stops this case being rejected at load. What catches
# that is test_load_rejects_what_the_schema_cannot_express, not the
# ownership test below -- a case is "owned" when it *loads* with the check
# disabled, which the mutation does not change. So the slot was already
# covered before #55; what was missing was the demonstration.
ALIAS_REJECTS = ("parse_alias literal that is a bound morpheme",)


@pytest.mark.parametrize("description", ALIAS_REJECTS)
def test_each_rejected_alias_really_does_break_the_alias_property(
    description, mizo_data, monkeypatch
):
    # The same bargain as the template test above, made against the property an
    # alias actually has. With validation switched off, a rejected alias
    # template has to fail to accept the spelling it itself describes --
    # otherwise the loader is rejecting a spec for a reason that is not true,
    # and the check should be narrowed rather than defended.
    monkeypatch.setattr(engine, "_validate_spec", lambda data: None)
    spec = Spec(LOAD_REJECTS[description](mizo_data))
    assert _first_alias_failure(spec) is not None, (
        f"{description!r} is rejected at load, but every declared alias still "
        f"parses to its own number, so the check is stricter than the property "
        f"it cites"
    )


def test_every_case_the_literal_check_owns_is_justified_by_the_property(
    mizo_data, monkeypatch
):
    # A guard on the list above, not on the engine. Which cases does
    # _validate_literals own? The ones that stop being rejected when it is
    # switched off -- asked of the engine rather than guessed from the wording
    # of a description, so a renamed case cannot drift out of scope.
    #
    # Adding a case to LOAD_REJECTS without adding it to TEMPLATE_REJECTS or
    # ALIAS_REJECTS fails here, which is the point: a check is entitled to
    # reject a spec only for a reason something demonstrates. Until #55 the
    # alias case was named here as a literal string instead -- an exception
    # in the one test whose job is that there are none.
    owned = set()
    for description, mutate in LOAD_REJECTS.items():
        with monkeypatch.context() as without_the_check:
            without_the_check.setattr(
                engine, "_validate_literals", lambda *a, **k: None
            )
            try:
                Spec(mutate(mizo_data))
            except ValueError:
                continue  # some other check rejects it; not this one's case
        owned.add(description)
    assert owned == set(TEMPLATE_REJECTS) | set(ALIAS_REJECTS)


# --- Note on languages/en.yaml --------------------------------------------
#
# en.yaml was ported to the current format in #29; before that it was written
# in the older illustrative `form:` mini-syntax and did not load in engine.py
# at all. It is capped at 0-99 rather than the 0-999 it used to claim, because
# English above 99 needs recursion ("three hundred and five" = {units} hundred
# and {0-99}) and the format has no recursive placeholder. That gap is tracked
# on #27, and the hundreds return with it.
