// Compares the JS port with Python on every Unicode code point in three
// places (out/per_char.json, from per_char.py): once with the runtime's own
// toLowerCase / NFD / \p{M}, once with the fold table. Several minutes.
//
//     node prototype/npm-design/per_char.mjs

import { readFileSync } from "node:fs";
import { makeConverter } from "./render.js";
import { fold } from "./checks.mjs";

const { patterns, accepted } = JSON.parse(
  readFileSync(new URL("out/per_char.json", import.meta.url), "utf8"));
const S = await import("./out/_mizo.data.js");
console.log(`node ${process.versions.node}, unicode ${process.versions.unicode}`);

for (const [label, opts] of [["runtime Unicode", {}], ["fold table", { fold }]]) {
  const c = makeConverter(S, opts);
  let total = 0, jsOnly = 0, pyOnly = 0, otherValue = 0;
  const codePoints = new Set();
  for (let cp = 0; cp < 0x110000; cp++) {
    if (cp >= 0xD800 && cp <= 0xDFFF) continue;
    for (const pattern of patterns) {
      const s = pattern.replace("{}", String.fromCodePoint(cp));
      total++;
      let got; try { got = c.textToNumber(s); } catch { got = null; }
      const want = accepted[s] ?? null;
      if (got === want) continue;
      codePoints.add(cp);
      if (want === null) jsOnly++; else if (got === null) pyOnly++; else otherValue++;
    }
  }
  console.log(`${label}: ${total.toLocaleString("en")} strings; ${codePoints.size} code points differ ` +
    `(JS accepts what Python rejects: ${jsOnly}; Python accepts what JS rejects: ${pyOnly}; ` +
    `different number: ${otherValue})`);
}
