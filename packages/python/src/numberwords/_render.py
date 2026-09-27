"""Interprets the compiled spec in _mizo.py.

This is the target-side counterpart to reference/engine.py. The engine reads
languages/mizo.yaml and is the oracle -- the definition of correct. This
module reads the compiled artifact instead, so the shipped package needs
neither PyYAML nor the spec file at runtime (#20). The two are kept honest
by vectors/mizo.json: the engine generates it, this module is tested against
it, and neither imports the other.

Deliberately boring. Every behaviour here exists because the engine has it,
and the comments say which decision each one implements rather than
restating the code.

Python 3.9 is the floor (pyproject's requires-python), so nothing newer than
3.9 syntax appears here.
"""

import re
import unicodedata

from ._mizo import CONNECTOR, LEXICON, PARSE, RULES, SUPPORTS


class NumberWordsError(ValueError):
    """Raised for a number outside the supported range, for text that does
    not name a number in it, and for an argument of the wrong type.

    Subclasses ValueError because that is what the failure usually is -- a
    bad value -- and callers who already write `except ValueError` keep
    working. The wrong-type case is folded in here rather than raised as
    TypeError so that the two public functions have exactly one failure
    mode to document and to catch. Re-exported from the package root; that
    is the public name.
    """


# --- Parsing constants ------------------------------------------------------
#
# The spec-derived ones the engine recomputes on every call, because it can
# be handed a new spec at any time. Here the spec is compiled in and cannot
# change, so they are built once at import. Same values, computed once.
#
# _WHITESPACE and _IGNORABLE are not spec-derived at all: since #46 they are
# properties of text that every language shares, so they are stated here
# rather than read out of the compiled spec.

# Unicode's White_Space property, enumerated. The engine's _WHITESPACE, and
# it has to be stated here rather than read out of the compiled spec: after
# #46 a spec declares only its non-whitespace separators, so
# PARSE["word_separators"] is ("-",) and a renderer trusting it alone would
# silently stop splitting on spaces.
#
# Neither runtime's convenience function is this set. Python's str.isspace()
# -- and re's \s, which matches it exactly -- also accepts U+001C-U+001F;
# JavaScript's \s also accepts U+FEFF. Implementing the named property is
# what keeps two targets agreeing, and no conformance vector can check it:
# every accepted_input is built by joining words with a separator the
# generator chose, so none contains an exotic space. tests/ pins this
# against str.isspace() on this side too.
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

_WHITESPACE_CLASS = "[{}]".format("".join(re.escape(ch) for ch in _WHITESPACE))

# Declared separators first, so a multi-character one is tried before a
# single whitespace character that could match inside it.
_SEPARATOR_RE = re.compile(
    "|".join(
        [
            *(re.escape(sep) for sep in PARSE.get("word_separators", ())),
            _WHITESPACE_CLASS,
        ]
    )
)


# Zero-width and format characters, removed from every word before it is
# compared.
#
# The engine decision (#46): strip, rather than treat as a separator or
# reject. The dominant real case is a BOM at position 0 -- a file read as
# utf-8-sig, a Windows copy-paste -- where stripping and separating behave
# identically. The exotic cases decide it: rejecting is hostile, because the
# string looks correct in a terminal and the caller did not put the character
# there, and calling one a separator asserts a boundary meaning these
# characters do not have. The one case where separator would win, U+200B as
# the only thing between two words, does not arise in Latin-script Mizo.
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


def _normalize_word(word: str) -> str:
    """Apply the parse flags to a single word.

    Applied to *both* sides -- the input and the lexicon value it is
    compared against -- so a flag only ever loosens the comparison. It
    never changes what number_to_text() emits, which keeps its diacritics
    and its casing. Applying it to one side only would stop the canonical
    spelling matching itself.

    The ignorable-character strip is unconditional rather than a parse
    flag, for the same reason whitespace is (#46): it is a property of
    text, not of a language. It runs first so the flags below see the
    word a reader would, and it is a no-op on authored lexicon entries.
    """
    word = word.translate(_IGNORABLE)
    if PARSE.get("case_insensitive", False):
        word = word.lower()
    if PARSE.get("strip_diacritics", False):
        # NFD splits a letter from its combining marks; dropping the marks
        # leaves the base letters, so "sâwm" and "sawm" compare equal.
        decomposed = unicodedata.normalize("NFD", word)
        word = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return word


# Connectors and aliases are normalised too, so they still match after the
# flags have been applied to the input. A connector written with a diacritic
# would otherwise stop being dropped once strip_diacritics changed the text.
_CONNECTORS = frozenset(_normalize_word(c) for c in PARSE.get("connectors", ()))
_ALIASES = {
    _normalize_word(variant): _normalize_word(canonical)
    for variant, canonical in PARSE.get("aliases", {}).items()
}


