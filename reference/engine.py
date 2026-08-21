"""Reference engine: interprets a language spec (languages/<lang>.yaml) to
convert numbers to text. This is the "oracle" described in
docs/architecture.md -- the definition of correctness that target packages
(Python, npm, ...) are eventually checked against, instead of each
reimplementing a language's rules by hand.

Scope: specs shaped like the current languages/mizo.yaml (positional
variables ones_digit/tens_digit only). That covers 0-199 as of #19 -- a rule
matches on its `range` as well as its condition, so 118 and 18 select
different rules despite identical positional variables, and the hundreds
digit is always 1 across the range. (The order of the two checks is not what
does this; a rule is selected only when both pass.) A third variable becomes
necessary at 200, where the hundreds digit multiplies. Larger ranges are
follow-up work.

text -> number first normalises both the input *and* the lexicon words
using the spec's `parse` section (see Spec._normalize_word). It then
searches the supported range for the number whose grammar rule matches
the input token by token -- see Spec.text_to_number().
Matching is placeholder-aware rather than a plain string comparison against
number_to_text()'s output: a freestanding single-digit phrase (one token,
one placeholder) accepts either bound or standalone form per
parse.accepted_forms (e.g. "khat" as well as "pakhat" for 1), while
multi-word rules (teens, exact_tens, compound_tens, ...) match each field
exactly as the canonical template names it, to avoid cross-rule ambiguity
(see _rule_matches). A rule may also declare `parse_aliases`: a list of
extra templates (same placeholder syntax as `output`) accepted when parsing
but never produced by number_to_text() -- e.g. compound_tens' shorthand that
drops the scale word. These are matched with the same field-exactness as
the canonical output; only a single freestanding placeholder gets bound/
standalone leniency. number_to_text() stays the single source of truth for
the canonical form. This is cheap enough for a 0-199 range by brute-force
search -- 200 candidates -- and #19 extended the range without needing to
change it. It will need to become a real parser well before Mizo's ceiling:
see #27, which puts that at 10^18 - 1.
"""

import ast
import operator
import re
import unicodedata

import yaml

_COMPARISONS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
}

_BOOL_COMBINERS = {
    ast.And: all,
    ast.Or: any,
}

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\[(\w+)\]\.(\w+)\}")


def _eval_condition(expr: str, variables: dict) -> bool:
    """Evaluate a `condition` string like "ones_digit == 0 and tens_digit > 1"
    against `variables`. Deliberately not eval()/exec(): `condition` is data
    loaded from a YAML spec file, not code we wrote, so only a small allowed
    set of nodes (comparisons, and/or, names, int constants) is permitted --
    anything else raises ValueError instead of silently running arbitrary
    Python.

    Since #37 the same allowlist runs over the whole tree at load, in
    _validate_condition_node, so by the time anything is evaluated here it
    has already been accepted. _eval_node's own raises are kept as a
    backstop and are unreachable through Spec: they can only fire for a
    caller who evaluates an expression without a Spec around it, as the
    tests do. Kept rather than deleted for the reason #36 settled on for the
    connector-normalisation assert -- an invariant that cannot currently
    fail is still worth stating, provided the limit is written down.
    """
    tree = ast.parse(expr, mode="eval").body
    return _eval_node(tree, variables)


