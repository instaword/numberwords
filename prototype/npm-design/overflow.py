"""How large a reading gets before the range check (#75, point 2).

Parses stacked chains of scale words and prints the largest reading the
parser produces for each, before parse_text() applies the range.

    reference/.venv/Scripts/python.exe prototype/npm-design/overflow.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "packages" / "python" / "src"))

from numberwords import _render  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

INT64_MAX = 2**63 - 1
SCALES = ["tlûklehdingâwn", "vaibêlchhetak", "vaibêlchhe", "maktaduai", "nuai", "sîng"]
for k in range(2, len(SCALES) + 1):
    phrase = " ".join(SCALES[:k]) + " kua"
    readings = _render._parse_readings(_render._tokenize(phrase))
    top = max(readings)
    print(f"{k + 1} words: largest reading {top:.3e}"
          f"{'  > int64' if top > INT64_MAX else ''}   ({phrase})")
