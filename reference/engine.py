"""Reference engine: interprets a language spec (languages/<lang>.yaml) to
convert numbers to text and back. This is the "oracle" described in
docs/architecture.md -- the definition of correctness that target packages
(Python, npm, ...) are checked against, instead of each reimplementing a
language's rules by hand.

The format it reads is the scale-keyed one from #65. Every rule is keyed by
the power of ten it consumes (`scale`), and sees two values derived from the
number and that scale:

    multiplier = n // scale
    remainder  = n %  scale

A rule's template names lexicon words through those two values
(`{units[multiplier].bound}`), and may hold `{remainder}`: the remainder,
rendered by the same rules. That one recursive placeholder is what the old
positional variables (ones_digit, tens_digit, hundreds_digit) could not
express, and it is why Mizo 0-999 needs 5 rules here where it needed 17.
A `[...]` segment is dropped when the remainder is zero -- CLDR RBNF's own
notation for the same thing (docs/spec-format.md, "Relationship to CLDR
RBNF").

number -> text: take the largest scale any emitting rule is keyed by that is
not above n, then the first rule at that scale whose fixed `multiplier` and
`condition` both hold (see Spec._find_rule). A connector declared under
`grammar.connector` is written before the final addend of the whole number,
which is the innermost {remainder} expansion (see Spec._render_rule).

text -> number: normalise the text using the spec's `parse` section (see
Spec._normalize_word), then parse it by recursive descent over the same
rules, collecting every value some derivation gives rather than stopping at
the first (see Spec._parse_readings). More than one is an error, except
where grammar.stacking lets a multiplier be a whole numeral: there the
multiplier binds greedily, and the reading whose stacked multiplier takes
in the most words wins (#27 rule 6). A freestanding single-word phrase
accepts either form parse.accepted_forms lists ("khat" as well as "pakhat"
for 1); inside a longer phrase every field must match exactly as the
template names it. A rule marked `emit: never` is accepted on input and
never produced, and `scope: whole` keeps it from being used as anybody's
remainder -- Mizo's `hnih thum` (23) is a whole phrase, not a way of writing
the last two words of `za hnih thum`.

Cost. The parser's loops are over the tokens of the input and the entries
of the lexicon, never over supports.max. Parsing used to brute-force the
supported range and template-match every candidate, which put the reference
suite at 16-20 minutes at 0-999 and was arithmetically impossible at 10^5
(#27, #65 requirement 2). Growing the range no longer changes what a parse
costs.
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
    """Evaluate a `condition` string like "multiplier > 1 and remainder > 0"
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

# The variables a condition or a placeholder key may name. Two, and they are
# the same two at every scale: that is what lets one rule describe every
# multiple of its scale instead of one rule per digit position (#65).
_VARIABLE_NAMES = frozenset({"multiplier", "remainder"})

# The one placeholder that is not a lexicon lookup: the remainder, rendered
# by the same rules. Only legal inside a [...] segment -- see _parse_template.
_REMAINDER = "remainder"