def _eval_node(node, variables):
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, variables)
        for op, comparator in zip(node.ops, node.comparators):
            op_type = type(op)
            if op_type not in _COMPARISONS:
                raise ValueError(f"Unsupported comparison operator: {op_type.__name__}")
            right = _eval_node(comparator, variables)
            if not _COMPARISONS[op_type](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        op_type = type(node.op)
        if op_type not in _BOOL_COMBINERS:
            raise ValueError(f"Unsupported boolean operator: {op_type.__name__}")
        return _BOOL_COMBINERS[op_type](_eval_node(v, variables) for v in node.values)
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise ValueError(f"Unknown variable in condition: {node.id!r}")
        return variables[node.id]
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    raise ValueError(f"Unsupported expression in condition: {ast.dump(node)}")


def _strip_diacritics(word: str) -> str:
    """Remove diacritics by splitting letters and their marks (NFD), then
    keep only the base letters. This is used for parse.strip_diacritics, so
    input typed without diacritics can still match lexicon words that
    include them ("sawm" -> "sâwm").
    """
    decomposed = unicodedata.normalize("NFD", word)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _normalize(word: str, parse_config: dict) -> str:
    """Apply the spec's parse flags to one word.

    Module-level rather than a method, because _validate_spec has to do this
    before there is a Spec to call it on -- and writing a second copy there
    would be the duplication #37 exists to remove. Spec._normalize_word is
    the method form of this and defers to it.
    """
    if parse_config.get("case_insensitive", False):
        word = word.lower()
    if parse_config.get("strip_diacritics", False):
        word = _strip_diacritics(word)
    return word


def _positional_variables(n: int) -> dict:
    return {
        "ones_digit": n % 10,
        "tens_digit": (n // 10) % 10,
    }


def _resolve_key(raw_key: str, variables: dict):
    """A placeholder's bracket key is either a positional variable name
    (e.g. "tens_digit") or a literal integer (e.g. scales[10])."""
    if raw_key in variables:
        return variables[raw_key]
    return int(raw_key)


def _render(output: str, lexicon: dict, variables: dict) -> str:
    def substitute(match: "re.Match") -> str:
        table_name, raw_key, field = match.groups()
        key = _resolve_key(raw_key, variables)
        return lexicon[table_name][key][field]

    return _PLACEHOLDER_RE.sub(substitute, output)


# The positional variable names a condition or a placeholder key may use.
# Derived from the function that defines them so the two cannot disagree.
_VARIABLE_NAMES = frozenset(_positional_variables(0))


def _validate_condition_node(node):
    """The allowlist for a `condition` expression, expressed once.

    Walks the whole tree rather than checking each node as it is evaluated.
    _eval_node's checks only fire on the nodes it actually reaches, and
    `and`/`or` short-circuit, so a subtree behind one was never visited and
    therefore never rejected -- which is how this engine came to accept
    expressions compile_spec.py refuses (#37). The trigger was never "an
    `or` is present"; it was "the operand that would have rejected it was
    not reached", which depends on the number being converted rather than
    on the spec.
    """
    if isinstance(node, ast.Compare):
        for op in node.ops:
            if type(op) not in _COMPARISONS:
                raise ValueError(f"Unsupported comparison operator: {type(op).__name__}")
        _validate_condition_node(node.left)
        for comparator in node.comparators:
            _validate_condition_node(comparator)
        return
    if isinstance(node, ast.BoolOp):
        if type(node.op) not in _BOOL_COMBINERS:
            raise ValueError(f"Unsupported boolean operator: {type(node.op).__name__}")
        for value in node.values:
            _validate_condition_node(value)
        return
    if isinstance(node, ast.Name):
        if node.id not in _VARIABLE_NAMES:
            raise ValueError(f"Unknown variable in condition: {node.id!r}")
        return
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return
    raise ValueError(f"Unsupported expression in condition: {ast.dump(node)}")


def _field_exists(lexicon: dict, table: str, field: str) -> bool:
    # At least one entry, not every entry: a language may carry an alternate
    # form for only some of its numerals.
    return any(field in entry for entry in lexicon[table].values())


def _validate_spec(data: dict) -> None:
    """Reject a malformed spec at load, in one traversal.

    Everything checked here is a cross-reference, or a constraint the JSON
    Schema structurally cannot express: it can say `accepted_forms` maps
    names to lists of names, not that those names exist in *this file's*
    lexicon. Each of these used to fail silently -- leniency quietly
    stopping, a connector quietly never certified, a literal quietly
    dropping out of matching -- and the hand-written cross-reference checks
    lived in test_spec_schema.py, which only sees the specs in languages/.
    A spec loaded from anywhere else got no warning at all.

    This is the oracle, so it rejects here rather than at the point of use:
    docs/architecture.md makes the engine the definition of correct, and a
    spec the engine accepts but the compiler refuses inverts that.

    Where the line sits. Structural validity -- that `rules` is a list, that
    a rule has a name and a two-integer range -- is spec.schema.json's job,
    and re-implementing it here would be the duplication this issue exists
    to remove. What this function adds is the part a schema cannot state:
    whether a name resolves, what is inside a condition, whether a literal
    can be matched, whether a range can ever fire. The few type checks below
    are not an exception to that: they guard only the fields this function
    itself parses or regexes, so that it returns a verdict rather than a
    TypeError from three calls down. A structurally malformed dict handed
    straight to Spec() can still surface as KeyError -- the schema is the
    gate for that, and every spec that reaches the engine by any supported
    route has been through it.
    """
    # Named rather than left to KeyError. The schema catches a missing section
    # in a checked-in spec, but a function called "validate" reporting
    # KeyError: 'lexicon' for the most basic malformation there is reads like
    # a crash rather than a verdict.
    for section in ("lexicon", "grammar"):
        if section not in data:
            raise ValueError(f"spec has no {section!r} section")
    if "rules" not in data["grammar"]:
        raise ValueError("spec has no 'grammar.rules'")

    lexicon = data["lexicon"]
    rules = data["grammar"]["rules"]
    parse = data.get("parse", {})

    # Schema-valid data never trips this -- output and condition are both
    # `type: string` there, and output is required. It exists for the same
    # reason the section check above does: Spec() can be built from a raw
    # dict with no schema in the loop, and without this a missing or
    # wrong-typed field reaches a KeyError from indexing or a TypeError three
    # calls down inside ast.parse or a regex, either of which this function
    # promises not to do. Found auditing #37 rather than filed against it.
    for rule in rules:
        name = rule.get("name", "<unnamed rule>")
        output = rule.get("output")
        if not isinstance(output, str):
            raise ValueError(
                f"rule {name!r}: 'output' must be a string, got "
                f"{type(output).__name__}"
            )
        condition = rule.get("condition")
        if condition is not None and not isinstance(condition, str):
            raise ValueError(
                f"rule {name!r}: 'condition' must be a string, got "
                f"{type(condition).__name__}"
            )
        for alias in rule.get("parse_aliases", []):
            if not isinstance(alias, str):
                raise ValueError(
                    f"rule {name!r}: each parse_aliases entry must be a "
                    f"string, got {type(alias).__name__}"
                )
        # An inverted range is the one thing about `range` the schema cannot
        # say: it can require two integers, not that the first is not larger
        # than the second. _find_rule tests `low <= n <= high`, so such a rule
        # never fires, and the only symptom is "No grammar rule matches n=..."
        # for whatever the rule was supposed to cover -- an error naming the
        # number rather than the rule that should have handled it.
        rule_range = rule.get("range")
        if isinstance(rule_range, list) and len(rule_range) == 2:
            low, high = rule_range
            if isinstance(low, int) and isinstance(high, int) and low > high:
                raise ValueError(
                    f"rule {name!r}: range is [{low}, {high}], which is empty, "
                    f"so the rule can never match"
                )

    separators = parse.get("word_separators", [" "])
    separator_pattern = "|".join(re.escape(sep) for sep in separators)
    connectors = {_normalize(c, parse) for c in parse.get("connectors", [])}

    for rule in rules:
        condition = rule.get("condition")
        if condition is None:
            continue
        try:
            _validate_condition_node(ast.parse(condition, mode="eval").body)
        except (ValueError, SyntaxError) as exc:
            raise ValueError(f"rule {rule['name']!r}: {exc}") from None

    # accepted_forms (#31) and connector_precedes (#19) have the same shape:
    # a lexicon table mapped to a list of its fields.
    for key in ("accepted_forms", "connector_precedes"):
        for table, fields in parse.get(key, {}).items():
            if table not in lexicon:
                raise ValueError(f"parse.{key}: unknown lexicon table {table!r}")
            for field in fields:
                if not _field_exists(lexicon, table, field):
                    raise ValueError(
                        f"parse.{key}: no {table} entry has a {field!r} field"
                    )
    # Declaring where a connector may stand, in a language with no connector,
    # is a mechanism nothing can exercise (#36, #38).
    if parse.get("connector_precedes") and not parse.get("connectors"):
        raise ValueError("parse.connector_precedes declared without any connectors")

    for rule in rules:
        for template in [rule["output"], *rule.get("parse_aliases", [])]:
            _validate_placeholders(rule["name"], template, lexicon)
            _validate_literals(
                rule["name"], template, separator_pattern, connectors, parse
            )


def _validate_placeholders(rule_name: str, template: str, lexicon: dict) -> None:
    """Every placeholder addresses something that is actually in the lexicon.

    Not in #37 as filed. Same shape as the cross-references above, reached by
    the same traversal, and the failure without it is a KeyError out of
    _render at conversion time rather than a message naming the rule.
    """
    for table, raw_key, field in _PLACEHOLDER_RE.findall(template):
        if table not in lexicon:
            raise ValueError(f"rule {rule_name!r}: unknown lexicon table {table!r}")
        if raw_key in _VARIABLE_NAMES:
            if not _field_exists(lexicon, table, field):
                raise ValueError(
                    f"rule {rule_name!r}: no {table} entry has a {field!r} field"
                )
            continue
        try:
            key = int(raw_key)
        except ValueError:
            raise ValueError(
                f"rule {rule_name!r}: placeholder key {raw_key!r} is neither a "
                f"positional variable nor an integer"
            ) from None
        if key not in lexicon[table]:
            raise ValueError(f"rule {rule_name!r}: {table}[{key}] is not in the lexicon")
        if field not in lexicon[table][key]:
            raise ValueError(
                f"rule {rule_name!r}: {table}[{key}] has no {field!r} field"
            )


def _validate_literals(
    rule_name: str, template: str, separator_pattern: str, connectors: set,
    parse_config: dict,
) -> None:
    """Every template literal is a word separator or a declared connector.

    _rule_matches compares placeholders and ignores literals, so a literal
    has to be something _tokenize also removes. A literal that is neither is
    emitted on output and matched on neither side, and the rule then rejects
    its own canonical output -- reproduced on #53, where a `"dâr {units[...]}"`
    rule renders 3 as `dâr pathum` and then fails to parse it, while bare
    `pathum` still parses. That breaks the round-trip property
    docs/architecture.md treats as non-negotiable.

    This is not a new restriction. It is the rule
    packages/python/tests/test_render_internals.py already asserts over the
    compiled Mizo rules, moved to load so it covers any spec rather than the
    checked-in ones. It is also a rule with a known expiry: #48 and #53 both
    need literals that carry meaning, and the engine change they share is
    exactly "require literals to be present, and segment bound ones". When
    the matcher learns that, this check narrows rather than disappears --
    and until it does, failing loudly here beats a spec that silently does
    not round-trip.
    """
    # _PLACEHOLDER_RE has three groups, so split() interleaves each literal
    # with its three captures: literal, table, key, field, literal, ...
    literals = _PLACEHOLDER_RE.split(template)[::4]
    placeholder_count = len(literals) - 1

    for position, literal in enumerate(literals):
        for word in (w for w in re.split(separator_pattern, literal) if w):
            if _normalize(word, parse_config) not in connectors:
                raise ValueError(
                    f"rule {rule_name!r}: template literal {word!r} is neither a "
                    f"word separator nor a connector, so it would be emitted on "
                    f"output and matched on neither side"
                )
        # A literal *between* two placeholders must also actually separate
        # them. Being a connector is not enough: "{a}leh{b}" renders the two
        # lexicon values run together as one token, so the arity check sees
        # one token against two placeholders and the rule cannot parse its
        # own output. Same for an empty literal, which is two placeholders
        # written adjacent -- the concatenation shape from #48.
        between = 0 < position < placeholder_count
        if between and not re.search(separator_pattern, literal):
            raise ValueError(
                f"rule {rule_name!r}: placeholders are joined by {literal!r}, "
                f"which contains no word separator, so they would render as a "
                f"single token and the rule could not parse its own output"
            )


def _find_rule(rules: list, n: int, variables: dict) -> dict:
    for rule in rules:
        low, high = rule["range"]
        if not (low <= n <= high):
            continue
        condition = rule.get("condition")
        if condition is not None and not _eval_condition(condition, variables):
            continue
        return rule
    raise ValueError(f"No grammar rule matches n={n}")


class Spec:
    """A loaded language spec, exposing number_to_text()."""

    def __init__(self, data: dict):
        # Validate here rather than in load(), so a Spec built straight from a
        # dict -- which the tests do constantly -- gets the same guarantee as
        # one read off disk.
        _validate_spec(data)
        self._data = data
        self.lexicon = data["lexicon"]
        self.rules = data["grammar"]["rules"]
        self.supports = data["meta"]["supports"]
        self.parse_config = data.get("parse", {})

    def number_to_text(self, n: int) -> str:
        if not (self.supports["min"] <= n <= self.supports["max"]):
            raise ValueError(
                f"{n} is outside the supported range "
                f"[{self.supports['min']}, {self.supports['max']}]"
            )
        variables = _positional_variables(n)
        rule = _find_rule(self.rules, n, variables)
        return _render(rule["output"], self.lexicon, variables)

    def text_to_number(self, text: str) -> int:
        # Collect every matching n rather than returning on the first hit.
        # This engine is the oracle -- the definition of correctness -- so an
        # ambiguous spelling (two numbers both accepting the same text) must
        # be a loud error, not a silent "whichever came first in the range."
        # There's no ambiguity today (verified across the full supported
        # range), but a future grammar change could introduce one, and this
        # is what would catch it.
        tokens = self._tokenize(text)
        matches = []
        for n in range(self.supports["min"], self.supports["max"] + 1):
            variables = _positional_variables(n)
            rule = _find_rule(self.rules, n, variables)
            templates = [rule["output"], *rule.get("parse_aliases", [])]
            if any(self._rule_matches(t, tokens, variables) for t in templates):
                matches.append(n)
        if not matches:
            raise ValueError(f"{text!r} does not match any number in the supported range")
        if len(matches) > 1:
            raise ValueError(f"{text!r} is ambiguous: matches {matches}")
        return matches[0]

    def _rule_matches(self, output: str, tokens: list, variables: dict) -> bool:
        placeholders = _PLACEHOLDER_RE.findall(output)
        if len(placeholders) != len(tokens):
            return False
        # Leniency (accepting either bound or standalone form) only applies
        # to a phrase that's a single freestanding digit -- e.g. "khat" as
        # well as "pakhat" for 1. A multi-word template (teens, exact_tens,
        # compound_tens, ...) must match each field exactly as named:
        # relaxing e.g. the tens-digit slot would let "sawm hnih" (20) also
        # match teens' ones-digit slot for 12, which is a real ambiguity,
        # not an accepted alternate spelling.
        lenient = len(placeholders) == 1
        return all(
            self._token_matches_entry(table, raw_key, field, variables, token, lenient)
            for (table, raw_key, field), token in zip(placeholders, tokens)
        )

    def _token_matches_entry(
        self, table: str, raw_key: str, field: str, variables: dict, token: str,
        lenient: bool,
    ) -> bool:
        """A token matches a placeholder if it equals the lexicon entry's
        value in the field the template names -- or, when `lenient`, any
        field accepted for that table (parse.accepted_forms).
        """
        key = _resolve_key(raw_key, variables)
        entry = self.lexicon[table][key]
        for candidate_field in self._acceptable_fields(table, field, lenient):
            value = entry.get(candidate_field)
            if value is not None and self._normalize_word(value) == token:
                return True
        return False

    def _acceptable_fields(self, table: str, default_field: str, lenient: bool) -> list:
        """Which lexicon fields a token may match for this placeholder.

        The field the template names always matches -- that is what
        number_to_text() emits, so it has to parse back. parse.accepted_forms
        widens that for the tables it names, and a spec that declares nothing
        gets exact matching. Listing the named field first also means a spec
        cannot break its own canonical spelling by leaving it out of the list
        (#31).

        Which table and which fields are eligible is spec data, not something
        this engine knows: Mizo declares `units: [bound]` -- the extra form
        only, `standalone` being the field its template names -- and English
        declares nothing because its entries have one form each.
        """
        if not lenient:
            return [default_field]
        eligible = self.parse_config.get("accepted_forms", {}).get(table, ())
        return [default_field] + [f for f in eligible if f != default_field]

    def _normalize_word(self, word: str) -> str:
        """Apply the same normalisation to *both* the input and the
        lexicon before comparing them. Each parse flag makes matching more
        flexible without changing the output of number_to_text(). The spec
        still keeps its original casing and diacritics; only the comparison
        is relaxed. Using one shared function keeps both sides consistent.
        If a flag were applied only to the input, it could stop matching the
        lexicon.
        """
        return _normalize(word, self.parse_config)

    def _tokenize(self, text: str) -> list:
        """Normalise text per the spec's `parse` section: apply the parse
        flags (see _normalize_word), split on word_separators, remove
        connector words, and resolve aliases. Mirrors docs/spec-format.md's
        description of the reverse direction ("drop connectors, resolve
        aliases").

        Connector words and aliases are normalised the same way, so they
        still match even if they are written differently in the spec.
        Otherwise, a connector with a diacritic would no longer be removed
        after strip_diacritics changed the input.
        """
        separators = self.parse_config.get("word_separators", [" "])
        pattern = "|".join(re.escape(sep) for sep in separators)
        words = [self._normalize_word(w) for w in re.split(pattern, text) if w]
        connectors = {
            self._normalize_word(c) for c in self.parse_config.get("connectors", [])
        }
        aliases = {
            self._normalize_word(variant): self._normalize_word(canonical)
            for variant, canonical in self.parse_config.get("aliases", {}).items()
        }
        return [aliases.get(w, w) for w in words if w not in connectors]

    @property
    def examples(self) -> list:
        return self._data.get("examples", [])


def load(path) -> Spec:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Spec(data)
