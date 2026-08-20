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
# restating the pattern and drifting from it.
from engine import _PLACEHOLDER_RE

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "spec" / "spec.schema.json"
MIZO_SPEC_PATH = REPO_ROOT / "languages" / "mizo.yaml"
ALL_SPEC_PATHS = sorted((REPO_ROOT / "languages").glob("*.yaml"))


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
def test_accepted_forms_names_tables_and_fields_that_exist(path):
    # accepted_forms points at the lexicon in the same file (#31), and JSON
    # Schema cannot check a cross-reference like that -- it can only say the
    # keys are names and the values are lists of names. A typo would validate
    # cleanly and then do nothing at all: leniency would quietly stop
    # applying, which is the same silent degradation #31 was filed about.
    spec = _as_ir(path)
    lexicon = spec["lexicon"]
    accepted = spec.get("parse", {}).get("accepted_forms", {})
    for table, fields in accepted.items():
        assert table in lexicon, f"unknown lexicon table {table!r}"
        for field in fields:
            # At least one entry, not every entry: a language may well have
            # an alternate form for only some of its numerals.
            assert any(
                field in entry for entry in lexicon[table].values()
            ), f"no {table} entry has a {field!r} field"


@pytest.mark.parametrize("path", ALL_SPEC_PATHS, ids=lambda p: p.name)
def test_connector_precedes_names_tables_and_fields_that_exist(path):
    # The same cross-reference JSON Schema cannot check, for the same reason as
    # accepted_forms above (#31). connector_precedes points at the lexicon in
    # this file, so a typo'd table or field validates cleanly and then certifies
    # nothing: the generator quietly stops emitting the connector spellings and
    # the only symptom is a vector table that shrank. Name the wrong key here
    # instead of leaving that to be inferred from a count.
    spec = _as_ir(path)
    lexicon = spec["lexicon"]
    parse = spec.get("parse", {})
    precedes = parse.get("connector_precedes", {})
    # Declaring where a connector may stand, in a language that has no
    # connector, is a mechanism nothing can exercise (#36, #38).
    if precedes:
        assert parse.get("connectors"), "connector_precedes without connectors"
    for table, fields in precedes.items():
        assert table in lexicon, f"unknown lexicon table {table!r}"
        for field in fields:
            # At least one entry, not every entry: a language may carry an
            # alternate form for only some of its numerals.
            assert any(
                field in entry for entry in lexicon[table].values()
            ), f"no {table} entry has a {field!r} field"


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


# --- Note on languages/en.yaml --------------------------------------------
#
# en.yaml was ported to the current format in #29; before that it was written
# in the older illustrative `form:` mini-syntax and did not load in engine.py
# at all. It is capped at 0-99 rather than the 0-999 it used to claim, because
# English above 99 needs recursion ("three hundred and five" = {units} hundred
# and {0-99}) and the format has no recursive placeholder. That gap is tracked
# on #27, and the hundreds return with it.