def _parse_template(template: str) -> tuple:
    """Split a template into items, the one representation the engine, the
    compiler and the package all read.

        "text"                          literal text, kept verbatim
        ("lex", table, key, field)      a lexicon word; key is "multiplier",
                                        "remainder" or an int
        ("remainder",)                  the remainder, rendered by the rules
        ("optional", items)             present exactly when remainder > 0

    A bracket opens an optional segment only outside a placeholder. Inside
    one it is the lexicon index: `{units[multiplier].bound}` holds a bracket
    that must not be read as `[...]`. The prototype for #65 got that wrong
    and rendered `{units.bound}`, so the scan below handles a whole
    placeholder at a time rather than looking at brackets character by
    character.

    Raises ValueError for anything malformed: an unbalanced bracket, a
    nested segment, a placeholder that is neither `{remainder}` nor
    `{table[key].field}`, or `{remainder}` outside a segment. The last one
    matters for output rather than syntax. Outside a segment, a remainder of
    zero would render the rules' word for zero ("bial") in the middle of a
    number.
    """
    stack = [[]]
    literal = []

    def flush():
        if literal:
            stack[-1].append("".join(literal))
            literal.clear()

    position = 0
    while position < len(template):
        ch = template[position]
        if ch == "{":
            end = template.find("}", position)
            if end < 0:
                raise ValueError(f"unclosed placeholder in {template!r}")
            body = template[position:end + 1]
            flush()
            if body == "{%s}" % _REMAINDER:
                if len(stack) == 1:
                    raise ValueError(
                        f"{{remainder}} outside a [...] segment in {template!r}: "
                        f"a zero remainder would render as a word"
                    )
                stack[-1].append((_REMAINDER,))
            else:
                match = _PLACEHOLDER_RE.fullmatch(body)
                if match is None:
                    raise ValueError(f"malformed placeholder {body!r} in {template!r}")
                table, raw_key, field = match.groups()
                if raw_key in _VARIABLE_NAMES:
                    key = raw_key
                else:
                    try:
                        key = int(raw_key)
                    except ValueError:
                        raise ValueError(
                            f"placeholder key {raw_key!r} is neither a variable "
                            f"({', '.join(sorted(_VARIABLE_NAMES))}) nor an integer"
                        ) from None
                stack[-1].append(("lex", table, key, field))
            position = end + 1
            continue
        if ch == "}":
            raise ValueError(f"stray '}}' in {template!r}")
        if ch == "[":
            if len(stack) > 1:
                raise ValueError(f"nested [...] segment in {template!r}")
            flush()
            stack.append([])
        elif ch == "]":
            if len(stack) == 1:
                raise ValueError(f"unbalanced ']' in {template!r}")
            flush()
            inner = stack.pop()
            stack[-1].append(("optional", tuple(inner)))
        else:
            literal.append(ch)
        position += 1
    if len(stack) > 1:
        raise ValueError(f"unclosed '[' in {template!r}")
    flush()
    return tuple(stack[0])


def _linearisations(items: tuple) -> list:
    """The template as it renders with its segment absent, then present.

    A template with no segment renders one way. Used by the literal check,
    which has to see every sequence of words a template can actually emit --
    a separator that exists only when the segment is present still has to
    separate what it sits between.
    """
    absent, present = [], []
    has_segment = False
    for item in items:
        if isinstance(item, tuple) and item[0] == "optional":
            has_segment = True
            present.extend(item[1])
        else:
            absent.append(item)
            present.append(item)
    return [absent, present] if has_segment else [absent]


