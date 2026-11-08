"""Two ways to bound a reading, against today's parser (#75, point 4 of the
10-18 review). overflow.py shows how large readings get; this shows what each
fix would change.

    drop   a reading above supports.max is thrown away as it is built
    cap    every reading above supports.max is one value, max + 1, keeping
           the best greedy rank among them. The remainder is checked before
           dividing, and a capped multiplier is never taken for a word.

Both are made by patching copies of packages/python/src/numberwords/_render.py
in a temporary folder, so the package itself is untouched. Each phrase's answer
is compared by class: a number, ambiguous (with every number above the range
written as "over"), above the range, or no match.

    reference/.venv/Scripts/python.exe prototype/npm-design/overflow_options.py

About 17 minutes on 14 processes. The random set is drawn with seed 75, so
every count reproduces.
"""

import itertools
import json
import random
import shutil
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PACKAGE = REPO / "packages" / "python" / "src" / "numberwords"

VALUE = '                    value = multiplier * rule["scale"] + remainder\n'
DROP = VALUE + (
    "                    if value > SUPPORTS[1]:\n"
    "                        continue\n"
)
CAP = (
    "                    if (\n"
    "                        remainder > SUPPORTS[1]\n"
    "                        or multiplier > (SUPPORTS[1] - remainder) // rule[\"scale\"]\n"
    "                    ):\n"
    "                        value = SUPPORTS[1] + 1\n"
    "                    else:\n"
    "                        value = multiplier * rule[\"scale\"] + remainder\n"
)
WORD_SLOT = "                        if value in LEXICON[table]:\n"
CAPPED_WORD_SLOT = (
    "                        if value <= SUPPORTS[1] and value in LEXICON[table]:\n"
)


def _variant(root, name, replacements):
    target = root / name
    # copy, not copy2: fresh timestamps, so a Temp cleaner that removes
    # old-dated files cannot take __init__.py out from under a running sweep.
    shutil.copytree(PACKAGE, target, copy_function=shutil.copy,
                    ignore=shutil.ignore_patterns("__pycache__"))
    render = target / "_render.py"
    text = render.read_text(encoding="utf-8")
    for old, new in replacements:
        assert text.count(old) == 1, (name, old)
        text = text.replace(old, new)
    render.write_text(text, encoding="utf-8")


def _load(root):
    sys.path.insert(0, str(root))
    import nw_cap
    import nw_drop
    import nw_exact
    return nw_exact, nw_drop, nw_cap


def _classify(pkg, text, high):
    try:
        return ("number", pkg.text_to_number(text))
    except pkg.NumberWordsError as error:
        message = str(error)
        if " is ambiguous: matches " in message:
            listed = json.loads(message.rsplit("matches ", 1)[1])
            return ("ambiguous", tuple(sorted({"over" if n > high else n for n in listed}, key=str)))
        if " reads as " in message:
            return ("above range",)
        if "does not match" in message:
            return ("no match",)
        return ("other", message)


def _work(args):
    root, chunk = args
    exact, drop, cap = _load(root)
    high = exact._render.SUPPORTS[1]
    dropped = capped = 0
    for text in chunk:
        answer = _classify(exact, text, high)
        dropped += _classify(drop, text, high) != answer
        capped += _classify(cap, text, high) != answer
    return dropped, capped


def main():
    root = Path(tempfile.mkdtemp(prefix="overflow_options_"))
    try:
        _variant(root, "nw_exact", [])
        _variant(root, "nw_drop", [(VALUE, DROP)])
        _variant(root, "nw_cap", [(VALUE, CAP), (WORD_SLOT, CAPPED_WORD_SLOT)])
        exact, _, _ = _load(root)
        r = exact._render
        words = [v for t in r.LEXICON.values() for e in t.values() for v in e.values()]
        words += list(r.PARSE["connectors"]) + list(r.PARSE["aliases"])
        words += list(r.PARSE["aliases"].values())
        vocab = sorted({r._normalize_word(w) for w in words})
        with open(REPO / "vectors" / "mizo.json", encoding="utf-8") as f:
            vectors = json.load(f)
        rng = random.Random(75)
        scales = sorted(r._normalize_word(e["standalone"]) for e in r.LEXICON["scales"].values())
        small = scales + [r._normalize_word(r.LEXICON["units"][k]["bound"]) for k in (2, 9)] + ["leh"]
        sets = {
            "Vectors (canonical + accepted inputs)":
                sorted({v["text"] for v in vectors} | {a for v in vectors for a in v["accepted_inputs"]}),
            f"Every phrase of 1-4 words from the {len(vocab)}-word vocabulary":
                [" ".join(p) for k in range(1, 5) for p in itertools.product(vocab, repeat=k)],
            "Random phrases of 5-8 words (seed 75)":
                [" ".join(rng.choice(vocab) for _ in range(rng.randint(5, 8))) for _ in range(400_000)],
            f"Every 5- and 6-word chain of {', '.join(small)}":
                [" ".join(p) for k in (5, 6) for p in itertools.product(small, repeat=k)],
        }
        print("| Phrases | Count | Drop: answers that differ | Cap: answers that differ |")
        print("|---|---|---|---|")
        with ProcessPoolExecutor(max_workers=14) as pool:
            for name, phrases in sets.items():
                chunks = [(root, phrases[i:i + 2000]) for i in range(0, len(phrases), 2000)]
                dropped = capped = 0
                for d, c in pool.map(_work, chunks):
                    dropped += d
                    capped += c
                print(f"| {name} | {len(phrases):,} | {dropped:,} | {capped:,} |")
                sys.stdout.flush()
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
