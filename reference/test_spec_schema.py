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