def _refers_to_remainder(items: tuple) -> bool:
    """Whether items say anything about the remainder: `{remainder}` itself,
    a word keyed by it (English's teens), or a segment that does."""
    for item in items:
        if isinstance(item, str):
            continue
        if item[0] == _REMAINDER:
            return True
        if item[0] == "lex" and item[2] == _REMAINDER:
            return True
        if item[0] == "optional" and _refers_to_remainder(item[1]):
            return True
    return False


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
    stopping, a connector quietly never stripped, a literal quietly
    dropping out of matching -- and the hand-written cross-reference checks
    lived in test_spec_schema.py, which only sees the specs in languages/.
    A spec loaded from anywhere else got no warning at all.

    This is the oracle, so it rejects here rather than at the point of use:
    docs/architecture.md makes the engine the definition of correct, and a
    spec the engine accepts but the compiler refuses inverts that.

    Where the line sits. Structural validity -- that `rules` is a list, that
    a rule has a name and an integer scale -- is spec.schema.json's job, and
    re-implementing it here would be the duplication this issue exists to
    remove. What this function adds is the part a schema cannot state:
    whether a name resolves, what is inside a condition or a template,
    whether a literal can be matched. The few type checks below are not an
    exception to that: they guard only the fields this function itself
    parses or regexes, so that it returns a verdict rather than a TypeError
    from three calls down. A structurally malformed dict handed straight to
    Spec() can still surface as KeyError -- the schema is the gate for that,
    and every spec that reaches the engine by any supported route has been
    through it.
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

    # Schema-valid data never trips these -- output and condition are both
    # `type: string` there, and output is required. They exist for the same
    # reason the section check above does: Spec() can be built from a raw
    # dict with no schema in the loop, and without them a missing or
    # wrong-typed field reaches a KeyError from indexing or a TypeError three
    # calls down inside ast.parse, either of which this function promises
    # not to do.
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
        # `scope: whole` exists to keep a parse-only form from being read as
        # somebody's remainder. On a rule number_to_text() also uses, it
        # would let the renderer emit a remainder the parser then refuses to
        # read back -- a spec that fails its own round trip.
        if rule.get("scope") == "whole" and rule.get("emit") != "never":
            raise ValueError(
                f"rule {name!r}: 'scope: whole' is only meaningful on an "
                f"'emit: never' rule; on an emitted rule it would break the "
                f"round trip"
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

    for table, fields in parse.get("accepted_forms", {}).items():
        if table not in lexicon:
            raise ValueError(f"parse.accepted_forms: unknown lexicon table {table!r}")
        for field in fields:
            if not _field_exists(lexicon, table, field):
                raise ValueError(
                    f"parse.accepted_forms: no {table} entry has a {field!r} field"
                )

    # The connector number_to_text() writes has to be one text_to_number()
    # drops, or the canonical spelling of every number from `min` up fails
    # to parse back. Two declarations because they are two facts: English
    # drops "and" on input but emits it nowhere below 100.
    connector = data["grammar"].get("connector")
    if connector is not None:
        if _normalize(connector.get("word", ""), parse) not in connectors:
            raise ValueError(
                f"grammar.connector: {connector.get('word')!r} is not one of "
                f"parse.connectors, so the canonical spelling would not parse back"
            )

    # Read by Spec.__init__, so guarded here for the same reason as `output`
    # above: a raw dict should get a verdict, not a KeyError. `emit: never`
    # is the only value -- stacked forms are input-only (#27 rule 6) -- and
    # is required so a reader sees that at the declaration.
    stacking = data["grammar"].get("stacking")
    if stacking is not None:
        floor = stacking.get("accepted_from")
        if not isinstance(floor, int) or isinstance(floor, bool) or floor < 1:
            raise ValueError(
                f"grammar.stacking.accepted_from must be a positive integer, "
                f"got {floor!r}"
            )
        if stacking.get("emit") != "never":
            raise ValueError(
                "grammar.stacking.emit must be 'never': stacked forms are "
                "accepted on input and never written"
            )

    for rule in rules:
        name = _rule_name(rule)
        try:
            items = _parse_template(rule["output"])
        except ValueError as exc:
            raise ValueError(f"rule {name!r}: {exc}") from None
        _validate_readable(name, rule, items)
        _validate_placeholders(name, items, lexicon)
        for sequence in _linearisations(items):
            _validate_literals(name, sequence, separator_pattern, connectors, parse)


def _writes_multiplier(items: tuple) -> bool:
    """Whether a template writes its multiplier as a word outside any [...]
    segment -- the slot a parser reads the multiplier from, and the one
    grammar.stacking widens."""
    return any(
        not isinstance(item, str) and item[0] == "lex" and item[2] == "multiplier"
        for item in items
    )


def _validate_readable(rule_name: str, rule: dict, items: tuple) -> None:
    """Two ways a template can render and still not be readable back.

    A rule has to write its multiplier down or fix it. A parser learns the
    multiplier from the word it reads, and a rule that writes none -- Mizo's
    bare "sâwm" -- gives it nothing, while a condition such as
    "multiplier == 1" can only check a value it has already been given. The
    rules first proposed for #65 did exactly that for `ten` and `hundred`,
    and 190 of the 1,000 shipped spellings rendered correctly and then parsed
    to nothing. Only a word outside a [...] segment counts, since a segment
    is absent whenever the remainder is zero.

    And a [...] segment has to render the remainder, through `{remainder}` or
    a remainder-keyed word. It is present exactly when the remainder is
    nonzero, so one that says nothing about the remainder -- `[ leh]` --
    has nowhere to put it. Spec._render_rule refuses such a number rather
    than drop the remainder and name a smaller one, but only when one is
    converted; this says so at load, for all of them.
    """
    if not _writes_multiplier(items) and "multiplier" not in rule:
        raise ValueError(
            f"rule {rule_name!r} never writes its multiplier and does not fix "
            f"one, so text_to_number could never read it: give it "
            f"`multiplier: <n>`, not a condition (#65)"
        )
    for item in items:
        if isinstance(item, tuple) and item[0] == "optional":
            if not _refers_to_remainder(item[1]):
                raise ValueError(
                    f"rule {rule_name!r}: a [...] segment never renders the "
                    f"remainder, so a nonzero remainder would be dropped from "
                    f"the output"
                )


def _validate_placeholders(rule_name: str, items: tuple, lexicon: dict) -> None:
    """Every lexicon placeholder addresses something that is actually in the
    lexicon. The failure without it is a KeyError out of rendering at
    conversion time rather than a message naming the rule.
    """
    for item in items:
        if isinstance(item, str) or item[0] == _REMAINDER:
            continue
        if item[0] == "optional":
            _validate_placeholders(rule_name, item[1], lexicon)
            continue
        _, table, key, field = item
        if table not in lexicon:
            raise ValueError(f"rule {rule_name!r}: unknown lexicon table {table!r}")
        if key in _VARIABLE_NAMES:
            if not _field_exists(lexicon, table, field):
                raise ValueError(
                    f"rule {rule_name!r}: no {table} entry has a {field!r} field"
                )
            continue
        if key not in lexicon[table]:
            raise ValueError(f"rule {rule_name!r}: {table}[{key}] is not in the lexicon")
        if field not in lexicon[table][key]:
            raise ValueError(
                f"rule {rule_name!r}: {table}[{key}] has no {field!r} field"
            )


def _validate_literals(
    rule_name: str, sequence: list, separator_pattern: str, connectors: set,
    parse_config: dict,
) -> None:
    """Every template literal is a separator or connector, and separates.

    Checked over each way the template can render (see _linearisations),
    with `{remainder}` counting as a placeholder: it renders to words too.

    Two clauses, and the second is the one with teeth. The parser matches
    placeholders and skips literals, so a literal has to be something
    _tokenize also removes. A literal that is neither is emitted on output
    and matched on neither side, and the rule then rejects its own canonical
    output -- reproduced on #53, where a `"dâr {units[...]}"` rule renders 3
    as `dâr pathum` and then fails to parse it, while bare `pathum` still
    parses. That breaks the round-trip property docs/architecture.md treats
    as non-negotiable.

    Being removable is necessary and not sufficient. A literal must also put
    a separator at every boundary where a placeholder abuts it, or the two
    render as one token and can never be matched. `leh` is a declared
    connector and every one of `"leh{a}"`, `"{a}leh"`, `"{a} leh{b}"` and
    `"{a}leh {b}"` satisfies the first clause while failing to parse its own
    output.

    It is also a rule with a known expiry: #48 and #53 both need literals
    that carry meaning, and the engine change they share is exactly
    "require literals to be present, and segment bound ones". When the
    matcher learns that, this check narrows rather than disappears -- and
    until it does, failing loudly here beats a spec that silently does not
    round-trip.
    """
    # Adjacent literals cannot arise from _parse_template, but a segment
    # boundary can put a literal from outside next to one from inside ("x[ y"
    # renders "x y"); merge them so each boundary is judged as rendered.
    literals = [""]
    for item in sequence:
        if isinstance(item, str):
            literals[-1] += item
        else:
            literals.append("")
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


class Spec:
    """A loaded language spec, exposing number_to_text() and text_to_number()."""

    def __init__(self, data: dict):
        # Validate here rather than in load(), so a Spec built straight from a
        # dict -- which the tests do constantly -- gets the same guarantee as
        # one read off disk.
        _validate_spec(data)
        self._data = data
        self.lexicon = data["lexicon"]
        self.rules = data["grammar"]["rules"]
        self.connector = data["grammar"].get("connector")
        self.supports = data["meta"]["supports"]
        self.parse_config = data.get("parse", {})
        # Parsed once here rather than on every conversion. Keyed by identity
        # because two rules may be equal as dicts and still be two rules.
        self._items = {id(rule): _parse_template(rule["output"]) for rule in self.rules}
        # Conditions are parsed once, for the same reason: ast.parse on every
        # evaluation cost more than the whole rest of a parse in the #65
        # prototype, and nearly hid how cheap the algorithm is.
        self._conditions = {
            id(rule): ast.parse(rule["condition"], mode="eval").body
            for rule in self.rules
            if rule.get("condition") is not None
        }
        # The scales number_to_text() chooses between, largest first.
        self._emitting_scales = sorted(
            {rule["scale"] for rule in self.rules if rule.get("emit") != "never"},
            reverse=True,
        )
        # The rules whose multiplier slot also takes a whole numeral on input
        # (grammar.stacking, #27 rule 6). See _parse_readings.
        stacking = data["grammar"].get("stacking")
        self._stacking_rules = {
            id(rule) for rule in self.rules
            if stacking is not None
            and rule["scale"] >= stacking["accepted_from"]
            and _writes_multiplier(self._items[id(rule)])
        }

    # --- number -> text --------------------------------------------------

    def _rule_applies(self, rule: dict, multiplier: int, remainder: int) -> bool:
        """A rule's fixed `multiplier`, if it declares one, and its condition.

        A fixed multiplier is a value, not a test. That is the difference that
        matters for parsing: `condition: "multiplier == 1"` can check a
        multiplier the parser already has, but cannot give it one, and a rule
        like Mizo's `ten` never writes its multiplier down -- `sâwm` is 10
        with no digit in sight. Under the rules as first proposed for #65, 190
        of the 1,000 shipped spellings parsed to nothing for exactly this
        reason.
        """
        if "multiplier" in rule and rule["multiplier"] != multiplier:
            return False
        tree = self._conditions.get(id(rule))
        if tree is None:
            return True
        return _eval_node(tree, {"multiplier": multiplier, "remainder": remainder})

    def _find_rule(self, n: int) -> dict:
        """The rule number_to_text() renders n with.

        The largest emitting scale that is not above n -- 0 falls to the
        smallest, since there is no scale below it -- then the first rule at
        that scale, in spec order, that applies. Spec order only breaks ties
        between rules of the same scale, which is where a language's ×1
        behaviour lives: Mizo's `ten` (bare `sâwm`) and `tens` (`sawm hnih`)
        are both scale 10.
        """
        scale = next(
            (s for s in self._emitting_scales if s <= max(n, 1)),
            self._emitting_scales[-1] if self._emitting_scales else None,
        )
        if scale is not None:
            multiplier, remainder = divmod(n, scale)
            for rule in self.rules:
                if rule["scale"] != scale or rule.get("emit") == "never":
                    continue
                if self._rule_applies(rule, multiplier, remainder):
                    return rule
        raise ValueError(f"No grammar rule matches n={n}")

    def _render_rule(self, rule: dict, n: int) -> tuple:
        """Render n with `rule`, before any connector goes in.

        Returns (text, boundaries), where boundaries are the offsets at which
        each {remainder} expansion starts, outermost first. They are where the
        number's addends begin: 128 is `zâ` + `sawm hnih` + `pariat`, and the
        last boundary is the final addend, which is where a connector goes.
        The vector generator reads the others, since they are the gaps a
        speaker may also put `leh` in.
        """
        multiplier, remainder = divmod(n, rule["scale"])
        if remainder and not _refers_to_remainder(self._items[id(rule)]):
            # A rule that cannot say anything about a nonzero remainder would
            # drop it silently, and the output would name a smaller number.
            raise ValueError(
                f"rule {rule['name']!r} has no way to render a remainder, "
                f"but n={n} leaves {remainder}"
            )
        parts = []
        boundaries = []

        def walk(items):
            for item in items:
                if isinstance(item, str):
                    parts.append(item)
                elif item[0] == "lex":
                    _, table, key, field = item
                    value = {"multiplier": multiplier, "remainder": remainder}.get(key, key)
                    if value not in self.lexicon[table]:
                        # The likeliest way here is supports.max raised past
                        # the rules: 1,000 with nothing above scale 100 asks
                        # for the hundreds digit 10. Name the rule and the
                        # word rather than surface KeyError: 10.
                        raise ValueError(
                            f"rule {rule['name']!r} needs {table}[{value}] to "
                            f"render n={n}, and the lexicon has no such entry"
                        )
                    parts.append(self.lexicon[table][value][field])
                elif item[0] == _REMAINDER:
                    start = sum(len(p) for p in parts)
                    sub_text, sub_boundaries = self._render_rule(
                        self._find_rule(remainder), remainder
                    )
                    boundaries.append(start)
                    boundaries.extend(start + b for b in sub_boundaries)
                    parts.append(sub_text)
                elif remainder:                     # ("optional", items)
                    walk(item[1])

        walk(self._items[id(rule)])
        return "".join(parts), boundaries

    def _with_connector(self, n: int, text: str, boundaries: list) -> str:
        """Write grammar.connector before the final addend, when n needs one.

        Decision (#27 Q-M): Mizo writes `leh` before the final addend of every
        number from 100 up, and nowhere else. That is a property of the whole
        number rather than of a rule, which is why it is declared once instead
        of written into ten of the old seventeen templates. The final addend
        is the innermost {remainder}: 130 is `zâ leh sawm thum`, 128 is `zâ
        sawm hnih leh pariat`.

        The connector is followed by a space, the first joinable separator
        (_joinable_separators); the boundary it goes in front of already
        follows one, since a literal before `{remainder}` has to separate.
        """
        if self.connector is None or n < self.connector["min"] or not boundaries:
            return text
        at = boundaries[-1]
        return text[:at] + self.connector["word"] + " " + text[at:]

    def number_to_text(self, n: int) -> str:
        if not (self.supports["min"] <= n <= self.supports["max"]):
            raise ValueError(
                f"{n} is outside the supported range "
                f"[{self.supports['min']}, {self.supports['max']}]"
            )
        text, boundaries = self._render_rule(self._find_rule(n), n)
        return self._with_connector(n, text, boundaries)

    # --- text -> number --------------------------------------------------

    def text_to_number(self, text: str) -> int:
        # Collect every reading rather than returning on the first derivation.
        # This engine is the oracle -- the definition of correctness -- so an
        # ambiguous spelling (two numbers both accepting the same text) must
        # be a loud error, not a silent "whichever the parser found first".
        #
        # The one ambiguity the grammar resolves is stacking's, by greedy
        # binding (#27, Decision 1 of 2026-08-30): `nuai za hnih sawm nga` is
        # 250 x 10^5, not 200 x 10^5 + 50, because a scale word's multiplier
        # takes in as much as it can. _parse_readings ranks each reading by
        # that, and the top rank wins. Two readings tied at the top is still
        # an error, and so is every ambiguity that does not involve stacking,
        # since only stacking rules contribute to a rank.
        #
        # The range is applied to the winner, not before choosing one. A
        # greedy reading above supports.max is refused rather than replaced by
        # a shorter reading that fits: that would answer with a number the
        # speaker did not say. At 10^10 - 1 the case cannot arise -- every
        # shorter multiplier starts with the same scale word and is as far out
        # of range -- and test_engine pins that rather than trusting it.
        readings = self._parse_readings(text)
        if not readings:
            raise ValueError(f"{text!r} does not match any number in the supported range")
        top = max(readings.values())
        winners = sorted(n for n, rank in readings.items() if rank == top)
        if len(winners) > 1:
            raise ValueError(f"{text!r} is ambiguous: matches {winners}")
        n = winners[0]
        if not (self.supports["min"] <= n <= self.supports["max"]):
            raise ValueError(
                f"{text!r} reads as {n}, outside the supported range "
                f"[{self.supports['min']}, {self.supports['max']}]"
            )
        return n

    def _parse_values(self, text: str) -> set:
        """Every number in range that some reading of `text` gives, before
        greedy binding chooses between them: the ungreedy enumeration #65
        asks the ambiguity tests to run against. text_to_number never uses
        it -- greed would make it 1 by construction.
        """
        low, high = self.supports["min"], self.supports["max"]
        return {n for n in self._parse_readings(text) if low <= n <= high}

    def _parse_readings(self, text: str) -> dict:
        """Every number some derivation of `text` gives, mapped to the rank
        greedy binding gives its best derivation. The range is not applied.

        Recursive descent over the rules, memoised on (start, end, whole,
        below): `whole` is whether the span is the entire input, which is
        what `scope: whole` asks, and `below` skips rules at or above a
        scale. For a remainder that is pruning: it must also come out
        smaller than the scale (`0 < value < rule["scale"]` below), which
        alone rejects a derivation through a larger rule. For a stacked
        multiplier it is the descending order #27 requires -- `nuai za hnih`,
        never `nuai maktaduai khat` -- though at 10^10 - 1 any ascending
        reading is out of range anyway.

        A rank is a tuple, compared like a word in a dictionary. A stacking
        rule contributes how many words its multiplier took, then its
        multiplier's rank, then its remainder's: the outermost multiplier
        that reaches further wins, and only a tie there looks inside. Any
        other rule contributes its remainder's rank only, so a reading never
        outranks another for a reason that has nothing to do with stacking.

        Literals in a template are skipped, because every one is a separator
        or a connector (_validate_literals), and _tokenize has already
        removed both.
        """
        tokens = self._tokenize(text)
        if not tokens:
            return {}
        # Leniency (accepting either form parse.accepted_forms lists) applies
        # only to a phrase that is a single freestanding word -- "khat" as
        # well as "pakhat" for 1. Relaxing a slot inside a longer phrase would
        # let "sawm hnih" (20) also read as 10 + 2 through the bound form of
        # 2, which is real ambiguity rather than an alternate spelling.
        lenient = len(tokens) == 1
        cache = {}

        def span(start, end, whole, below):
            key = (start, end, whole, below)
            if key not in cache:
                readings = {}
                for rule in self.rules:
                    if below is not None and rule["scale"] >= below:
                        continue
                    if rule.get("scope") == "whole" and not whole:
                        continue
                    initial = {}
                    if "multiplier" in rule:
                        initial["multiplier"] = rule["multiplier"]
                    for bound in match(self._items[id(rule)], start, end, initial, rule, whole):
                        if "multiplier" not in bound:
                            continue
                        multiplier = bound["multiplier"]
                        remainder = bound.get("remainder", 0)
                        if not self._rule_applies(rule, multiplier, remainder):
                            continue
                        rank = bound.get("_remainder_rank", ())
                        if id(rule) in self._stacking_rules:
                            rank = (
                                (bound.get("_multiplier_words", 0),)
                                + bound.get("_multiplier_rank", ())
                                + rank
                            )
                        value = multiplier * rule["scale"] + remainder
                        if value not in readings or rank > readings[value]:
                            readings[value] = rank
                cache[key] = readings
            return cache[key]

        def bind(bound, name, value):
            if bound.get(name, value) != value:
                return None
            return {**bound, name: value}

        def match(items, position, end, bound, rule, whole):
            """Yield every binding under which `items` consume exactly
            tokens[position:end]."""
            if not items:
                if position == end:
                    yield bound
                return
            item, rest = items[0], items[1:]
            if isinstance(item, str):
                yield from match(rest, position, end, bound, rule, whole)
            elif item[0] == "lex":
                if position >= end:
                    return
                _, table, key, field = item
                token = tokens[position]
                if isinstance(key, int):
                    if self._normalize_word(self.lexicon[table][key][field]) == token:
                        yield from match(rest, position + 1, end, bound, rule, whole)
                    return
                # Two gates, each a backstop for the other: `lenient` (the
                # input is one word) and `whole` (this span is the input). On
                # today's data either alone is enough -- a one-word input has
                # no room for a remainder, and the only rule that can match a
                # whole input through a lenient table is the one-word units
                # rule -- so removing one is caught by no test. Removing both
                # is caught at once: "sawm hnih" then reads as 12 (sâwm + a
                # lenient "hnih") as well as 20, and the vectors stop generating.
                stacks = key == "multiplier" and id(rule) in self._stacking_rules
                fields = self._acceptable_fields(table, field, lenient and whole)
                for entry_key, entry in self.lexicon[table].items():
                    if any(
                        f in entry and self._normalize_word(entry[f]) == token
                        for f in fields
                    ):
                        rebound = bind(bound, key, entry_key)
                        if rebound is not None:
                            if key == "multiplier":
                                rebound["_multiplier_words"] = 1
                            yield from match(rest, position + 1, end, rebound, rule, whole)
                if stacks:
                    # Stacking (#27 rule 6): the multiplier may instead be a
                    # whole numeral read by these same rules -- "nuai za hnih"
                    # is 10^5 x 200. Only a numeral the word slot cannot hold:
                    # a single digit is the ordinary multiplier and takes the
                    # bound form, so "vaibêlchhe pahnih" is not 2 x 10^7 (Q-L).
                    for stop in range(position + 1, end + 1):
                        for value, rank in span(position, stop, False, rule["scale"]).items():
                            if value in self.lexicon[table]:
                                continue
                            rebound = bind(bound, "multiplier", value)
                            if rebound is not None:
                                rebound["_multiplier_words"] = stop - position
                                rebound["_multiplier_rank"] = rank
                                yield from match(rest, stop, end, rebound, rule, whole)
            elif item[0] == _REMAINDER:
                for stop in range(position + 1, end + 1):
                    for value, rank in span(position, stop, False, rule["scale"]).items():
                        if 0 < value < rule["scale"]:
                            rebound = bind(bound, "remainder", value)
                            if rebound is not None:
                                rebound["_remainder_rank"] = rank
                                yield from match(rest, stop, end, rebound, rule, whole)
            elif item[0] == "optional":
                # Absent: the remainder is zero.
                rebound = bind(bound, "remainder", 0)
                if rebound is not None:
                    yield from match(rest, position, end, rebound, rule, whole)
                # Present: the remainder is not.
                yield from match(
                    item[1] + (("end_optional",),) + rest,
                    position, end, bound, rule, whole,
                )
            elif item[0] == "end_optional":
                if bound.get("remainder", 0) > 0:
                    yield from match(rest, position, end, bound, rule, whole)

        return dict(span(0, len(tokens), True, None))

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
