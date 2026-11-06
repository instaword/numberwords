"""The Python package with points 1 and 2 applied: conditions as data and
the fold table. Works on a temporary copy; the real package is not touched.

Checks the copy two ways: its own test suite (packages/python/tests), and
its answer on every phrase in out/phrases.json against the shipped package.

    reference/.venv/Scripts/python.exe prototype/npm-design/python_shape.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "reference"))
sys.path.insert(0, str(HERE))

from conditions import condition_tree  # noqa: E402
from engine import _validate_condition_node, load  # noqa: E402

spec = load(REPO / "languages" / "mizo.yaml")
trees = {r["name"]: condition_tree(r.get("condition"), _validate_condition_node) for r in spec.rules}
fold = json.loads((HERE / "out" / "fold.json").read_text(encoding="utf-8"))["fold"]

EVALUATOR = '''

_CMP = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b}


def _eval(t, v):
    if t[0] == "and":
        return all(_eval(x, v) for x in t[1:])
    if t[0] == "or":
        return any(_eval(x, v) for x in t[1:])
    if t[0] == "var":
        return v[t[1]]
    if t[0] == "int":
        return t[1]
    return _CMP[t[1]](_eval(t[2], v), _eval(t[3], v))


def _rule_applies('''


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    # shutil.copy, not copy2: fresh timestamps, so a temp-folder cleaner
    # cannot mistake the copy for old files mid-run.
    shutil.copytree(REPO / "packages" / "python", tmp / "packages" / "python",
                    copy_function=shutil.copy, ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
    shutil.copytree(REPO / "vectors", tmp / "vectors", copy_function=shutil.copy)
    pkg = tmp / "packages" / "python" / "src" / "numberwords"

    mizo = (pkg / "_mizo.py").read_text(encoding="utf-8")
    mizo += ("\n# Points 1 and 2 of #75: conditions as data, and the fold table.\n"
             f"_TREES = {trees!r}\n"
             "RULES = tuple(dict(rule, condition=_TREES[rule['name']]) for rule in RULES)\n"
             f"FOLD = {fold!r}\n")
    (pkg / "_mizo.py").write_text(mizo, encoding="utf-8")

    render = (pkg / "_render.py").read_text(encoding="utf-8")
    render = replace_once(render, "from ._mizo import CONNECTOR, LEXICON, PARSE, RULES, SUPPORTS",
                          "from ._mizo import CONNECTOR, FOLD, LEXICON, PARSE, RULES, SUPPORTS")
    render = replace_once(render, '    return condition({"multiplier": multiplier, "remainder": remainder})',
                          '    return _eval(condition, {"multiplier": multiplier, "remainder": remainder})')
    render = replace_once(render, "\n\ndef _rule_applies(", EVALUATOR)
    render = replace_once(render, '    if PARSE.get("case_insensitive", False):',
                          '    return "".join(FOLD.get(ch, ch) for ch in word)\n'
                          '    if PARSE.get("case_insensitive", False):')
    (pkg / "_render.py").write_text(render, encoding="utf-8")
    assert "lambda variables" not in (pkg / "_mizo.py").read_text(encoding="utf-8").split("_TREES")[1]

    tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                           cwd=tmp / "packages" / "python", capture_output=True, text=True)
    print("package tests on the copy:", tests.stdout.strip().splitlines()[-1])

    sys.path.insert(0, str(tmp / "packages" / "python" / "src"))
    import numberwords  # noqa: E402
    assert Path(numberwords.__file__).resolve().is_relative_to(tmp.resolve()), numberwords.__file__
    assert hasattr(numberwords._render, "FOLD")
    phrases = json.loads((HERE / "out" / "phrases.json").read_text(encoding="utf-8"))["results"]
    differ = 0
    for s, want in phrases.items():
        try:
            got = numberwords.text_to_number(s)
        except numberwords.NumberWordsError:
            got = None
        differ += got != want
    print(f"phrases: {len(phrases)}, {differ} differ from the shipped package")
