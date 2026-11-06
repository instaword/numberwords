// Plants four bugs in render.js, one at a time, and reports which checks
// catch each. Writes out/render_mut_<n>.js; render.js itself is not touched.
//
// Run from the repo root after emit_js.py and build_data.py:
//
//     node prototype/npm-design/mutants.mjs
//
// Mutants 1 and 2 change no answer on today's spec, so no check can catch
// them -- see README.md for why.

import { readFileSync, writeFileSync } from "node:fs";
import { checkClosed, checkVectors, fold } from "./checks.mjs";

const MUTANTS = [
  ["leniency on every phrase, not only one-word ones",
   "const lenient = tokens.length === 1;", "const lenient = true;"],
  ["keep the lowest-ranked derivation of a value, not the highest",
   "cmpRank(rank, readings.get(value)) > 0", "cmpRank(rank, readings.get(value)) < 0"],
  ["let a single digit be a stacked multiplier",
   "if (LEX[table].has(value)) continue;", ";"],
  ["let a whole-phrase-only rule match inside a longer phrase",
   "if (rule.whole_only && !whole) continue;", ";"],
];

const source = readFileSync(new URL("render.js", import.meta.url), "utf8");
const S = await import("./out/_mizo.data.js");

for (const [i, [name, from, to]] of MUTANTS.entries()) {
  if (source.split(from).length !== 2) throw new Error(`mutant ${i + 1} does not apply: ${from}`);
  const file = new URL(`out/render_mut_${i + 1}.js`, import.meta.url);
  writeFileSync(file, source.replace(from, to));
  const { makeConverter } = await import(file.href);
  const c = makeConverter(S, { fold });
  const v = checkVectors(c), k = checkClosed(c);
  console.log(`mutant ${i + 1} (${name}): vectors ${v.failures} failures, ` +
    `closed-world ${k.wrong} wrong -> ${v.failures || k.wrong ? "CAUGHT" : "not caught"}`);
}
