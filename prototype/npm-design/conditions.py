"""Rule conditions as data: the shape proposed in #75, point 1.

    ["and" | "or", tree, tree, ...]
    ["cmp", op, tree, tree]          op in > >= < <= == !=
    ["var", "multiplier" | "remainder"]
    ["int", k]

Chained comparisons (0 < d < 5) become an explicit "and" here, so no target
ever has to know Python's chaining rule.
"""

import ast

OPS = {ast.Gt: ">", ast.GtE: ">=", ast.Lt: "<", ast.LtE: "<=", ast.Eq: "==", ast.NotEq: "!="}


def cond_tree(node):
    if isinstance(node, ast.BoolOp):
        return ["and" if isinstance(node.op, ast.And) else "or"] + [cond_tree(v) for v in node.values]
    if isinstance(node, ast.Compare):
        operands = [node.left] + node.comparators
        parts = [["cmp", OPS[type(op)], cond_tree(a), cond_tree(b)]
                 for op, a, b in zip(node.ops, operands, operands[1:])]
        return parts[0] if len(parts) == 1 else ["and"] + parts
    if isinstance(node, ast.Name):
        return ["var", node.id]
    if isinstance(node, ast.Constant):
        return ["int", int(node.value)]
    raise ValueError(ast.dump(node))


def condition_tree(expression, validate):
    """The tree for one spec `condition` string, or None. `validate` is the
    engine's allowlist check, run on the Python AST before converting."""
    if expression is None:
        return None
    node = ast.parse(expression, mode="eval").body
    validate(node)
    return cond_tree(node)
