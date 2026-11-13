"""The Python package's answer for every Unicode code point in three places:
alone, replacing the "a" of "sawm", and inside "sawm" after the "a".

Writes out/per_char.json with only the strings Python accepts (everything
else is rejected). About 3.3 million parses: several minutes.

    reference/.venv/Scripts/python.exe prototype/npm-design/per_char.py
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "packages" / "python" / "src"))

import numberwords  # noqa: E402

PATTERNS = ("s{}wm", "sa{}wm", "{}")
accepted = {}
total = 0
for cp in range(0x110000):
    if 0xD800 <= cp <= 0xDFFF:
        continue
    for pattern in PATTERNS:
        s = pattern.format(chr(cp))
        total += 1
        try:
            accepted[s] = numberwords.text_to_number(s)
        except numberwords.NumberWordsError:
            pass
(HERE / "out").mkdir(exist_ok=True)
(HERE / "out" / "per_char.json").write_text(
    json.dumps({"patterns": PATTERNS, "accepted": accepted}, ensure_ascii=False), encoding="utf-8")
print(f"{total:,} strings, {len(accepted)} accepted by Python")
