"""Why mutant 2 in mutants.mjs is caught by nothing.

Mutant 2 keeps the lowest-ranked derivation of a value instead of the
highest. That can only change an answer if, somewhere in a parse, one value
is reached by two derivations with different ranks. This instruments a
temporary copy of the Python package to record every such case, then parses
every vector spelling, every one-slip phrase (as test_compile_spec.py builds
them), and every phrase of 1-4 words the lexicon can spell. Zero cases means
the mutant gives the same answer as the real code on all of them.

The 4-word phrases are 923,521 parses: about ten minutes.

    reference/.venv/Scripts/python.exe prototype/npm-design/rank_clash.py
"""

import itertools
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
MAX_WORDS = int(sys.argv[1]) if len(sys.argv) > 1 else 4

with tempfile.TemporaryDirectory() as tmp:
    src = Path(tmp) / "src"
    shutil.copytree(REPO / "packages" / "python" / "src", src,
                    copy_function=shutil.copy, ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
    render_path = src / "numberwords" / "_render.py"
    render = render_path.read_text(encoding="utf-8")
    merge = "                    if value not in readings or rank > readings[value]:"
    assert render.count(merge) == 1
    render = render.replace(merge,
        "                    if value in readings and rank != readings[value]:\n"
        "                        RANK_CLASHES.append((tuple(tokens[start:end]), value))\n" + merge)
    render = render.replace("class NumberWordsError(ValueError):",
                            "RANK_CLASHES = []\n\n\nclass NumberWordsError(ValueError):", 1)
    render_path.write_text(render, encoding="utf-8")

    sys.path.insert(0, str(src))
    sys.path.insert(0, str(REPO / "reference"))
    import numberwords  # noqa: E402
    from numberwords import _render  # noqa: E402
    import engine  # noqa: E402
    import generate_vectors  # noqa: E402
    from test_compile_spec import SLIP_PHRASE_MAX_WORDS, _near_misses  # noqa: E402
    assert hasattr(_render, "RANK_CLASHES"), "not the instrumented copy"

    def run(name, phrases):
        before, n = len(_render.RANK_CLASHES), 0
        for s in phrases:
            n += 1
            try:
                numberwords.text_to_number(s)
            except numberwords.NumberWordsError:
                pass
        print(f"{name}: {n:,} phrases, {len(_render.RANK_CLASHES) - before} rank clashes", flush=True)

    vectors = json.loads((REPO / "vectors" / "mizo.json").read_text(encoding="utf-8"))
    run("vector spellings", (t for v in vectors for t in v["accepted_inputs"]))

    spec = engine.load(REPO / "languages" / "mizo.yaml")
    slips = set()
    for n in generate_vectors.numbers_to_sweep(spec):
        for text in generate_vectors.accepted_inputs(spec, n):
            slips |= {s for s in _near_misses(text) if len(s.split()) <= SLIP_PHRASE_MAX_WORDS}
    run("one-slip phrases", sorted(slips))

    vocab = sorted({_render._normalize_word(w) for t in _render.LEXICON.values()
                    for e in t.values() for w in e.values()}
                   | set(_render.PARSE["connectors"]) | set(_render.PARSE["aliases"]))
    for k in range(1, MAX_WORDS + 1):
        run(f"all {k}-word phrases", (" ".join(c) for c in itertools.product(vocab, repeat=k)))
    print("examples:", _render.RANK_CLASHES[:5])
