"""Builds the data the JS checks compare against, from the Python package.

    out/fold.json      the fold table (point 2 of the #75 proposal)
    out/phrases.json   the package's answer for every phrase of 1-3 words
                       the lexicon can spell, plus the closed-world file
                       (vocabulary + every phrase that parses)

The vocabulary is the one reference/test_compile_spec.py uses for its
short-phrase test: every normalised lexicon word, connector and alias.

Run from the repo root:

    reference/.venv/Scripts/python.exe prototype/npm-design/build_data.py
"""

import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = HERE / "out"
sys.path.insert(0, str(REPO / "packages" / "python" / "src"))

import numberwords  # noqa: E402
from numberwords import _mizo, _render  # noqa: E402

OUT.mkdir(exist_ok=True)

# --- Fold table -------------------------------------------------------------
# Every character whose normalisation is made only of letters the language's
# normalised words use (or nothing), and which is not one of those letters.
# Any other character is left alone: it cannot help a word match, and Python's
# normalisation of it cannot either, so lookups give the same answer.
words = [v for t in _mizo.LEXICON.values() for e in t.values() for v in e.values()]
words += list(_mizo.PARSE["connectors"]) + list(_mizo.PARSE["aliases"]) + list(_mizo.PARSE["aliases"].values())
alphabet = set("".join(_render._normalize_word(w) for w in words))
fold = {}
for cp in range(0x110000):
    if 0xD800 <= cp <= 0xDFFF or cp in _render._IGNORABLE:
        continue
    ch = chr(cp)
    if ch in alphabet:
        continue
    folded = _render._normalize_word(ch)
    if all(c in alphabet for c in folded):
        fold[ch] = folded
(OUT / "fold.json").write_text(json.dumps({"alphabet": "".join(sorted(alphabet)), "fold": fold},
                                          ensure_ascii=False), encoding="utf-8")
print(f"fold table: {len(fold)} entries over alphabet {''.join(sorted(alphabet))}")

# --- Phrases ----------------------------------------------------------------
vocab = sorted({_render._normalize_word(w) for w in words})
results = {}
for k in (1, 2, 3):
    for combo in itertools.product(vocab, repeat=k):
        s = " ".join(combo)
        try:
            results[s] = numberwords.text_to_number(s)
        except numberwords.NumberWordsError:
            results[s] = None
accepted = {s: v for s, v in results.items() if v is not None}
(OUT / "phrases.json").write_text(json.dumps(
    {"vocabulary": vocab, "max_words": 3, "results": results}, ensure_ascii=False), encoding="utf-8")
closed = json.dumps({"vocabulary": vocab, "max_words": 3, "accepted": accepted},
                    ensure_ascii=False, indent=1)
(OUT / "closed.json").write_text(closed, encoding="utf-8")
print(f"phrases: {len(vocab)} words, {len(results)} phrases, {len(accepted)} parse; "
      f"closed-world file {len(closed.encode('utf-8')):,} bytes")