# --- Templates --------------------------------------------------------------
#
# A compiled template is a tuple of items, produced by the engine's own
# template parser and documented there (engine._parse_template):
#
#     "text"                          literal text
#     ("lex", table, key, field)      a lexicon word; key is "multiplier",
#                                     "remainder" or an int
#     ("remainder",)                  the remainder, rendered by the rules
#     ("optional", items)             present exactly when remainder > 0
#
# Every literal in the checked-in spec is a word separator or a connector,
# which is why matching can skip literals entirely: the input was split on
# those same separators and its connectors dropped, so they are not tokens.
# A literal that was neither would break that assumption --
# tests/test_render_internals.py asserts none appears, and the engine refuses
# such a spec at load.

# The scales number_to_text chooses between, largest first. Computed once:
# the compiled spec cannot change.
_EMITTING_SCALES = sorted(
    {rule["scale"] for rule in RULES if rule["emit"]}, reverse=True
)


def _rule_applies(rule: dict, multiplier: int, remainder: int) -> bool:
    """A rule's fixed multiplier, if it has one, and its condition.

    The fixed multiplier is what lets a parser read a rule that never writes
    its multiplier down -- Mizo's "zâ" is one hundred with no digit in sight,
    and a condition can only check a multiplier it has already been given.
    """
    if rule["multiplier"] is not None and rule["multiplier"] != multiplier:
        return False
    condition = rule["condition"]
    if condition is None:
        return True
    return condition({"multiplier": multiplier, "remainder": remainder})


def _find_rule(n: int) -> dict:
    """The rule n is rendered with: the largest emitting scale not above n,
    then the first rule at that scale, in spec order, that applies.

    Spec order only breaks ties within one scale, which is where ×1 lives:
    Mizo's `ten` (bare "sâwm") and `tens` ("sawm hnih") are both scale 10.
    """
    candidates = [s for s in _EMITTING_SCALES if s <= max(n, 1)]
    scale = candidates[0] if candidates else _EMITTING_SCALES[-1]
    multiplier, remainder = divmod(n, scale)
    for rule in RULES:
        if rule["scale"] == scale and rule["emit"]:
            if _rule_applies(rule, multiplier, remainder):
                return rule
    raise NumberWordsError(f"no grammar rule matches n={n}")


def _render(rule: dict, n: int) -> tuple:
    """Render n with `rule`, before any connector goes in.

    Returns (text, boundaries): the offsets where each {remainder} expansion
    starts, outermost first. The last one is where the final addend begins,
    which is where the connector goes.
    """
    multiplier, remainder = divmod(n, rule["scale"])
    values = {"multiplier": multiplier, "remainder": remainder}
    parts = []
    boundaries = []

    def walk(items):
        for item in items:
            if isinstance(item, str):
                parts.append(item)
            elif item[0] == "lex":
                _, table, key, field = item
                parts.append(LEXICON[table][values.get(key, key)][field])
            elif item[0] == "remainder":
                start = sum(len(p) for p in parts)
                sub_text, sub_boundaries = _render(_find_rule(remainder), remainder)
                boundaries.append(start)
                boundaries.extend(start + b for b in sub_boundaries)
                parts.append(sub_text)
            elif remainder:                     # ("optional", items)
                walk(item[1])

    walk(rule["output"])
    return "".join(parts), boundaries


def _with_connector(n: int, text: str, boundaries: list) -> str:
    """The connector before the final addend, for every n from its `min` up
    (Mizo: "leh" from 100, #27 Q-M). Followed by a space: the boundary it
    goes in front of already follows a separator."""
    if CONNECTOR is None or n < CONNECTOR["min"] or not boundaries:
        return text
    at = boundaries[-1]
    return text[:at] + CONNECTOR["word"] + " " + text[at:]


# --- Parsing ----------------------------------------------------------------


def _tokenize(text: str) -> list:
    """Split text into comparable tokens: normalise, split on the spec's
    word separators, drop connectors, resolve aliases."""
    # Filter after normalising, not before: a split piece holding only an
    # ignorable character is truthy going in and empty coming out, and an
    # empty token matches nothing (#46). The engine does the same.
    words = [
        word
        for word in (_normalize_word(w) for w in _SEPARATOR_RE.split(text))
        if word
    ]
    return [_ALIASES.get(w, w) for w in words if w not in _CONNECTORS]


def _acceptable_fields(table: str, named_field: str, lenient: bool) -> list:
    """Which lexicon fields a token may match for one placeholder.

    The field the template names is *always* accepted -- number_to_text()
    emits it, so it has to parse back -- and parse.accepted_forms only ever
    widens that (#31). Reading only the list instead would be wrong for a
    spec that lists a table without repeating the named field, which is
    exactly how mizo.yaml is written: it declares `units: [bound]`, so this
    shortcut would stop accepting "pakhat". The vectors catch that.
    """
    if not lenient:
        return [named_field]
    extras = PARSE.get("accepted_forms", {}).get(table, ())
    return [named_field] + [f for f in extras if f != named_field]


