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


# Unicode's White_Space property, enumerated.
#
# Decision (#46): whitespace is a property of text rather than of a language,
# so the engine treats it as a separator everywhere and specs declare only
# their non-whitespace separators. The property is named rather than delegated
# to a runtime's convenience function because neither runtime's is correct,
# and they are wrong in opposite directions: Python's str.isspace() -- and
# re's \s, which matches it exactly -- also accepts U+001C-U+001F, while
# JavaScript's \s also accepts U+FEFF. A target implementing "whatever my
# standard library calls whitespace" would diverge from one implementing the
# property, and no conformance vector could see it: every accepted_input is
# built by joining words with a separator the generator chose, so none of them
# contains an exotic space.
#
# Enumerated rather than derived, because deriving it means testing every code
# point, which costs ~150 ms at import. test_engine.py pins this against
# str.isspace() so that a Unicode update fails loudly rather than drifting.
_WHITESPACE = (
    "\t\n\v\f\r"                            # U+0009-U+000D
    " "                                     # U+0020 SPACE
    "\x85"                                  # U+0085 NEXT LINE
    "\xa0"                                  # U+00A0 NO-BREAK SPACE
    "\u1680"                                # U+1680 OGHAM SPACE MARK
    "\u2000\u2001\u2002\u2003\u2004\u2005"
    "\u2006\u2007\u2008\u2009\u200a"        # U+2000-U+200A
    "\u2028"                                # U+2028 LINE SEPARATOR
    "\u2029"                                # U+2029 PARAGRAPH SEPARATOR
    "\u202f"                                # U+202F NARROW NO-BREAK SPACE
    "\u205f"                                # U+205F MEDIUM MATHEMATICAL SPACE
    "\u3000"                                # U+3000 IDEOGRAPHIC SPACE
)


def _separator_pattern(parse_config: dict) -> str:
    """A regex alternation matching one effective separator.

    The effective set is whatever the spec declares plus Unicode whitespace.
    Everything that splits or validates text goes through here rather than
    reading parse.word_separators directly, so a spec declaring only "-"
    still splits on spaces.

    Declared separators come first so that a multi-character one is tried
    before a single whitespace character that could match inside it.
    """
    declared = parse_config.get("word_separators", [])
    whitespace = "".join(re.escape(ch) for ch in _WHITESPACE)
    return "|".join([*(re.escape(sep) for sep in declared), f"[{whitespace}]"])


def _joinable_separators(parse_config: dict) -> list:
    """The effective separators as concrete strings, for code that builds
    text rather than splitting it.

    A character property cannot be joined with, so U+0020 stands in for
    whitespace. It comes first because the vector generator falls back to
    the first entry when no separator reproduces a rendering -- which is
    every single-word rendering, where they all do -- and a space is the
    right canonical joiner there for both current specs.

    That ordering is currently a claim rather than an observable: both
    orders regenerate vectors/mizo.json byte-identical, because a
    single-word rendering has no gap to join and so grows no separator
    variant. It is pinned directly in test_engine.py rather than left for
    the artifact to prove, on #36's precedent -- an invariant that cannot
    currently fail is still worth stating, provided the limit is written
    down.
    """
    declared = parse_config.get("word_separators", [])
    return [" ", *(sep for sep in declared if sep != " ")]


# Zero-width and format characters, removed from every word before it is
# compared.
#
# Decision (#46): strip, rather than treat as a separator or reject. The
# dominant real case is a BOM at position 0 -- a file read as utf-8-sig, a
# Windows copy-paste -- where stripping and separating behave identically.
# The exotic cases decide it: rejecting is hostile, because the string looks
# correct in a terminal and the caller did not put the character there, and
# calling one a separator asserts a boundary meaning these characters do not
# have. The one case where separator would win, U+200B as the only thing
# between two words, does not arise in Latin-script Mizo.
#
# An explicit list rather than the Default_Ignorable_Code_Point property,
# which covers exactly these six for our purposes but needs the third-party
# regex package to test in Python -- and this library is deliberately
# dependency-free. Hardcoding that property's table instead would reintroduce
# the problem #46 exists to remove: it changes between Unicode versions, so
# two targets built against different versions would disagree. Six characters
# covers anything realistic and cannot drift.
_IGNORABLE = {
    ord(ch): None
    for ch in (
        "\u200b"    # ZERO WIDTH SPACE
        "\ufeff"    # ZERO WIDTH NO-BREAK SPACE / BOM
        "\u2060"    # WORD JOINER
        "\u200c"    # ZERO WIDTH NON-JOINER
        "\u200d"    # ZERO WIDTH JOINER
        "\u00ad"    # SOFT HYPHEN
    )
}


def _normalize(word: str, parse_config: dict) -> str:
    """Apply the spec's parse flags to one word.

    Module-level rather than a method, because _validate_spec has to do this
    before there is a Spec to call it on -- and writing a second copy there
    would be the duplication #37 exists to remove. Spec._normalize_word is
    the method form of this and defers to it.

    The ignorable-character strip is unconditional rather than a parse
    flag, for the same reason whitespace is (#46): it is a property of
    text, not of a language. It runs first so the flags below see the
    word a reader would.
    """
    word = word.translate(_IGNORABLE)
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


