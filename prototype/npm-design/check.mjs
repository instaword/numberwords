// The JS port against the vectors and the Python package, for both
// compiled variants, with and without the fold table.
//
// Run from the repo root after emit_js.py and build_data.py:
//
//     node prototype/npm-design/check.mjs

import { makeConverter } from "./render.js";
import { checkClosed, checkPhrases, checkVectors, fold } from "./checks.mjs";

for (const variant of ["code", "data"]) {
  for (const [label, opts] of [["runtime Unicode", {}], ["fold table", { fold }]]) {
    const S = await import(`./out/_mizo.${variant}.js`);
    const c = makeConverter(S, opts);
    const v = checkVectors(c), p = checkPhrases(c), k = checkClosed(c);
    console.log(`${variant} conditions, ${label}: ` +
      `vectors ${v.numbers} numbers / ${v.inputs} inputs, ${v.failures} failures; ` +
      `phrases ${p.phrases}, ${p.differ} differ from Python; ` +
      `closed-world ${k.generated} generated / ${k.listed} listed, ${k.wrong} wrong`);
  }
}
