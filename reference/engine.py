"""Reference engine: interprets a language spec (languages/<lang>.yaml) to
convert numbers to text. This is the "oracle" described in
docs/architecture.md -- the definition of correctness that target packages
(Python, npm, ...) are eventually checked against, instead of each
reimplementing a language's rules by hand.

Scope: specs shaped like the current languages/mizo.yaml (positional
variables ones_digit/tens_digit only, i.e. the 0-100 range). Larger ranges
are follow-up work.

text -> number is implemented by normalising the input per the spec's
`parse` section and searching the supported range for the number whose
number_to_text() output matches -- see Spec.text_to_number(). That keeps
number_to_text() as the single source of truth (no separate parsing
grammar to keep in sync) and is cheap enough for a 0-100 range; it will
need to become a real parser once milestone 7 extends the range.
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
        tokens = self._tokenize(text)
        for n in range(self.supports["min"], self.supports["max"] + 1):
            if self._tokenize(self.number_to_text(n)) == tokens:
                return n
        raise ValueError(f"{text!r} does not match any number in the supported range")

    def _tokenize(self, text: str) -> list:
        """Normalise text per the spec's `parse` section: lowercase (if
        configured), split on word_separators, and drop connector words.
        Mirrors docs/spec-format.md's description of the reverse direction.
        """
        if self.parse_config.get("case_insensitive", False):
            text = text.lower()
        separators = self.parse_config.get("word_separators", [" "])
        pattern = "|".join(re.escape(sep) for sep in separators)
        words = [w for w in re.split(pattern, text) if w]
        connectors = set(self.parse_config.get("connectors", []))
        return [w for w in words if w not in connectors]

    @property
    def examples(self) -> list:
        return self._data.get("examples", [])


def load(path) -> Spec:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Spec(data)
