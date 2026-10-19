"""Prototype JS backend for compile_spec.py (#75).

Writes two versions of the compiled spec so the two ways of shipping rule
conditions can be compared:

    out/_mizo.code.js   conditions as JS functions (a code generator per target)
    out/_mizo.data.js   conditions as a small expression tree (data)

Chained comparisons (0 < d < 5) are expanded to an explicit `and` here, once,
so no target ever sees a chain.

Run from the repo root with the reference venv:

    reference/.venv/Scripts/python.exe prototype/npm-design/emit_js.py
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = HERE / "out"
sys.path.insert(0, str(REPO / "reference"))

from engine import _parse_template, _validate_condition_node, load  # noqa: E402

sys.path.insert(0, str(HERE))
from conditions import condition_tree  # noqa: E402

spec = load(REPO / "languages" / "mizo.yaml")

JS_OPS = {">": ">", ">=": ">=", "<": "<", "<=": "<=", "==": "===", "!=": "!=="}


def tree_to_js(t):
    kind = t[0]
    if kind in ("and", "or"):
        joiner = " && " if kind == "and" else " || "
        return "(" + joiner.join(tree_to_js(x) for x in t[1:]) + ")"
    if kind == "cmp":
        return f"{tree_to_js(t[2])} {JS_OPS[t[1]]} {tree_to_js(t[3])}"
    if kind == "var":
        return f"v.{t[1]}"
    return str(t[1])


def condition(expr, as_code):
    if expr is None:
        return None
    t = condition_tree(expr, _validate_condition_node)
    return ["CODE", f"(v) => {tree_to_js(t)}"] if as_code else t


def template(items):
    res = []
    for it in items:
        if isinstance(it, str):
            res.append(it)
        elif it[0] == "optional":
            res.append(["optional", template(it[1])])
        else:
            res.append(list(it))
    return res


def module(as_code):
    rules = []
    for r in spec.rules:
        rules.append({
            "name": r["name"],
            "scale": r["scale"],
            "multiplier": r.get("multiplier"),
            "condition": condition(r.get("condition"), as_code),
            "output": template(_parse_template(r["output"])),
            "emit": r.get("emit") != "never",
            "whole_only": r.get("scope") == "whole",
            "stacks": id(r) in spec._stacking_rules,
        })
    cfg = spec.parse_config
    data = {
        "LANGUAGE": spec._data["meta"]["language"],
        "CODE": spec._data["meta"]["code"],
        "SPEC_VERSION": str(spec._data["meta"]["version"]),
        "SUPPORTS": [spec.supports["min"], spec.supports["max"]],
        # [key, entry] pairs: JS object keys are always strings.
        "LEXICON": {t: [[k, spec.lexicon[t][k]] for k in sorted(spec.lexicon[t])]
                    for t in sorted(spec.lexicon)},
        "RULES": rules,
        "CONNECTOR": spec.connector and {"word": spec.connector["word"], "min": spec.connector["min"]},
        "PARSE": {
            "case_insensitive": cfg.get("case_insensitive", False),
            "strip_diacritics": cfg.get("strip_diacritics", False),
            "word_separators": list(cfg.get("word_separators", [])),
            "accepted_forms": {t: list(f) for t, f in sorted(cfg.get("accepted_forms", {}).items())},
            "connectors": sorted(spec._normalize_word(c) for c in cfg.get("connectors", [])),
            "aliases": {spec._normalize_word(a): spec._normalize_word(b)
                        for a, b in sorted(cfg.get("aliases", {}).items())},
        },
    }
    lines = ["// Compiled from languages/mizo.yaml by emit_js.py. Do not edit by hand.", ""]
    for name, value in data.items():
        text = json.dumps(value, ensure_ascii=False, indent=2)
        if as_code:
            text = re.sub(r'\[\s*"CODE",\s*"((?:[^"\\]|\\.)*)"\s*\]',
                          lambda m: json.loads('"' + m.group(1) + '"'), text)
        lines.append(f"export const {name} = {text};")
        lines.append("")
    return "\n".join(lines)


OUT.mkdir(exist_ok=True)
(OUT / "_mizo.code.js").write_text(module(True), encoding="utf-8", newline="\n")
(OUT / "_mizo.data.js").write_text(module(False), encoding="utf-8", newline="\n")
print("wrote out/_mizo.code.js and out/_mizo.data.js")