def _parse_values(tokens: list) -> set:
    """Every number in the supported range some derivation of `tokens` gives.

    Recursive descent over the rules, the same algorithm as the engine's
    Spec._parse_values and deliberately a separate copy of it: this module
    never imports the oracle. The two are held together by vectors/mizo.json,
    and by reference/test_compile_spec.py, which feeds both every phrase of
    up to three words and requires the same answer.

    Memoised on (start, end, whole, below). `whole` is whether the span is
    the entire input -- a `scope: whole` rule is only ever the whole phrase,
    never somebody's remainder -- and `below` skips rules too large to render
    a remainder. That is pruning, not correctness: the remainder also has to
    come out smaller than the scale, which alone rejects the rest.
    """
    # Leniency applies only to a phrase that is a single freestanding word --
    # "khat" as well as "pakhat" for 1. Relaxing a slot inside a longer phrase
    # would let "sawm hnih" (20) also read as 10 + 2 through the bound form of
    # 2, which is real ambiguity rather than an accepted alternate spelling.
    lenient = len(tokens) == 1
    cache = {}

    def span(start, end, whole, below):
        key = (start, end, whole, below)
        if key not in cache:
            values = set()
            for rule in RULES:
                if below is not None and rule["scale"] >= below:
                    continue
                if rule["whole_only"] and not whole:
                    continue
                initial = {}
                if rule["multiplier"] is not None:
                    initial["multiplier"] = rule["multiplier"]
                for bound in match(rule["output"], start, end, initial, rule, whole):
                    if "multiplier" not in bound:
                        continue
                    multiplier = bound["multiplier"]
                    remainder = bound.get("remainder", 0)
                    if _rule_applies(rule, multiplier, remainder):
                        values.add(multiplier * rule["scale"] + remainder)
            cache[key] = values
        return cache[key]

    def bind(bound, name, value):
        if bound.get(name, value) != value:
            return None
        rebound = dict(bound)
        rebound[name] = value
        return rebound

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
                if _normalize_word(LEXICON[table][key][field]) == token:
                    yield from match(rest, position + 1, end, bound, rule, whole)
                return
            # Two gates, each a backstop for the other, as in the engine:
            # removing one is caught by no test on today's data; removing
            # both makes "sawm hnih" read as 12 as well as 20, which the
            # vectors catch at once.
            fields = _acceptable_fields(table, field, lenient and whole)
            for entry_key, entry in LEXICON[table].items():
                if any(
                    f in entry and _normalize_word(entry[f]) == token
                    for f in fields
                ):
                    rebound = bind(bound, key, entry_key)
                    if rebound is not None:
                        yield from match(rest, position + 1, end, rebound, rule, whole)
        elif item[0] == "remainder":
            for stop in range(position + 1, end + 1):
                for value in span(position, stop, False, rule["scale"]):
                    if 0 < value < rule["scale"]:
                        rebound = bind(bound, "remainder", value)
                        if rebound is not None:
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

    if not tokens:
        return set()
    low, high = SUPPORTS
    return {v for v in span(0, len(tokens), True, None) if low <= v <= high}


# --- Public behaviour -------------------------------------------------------


def render_number(n: int) -> str:
    # The engine does not check this -- it is handed numbers by code that
    # already knows they are numbers. A published API is handed whatever a
    # caller has, so check here rather than letting a KeyError out of a
    # lexicon lookup two frames down.
    #
    # bool is excluded explicitly because it is a subclass of int: without
    # this, number_to_text(True) answers "pakhat" and a caller who passed a
    # flag by mistake never finds out. Floats go the same way -- 5.0 would
    # work and 5.5 would not, which is worse than neither working.
    if not isinstance(n, int) or isinstance(n, bool):
        raise NumberWordsError(
            f"expected an int, got {type(n).__name__}"
        )
    low, high = SUPPORTS
    if not (low <= n <= high):
        raise NumberWordsError(
            f"{n} is outside the supported range [{low}, {high}]"
        )
    text, boundaries = _render(_find_rule(n), n)
    return _with_connector(n, text, boundaries)


def parse_text(text: str) -> int:
    """Every number some derivation of the text gives, then exactly one of
    them or an error.

    Collecting all of them rather than returning the first is the point.
    Two numbers accepting the same spelling is a fault in the spec, and it
    has to be loud: returning whichever the parser happened to find first
    would hide it behind an answer that looks right. There is no ambiguity
    in the current spec, so this is here for the grammar change that
    introduces one.
    """
    # Same reason as render_number: without this, a non-string reaches the
    # separator regex and surfaces as TypeError from inside re.
    if not isinstance(text, str):
        raise NumberWordsError(
            f"expected a str, got {type(text).__name__}"
        )
    matches = sorted(_parse_values(_tokenize(text)))
    if not matches:
        raise NumberWordsError(
            f"{text!r} does not match any number in the supported range"
        )
    if len(matches) > 1:
        raise NumberWordsError(
            f"{text!r} is ambiguous: matches {matches}"
        )
    return matches[0]
