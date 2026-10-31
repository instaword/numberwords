// Shared checks, used by check.mjs and mutants.mjs.
//
//   1. vectors/mizo.json, both directions, for both compiled variants
//   2. every phrase of 1-3 words the lexicon can spell, against the
//      Python package's answers (out/phrases.json)
//   3. the closed-world file (out/closed.json): generate every phrase from
//      the vocabulary; listed ones must give their value, all others must
//      be rejected

import { readFileSync } from "node:fs";

const here = new URL(".", import.meta.url);
const read = (p) => JSON.parse(readFileSync(new URL(p, here), "utf8"));
const vectors = read("../../vectors/mizo.json");
const phrases = read("out/phrases.json").results;
const closed = read("out/closed.json");
export const fold = read("out/fold.json").fold;

function parseOrNull(c, s) {
  try { return c.textToNumber(s); } catch { return null; }
}

export function checkVectors(c) {
  let failures = 0, inputs = 0;
  for (const v of vectors) {
    const n = Number(v.number);
    if (c.numberToText(n) !== v.text) failures++;
    for (const t of v.accepted_inputs) {
      inputs++;
      if (parseOrNull(c, t) !== n) failures++;
      else if (c.numberToText(c.textToNumber(t)) !== v.text) failures++;
    }
  }
  return { numbers: vectors.length, inputs, failures };
}

export function checkPhrases(c) {
  let differ = 0;
  for (const [s, want] of Object.entries(phrases)) if (parseOrNull(c, s) !== want) differ++;
  return { phrases: Object.keys(phrases).length, differ };
}

export function checkClosed(c) {
  let total = 0, wrong = 0;
  const walk = (prefix, k) => {
    if (k === 0) return;
    for (const w of closed.vocabulary) {
      const p = [...prefix, w], s = p.join(" ");
      total++;
      if (parseOrNull(c, s) !== (closed.accepted[s] ?? null)) wrong++;
      walk(p, k - 1);
    }
  };
  walk([], closed.max_words);
  return { generated: total, listed: Object.keys(closed.accepted).length, wrong };
}
