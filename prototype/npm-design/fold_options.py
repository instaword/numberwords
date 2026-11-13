"""The two fold tables the #75 fold-table comment weighs, on this Python.

    full table        build_data.py's rule: every character whose
                      normalisation is made only of the language's letters,
                      or of nothing. Every combining mark normalises to
                      nothing, so every mark this Python's Unicode knows is
                      in it.
    Latin-only table  the full table's letters, plus only the marks found
                      inside those letters.

Prints both sizes, a digest of the Latin-only table (compare it across
Pythons: it should not change), a few spellings it still reads -- uppercase,
no accent, the wrong accent, a separate circumflex -- and what it changes
against today's package. Only the dropped marks can change anything, so
each is tried in five positions: alone, before, inside and after `sâwm`,
and as a second word after it.

Needs nothing but the package, so it runs on any Python, including the
python.org embeddable builds. From the repo root:

    reference/.venv/Scripts/python.exe prototype/npm-design/fold_options.py
"""

import hashlib
import json
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "packages" / "python" / "src"))

import numberwords  # noqa: E402
from numberwords import _mizo, _render  # noqa: E402

# --- The full table: build_data.py's rule, unchanged ------------------------
words = [v for t in _mizo.LEXICON.values()
         for e in t.values() for v in e.values()]
words += list(_mizo.PARSE["connectors"]) + list(_mizo.PARSE["aliases"])
words += list(_mizo.PARSE["aliases"].values())
alphabet = set("".join(_render._normalize_word(w) for w in words))
full = {}
for cp in range(0x110000):
    if 0xD800 <= cp <= 0xDFFF or cp in _render._IGNORABLE:
        continue
    ch = chr(cp)
    if ch in alphabet:
        continue
    folded = _render._normalize_word(ch)
    if all(c in alphabet for c in folded):
        full[ch] = folded

# --- The Latin-only table ---------------------------------------------------
letters = {ch: f for ch, f in full.items() if f}
marks = {ch for ch, f in full.items() if not f}
inside = {m for ch in letters for m in unicodedata.normalize("NFD", ch)
          if unicodedata.combining(m)}
latin = dict(letters, **{m: "" for m in inside})
assert inside <= marks, "a mark inside a letter is missing from the full table"
dropped = marks - inside

digest = hashlib.sha256(json.dumps(sorted(latin.items())).encode()).hexdigest()

# --- What the Latin-only table changes ---------------------------------------
stock = _render._normalize_word


def latin_normalize(word):
    word = word.translate(_render._IGNORABLE)
    return "".join(latin.get(ch, ch) for ch in word)


# The package builds its connector and alias sets at import with the stock
# function. Patching that function below only proves something if the
# Latin-only table builds the same sets.
assert {latin_normalize(c) for c in _mizo.PARSE["connectors"]} \
    == _render._CONNECTORS
assert {latin_normalize(a): latin_normalize(c)
        for a, c in _mizo.PARSE["aliases"].items()} == _render._ALIASES


def answer(text):
    try:
        return numberwords.text_to_number(text)
    except numberwords.NumberWordsError:
        return None


_render._normalize_word = latin_normalize
# ascii(), without its quotes: a Windows console may not print the accents.
spellings = ("SÂWM", "sawm", "sáwm", "sa" + chr(0x302) + "wm")
examples = ", ".join(f"{ascii(t)[1:-1]} {answer(t)}" for t in spellings)

lost = other = 0
for m in sorted(dropped):
    for text in (m, m + "sâwm", "sâ" + m + "wm", "sâwm" + m, "sâwm " + m):
        _render._normalize_word = stock
        before = answer(text)
        _render._normalize_word = latin_normalize
        after = answer(text)
        if before != after:
            if before is not None and after is None:
                lost += 1
            else:
                other += 1
_render._normalize_word = stock

print(f"Python {sys.version.split()[0]}, Unicode {unicodedata.unidata_version}")
print(f"full table: {len(full)} entries "
      f"({len(letters)} letters, {len(marks)} marks)")
print(f"Latin-only table: {len(latin)} entries ({len(letters)} letters, "
      f"{len(inside)} marks), sha256 {digest[:12]}")
print(f"Latin-only table reads: {examples}")
print(f"Latin-only vs today, {len(dropped)} dropped marks in 5 positions: "
      f"{lost} number -> error, {other} other")
