"""Reference engine: interprets a language spec (languages/<lang>.yaml) to
convert numbers to text. This is the "oracle" described in
docs/architecture.md -- the definition of correctness that target packages
(Python, npm, ...) are eventually checked against, instead of each
reimplementing a language's rules by hand.

Scope: specs shaped like the current languages/mizo.yaml (positional
variables ones_digit/tens_digit only, i.e. the 0-100 range). Larger ranges
are follow-up work.

text -> number is implemented by normalising the input per the spec's
`parse` section, then searching the supported range for the number whose
grammar rule matches the input token-by-token -- see Spec.text_to_number().
Matching is placeholder-aware rather than a plain string comparison against
number_to_text()'s output: a freestanding single-digit phrase (one token,
one placeholder) accepts either bound or standalone form per
parse.accepted_forms (e.g. "khat" as well as "pakhat" for 1), while
multi-word rules (teens, exact_tens, compound_tens, ...) match each field
exactly as the canonical template names it, to avoid cross-rule ambiguity
(see _rule_matches). number_to_text() stays the single source of truth for
the canonical form. This is cheap enough for a 0-100 range by brute-force
search; it will need to become a real parser once milestone 7 extends the
range.
"""

import ast
import operator
import re

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
            if self._rule_matches(rule["output"], tokens, variables):
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
        # TODO: "units" and the "standalone"/"bound" field names are
        # hardcoded Mizo-specific assumptions living inside code that's
        # otherwise language-agnostic -- a small tension with "the spec is
        # the source of truth" (docs/architecture.md). Fine while Mizo is
        # the only language; when a second language is added, this should
        # be driven from the spec (e.g. which table/fields are
        # leniency-eligible) instead of a fixed string check.
        if not lenient or table != "units":
            return [default_field]
        accepted = self.parse_config.get("accepted_forms", {})
        fields = [
            f
            for f, enabled in (("standalone", accepted.get("standalone_units", True)),
                               ("bound", accepted.get("bound_units", True)))
            if enabled
        ]
        return fields or [default_field]

    def _normalize_word(self, word: str) -> str:
        return word.lower() if self.parse_config.get("case_insensitive", False) else word

    def _tokenize(self, text: str) -> list:
        """Normalise text per the spec's `parse` section: lowercase (if
        configured), split on word_separators, drop connector words, and
        resolve spelling-variant aliases to their canonical word. Mirrors
        docs/spec-format.md's description of the reverse direction ("drop
        connectors, resolve aliases").
        """
        if self.parse_config.get("case_insensitive", False):
            text = text.lower()
        separators = self.parse_config.get("word_separators", [" "])
        pattern = "|".join(re.escape(sep) for sep in separators)
        words = [w for w in re.split(pattern, text) if w]
        connectors = set(self.parse_config.get("connectors", []))
        aliases = self.parse_config.get("aliases", {})
        return [aliases.get(w, w) for w in words if w not in connectors]

    @property
    def examples(self) -> list:
        return self._data.get("examples", [])


def load(path) -> Spec:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Spec(data)