def _rule_name(rule: dict) -> str:
    """The name to blame in an error message, or a stand-in.

    A rule with no name is a schema violation, so this default should be
    unreachable through any supported route. It exists because _validate_spec
    promises a verdict: reporting KeyError('name') from inside a function
    called "validate" reads as a crash rather than an answer. Defined once
    because three separate loops need it, and three copies of the fallback
    string is the duplication #37 is about, in miniature.
    """
    return rule.get("name", "<unnamed rule>")


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
        name = _rule_name(rule)
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

    separator_pattern = _separator_pattern(parse)
    connectors = {_normalize(c, parse) for c in parse.get("connectors", [])}

    for rule in rules:
        condition = rule.get("condition")
        if condition is None:
            continue
        try:
            _validate_condition_node(ast.parse(condition, mode="eval").body)
        except (ValueError, SyntaxError) as exc:
            raise ValueError(f"rule {_rule_name(rule)!r}: {exc}") from None

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
        name = _rule_name(rule)
        for template in [rule["output"], *rule.get("parse_aliases", [])]:
            _validate_placeholders(name, template, lexicon)
            _validate_literals(
                name, template, separator_pattern, connectors, parse
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
    """Every template literal is a separator or connector, and separates.

    Two clauses, and the second is the one with teeth. _rule_matches
    compares placeholders and ignores literals, so a literal has to be
    something _tokenize also removes. A literal that is neither is emitted
    on output and matched on neither side, and the rule then rejects its own
    canonical output -- reproduced on #53, where a `"dâr {units[...]}"` rule
    renders 3 as `dâr pathum` and then fails to parse it, while bare `pathum`
    still parses. That breaks the round-trip property docs/architecture.md
    treats as non-negotiable.

    Being removable is necessary and not sufficient. A literal must also put
    a separator at every boundary where a placeholder abuts it, or the two
    render as one token and the arity check can never match. `leh` is a
    declared connector and every one of `"leh{a}"`, `"{a}leh"`, `"{a} leh{b}"`
    and `"{a}leh {b}"` satisfies the first clause while failing to parse its
    own output.

    The first clause is not a new restriction: it is the rule
    packages/python/tests/test_render_internals.py already asserts over the
    compiled Mizo rules, moved to load so it covers any spec rather than the
    checked-in ones. The second is new, and that test is deliberately left
    alone -- it reads the compiled Mizo rules, which cannot exhibit any of
    the four shapes above, so strengthening it there would assert something
    no input can violate. The boundary rule belongs where a spec arrives.

    It is also a rule with a known expiry: #48 and #53 both need literals
    that carry meaning, and the engine change they share is exactly
    "require literals to be present, and segment bound ones". When
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
        # Being a connector is not enough: a literal also has to separate the
        # placeholders it abuts, and that invariant is per *boundary* rather
        # than per literal. "Is a separator present somewhere in this literal"
        # passes "{a} leh{b}" on the strength of the space on the left while
        # the right-hand boundary still renders run together, and it never
        # looks at an edge literal at all. So each side is asked separately:
        # a placeholder on the left needs the literal to begin with a
        # separator, a placeholder on the right needs it to end with one.
        #
        # An empty literal at either edge is just a template that starts or
        # ends with a placeholder. Between two placeholders it is adjacency,
        # and it fails both clauses -- the concatenation shape from #48.
        #
        # separator_pattern is a bare alternation, so the end-anchored search
        # needs the non-capturing group: re.search(r"\ |\-$", s) parses as
        # (space anywhere) OR (dash at the end), which is true of any literal
        # containing a space. re.match does not need it -- every branch is
        # anchored at the start already -- but it is written the same way so
        # that the two read alike and neither invites the mistake.
        if not literal and position in (0, placeholder_count):
            continue
        if position > 0 and not re.match(f"(?:{separator_pattern})", literal):
            raise ValueError(
                f"rule {rule_name!r}: template literal {literal!r} does not "
                f"begin with a word separator, so it renders run together "
                f"with the placeholder on its left as a single token and the "
                f"rule could not parse its own output"
            )
        if position < placeholder_count and not re.search(
            f"(?:{separator_pattern})$", literal
        ):
            raise ValueError(
                f"rule {rule_name!r}: template literal {literal!r} does not "
                f"end with a word separator, so it renders run together with "
                f"the placeholder on its right as a single token and the rule "
                f"could not parse its own output"
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
        flags (see _normalize_word), split on the effective separators
        (_separator_pattern: declared plus Unicode whitespace), remove
        connector words, and resolve aliases. Mirrors docs/spec-format.md's
        description of the reverse direction ("drop connectors, resolve
        aliases").

        Connector words and aliases are normalised the same way, so they
        still match even if they are written differently in the spec.
        Otherwise, a connector with a diacritic would no longer be removed
        after strip_diacritics changed the input.
        """
        pattern = _separator_pattern(self.parse_config)
        # Filter after normalising, not before. A split piece holding only
        # an ignorable character is truthy on the way in and empty on the
        # way out, so filtering the raw piece lets "" into the token list,
        # where it matches nothing and the whole phrase is rejected -- which
        # would be rejecting a standalone ignorable rather than stripping it,
        # against the decision on #46. A token that is run together with a
        # word is unaffected: it does not normalise to empty.
        words = [
            word
            for word in (self._normalize_word(w) for w in re.split(pattern, text))
            if word
        ]
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
