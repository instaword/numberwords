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

from ._mizo import LEXICON, PARSE, RULES, SUPPORTS


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
# A compiled template is a tuple whose items are either a literal string or a
# (table, key, field) placeholder triple. The engine's templates are strings
# with "{table[key].field}" markers and it finds them with a regex; here the
# compiler has already done that work, so a placeholder is anything that is a
# tuple.
#
# Every literal in the checked-in spec is a word separator, which is why
# matching can ignore literals entirely: the input was split on those same
# separators, so they are not tokens. A literal that was not a separator
# would break that assumption -- tests/test_render_internals.py asserts none
# appears.


def _placeholders(template) -> list:
    return [item for item in template if isinstance(item, tuple)]


def _positional_variables(n: int) -> dict:
    """The variables a placeholder key or a rule condition may refer to.

    Hardcoded to three names, matching the engine and the compiler. Adding a
    name here without adding it to reference/engine.py (or the reverse) makes
    every rule that reads it raise KeyError in one implementation while the
    other stays green -- the two are separate copies on purpose, since this
    module never imports the oracle.

    #27 notes these do not generalise up the ladder: one variable per digit
    position stops working long before 10^9, and the multiplier there can be
    any numeral the grammar produces rather than a single digit. That is a
    known limit of the format, not of this module.
    """
    return {
        "ones_digit": n % 10,
        "tens_digit": (n // 10) % 10,
        "hundreds_digit": (n // 100) % 10,
    }


def _resolve_key(raw_key, variables: dict):
    """A placeholder's key is either a variable name ("ones_digit") or a
    literal lexicon key (scales[10]). The compiler preserves the
    distinction as str vs int, so no reparsing is needed here."""
    if isinstance(raw_key, str):
        return variables[raw_key]
    return raw_key


def _find_rule(n: int, variables: dict) -> dict:
    """The first rule whose range contains n and whose condition passes.

    Order is significant and comes from the spec -- exact_tens is listed
    before compound_tens and both cover 21-99, so the conditions are what
    separate them. Scanning in order is the rule-selection algorithm, not
    an implementation detail.
    """
    for rule in RULES:
        low, high = rule["range"]
        if not (low <= n <= high):
            continue
        condition = rule["condition"]
        if condition is not None and not condition(variables):
            continue
        return rule
    raise NumberWordsError(f"no grammar rule matches n={n}")


def _render(template, variables: dict) -> str:
    parts = []
    for item in template:
        if isinstance(item, tuple):
            table, raw_key, field = item
            key = _resolve_key(raw_key, variables)
            parts.append(LEXICON[table][key][field])
        else:
            parts.append(item)
    return "".join(parts)


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


def _token_matches(item, variables: dict, token: str, lenient: bool) -> bool:
    table, raw_key, field = item
    entry = LEXICON[table][_resolve_key(raw_key, variables)]
    for candidate_field in _acceptable_fields(table, field, lenient):
        value = entry.get(candidate_field)
        if value is not None and _normalize_word(value) == token:
            return True
    return False


def _rule_matches(template, tokens: list, variables: dict) -> bool:
    placeholders = _placeholders(template)
    if len(placeholders) != len(tokens):
        return False
    # Leniency applies only to a phrase that is a single freestanding digit
    # -- "khat" as well as "pakhat" for 1. Relaxing a slot inside a
    # multi-word template would make "sawm hnih" match both 20 and teens'
    # ones-digit slot for 12, which is real ambiguity rather than an
    # accepted alternate spelling.
    lenient = len(placeholders) == 1
    # zip is safe only because the lengths were just asserted equal; it
    # truncates silently otherwise.
    return all(
        _token_matches(item, variables, token, lenient)
        for item, token in zip(placeholders, tokens)
    )


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
    variables = _positional_variables(n)
    return _render(_find_rule(n, variables)["output"], variables)


def parse_text(text: str) -> int:
    """Every number in the supported range whose grammar rule matches the
    text, then exactly one of them or an error.

    Collecting all matches rather than returning the first is the point.
    Two numbers accepting the same spelling is a fault in the spec, and it
    has to be loud: returning whichever came first in the range would hide
    it behind an answer that looks right. There is no ambiguity in the
    current spec -- checked across the whole range -- so this is here for
    the grammar change that introduces one.
    """
    # Same reason as render_number: without this, a non-string reaches the
    # separator regex and surfaces as TypeError from inside re.
    if not isinstance(text, str):
        raise NumberWordsError(
            f"expected a str, got {type(text).__name__}"
        )
    tokens = _tokenize(text)
    low, high = SUPPORTS
    matches = []
    for n in range(low, high + 1):
        variables = _positional_variables(n)
        rule = _find_rule(n, variables)
        templates = [rule["output"]]
        templates.extend(rule["parse_aliases"])
        if any(_rule_matches(t, tokens, variables) for t in templates):
            matches.append(n)
    if not matches:
        raise NumberWordsError(
            f"{text!r} does not match any number in the supported range"
        )
    if len(matches) > 1:
        raise NumberWordsError(
            f"{text!r} is ambiguous: matches {matches}"
        )
    return matches[0]
