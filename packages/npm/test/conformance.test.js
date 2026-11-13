// The package against vectors/mizo.json and vectors/mizo.phrases.json, the
// shared files every target passes (docs/interpreter-contract.md, "What each
// target tests"). The reference engine generates them; this package is
// checked against them; neither imports the other.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { NumberWordsError, numberToText, textToNumber } from "../index.js";

const read = (name) =>
  JSON.parse(readFileSync(new URL(`../../../vectors/${name}`, import.meta.url), "utf8"));
const vectors = read("mizo.json");
const phrases = read("mizo.phrases.json");

// Asserted rather than assumed, as in the Python package's suite: an empty
// or truncated file would otherwise make every loop below pass by having
// nothing to check. A range or vocabulary change bumps these by hand.
const EXPECTED_VECTORS = 1420;
const EXPECTED_ACCEPTED_INPUTS = 8883;
const EXPECTED_PHRASE_VOCABULARY = 34;
const EXPECTED_PHRASES = 40494;
const EXPECTED_ACCEPTED_PHRASES = 2909;
const EXPECTED_LISTED_PHRASES = { one_slip: [6306, 2518], stacked: [19, 15] };

// The number a phrase names, or null where the package refuses it. Only
// NumberWordsError counts as a refusal: anything else is a fault.
function answer(text) {
  try {
    return textToNumber(text);
  } catch (error) {
    if (error instanceof NumberWordsError) return null;
    throw error;
  }
}

function* everyPhrase() {
  const { vocabulary, max_words: maxWords } = phrases;
  function* build(prefix, length) {
    if (length === 0) {
      yield prefix.join(" ");
      return;
    }
    for (const word of vocabulary) yield* build([...prefix, word], length - 1);
  }
  for (let length = 1; length <= maxWords; length++) yield* build([], length);
}

test("the vectors are the size they should be", () => {
  assert.equal(vectors.length, EXPECTED_VECTORS);
  assert.equal(
    vectors.reduce((sum, v) => sum + v.accepted_inputs.length, 0),
    EXPECTED_ACCEPTED_INPUTS,
  );
});

test("every vector's number is a string and its text an accepted input", () => {
  // Numbers are strings in the file (#12): a JavaScript number would hold
  // today's, but not the next ceiling's.
  for (const v of vectors) {
    assert.equal(typeof v.number, "string");
    assert.ok(v.accepted_inputs.includes(v.text), v.number);
  }
});

test("numberToText matches every vector", () => {
  for (const v of vectors) assert.equal(numberToText(Number(v.number)), v.text, v.number);
});

test("textToNumber accepts every accepted input", () => {
  for (const v of vectors) {
    for (const text of v.accepted_inputs) assert.equal(textToNumber(text), Number(v.number), text);
  }
});

test("both round trips hold on every vector", () => {
  for (const v of vectors) {
    const n = Number(v.number);
    assert.equal(textToNumber(numberToText(n)), n);
    for (const text of v.accepted_inputs) assert.equal(numberToText(textToNumber(text)), v.text);
  }
});

test("the phrase file is the size it should be", () => {
  assert.equal(phrases.vocabulary.length, EXPECTED_PHRASE_VOCABULARY);
  let count = 0;
  for (const _ of everyPhrase()) count++;
  assert.equal(count, EXPECTED_PHRASES);
  assert.equal(Object.keys(phrases.accepted).length, EXPECTED_ACCEPTED_PHRASES);
  for (const [section, [listed, numbered]] of Object.entries(EXPECTED_LISTED_PHRASES)) {
    const values = Object.values(phrases[section]);
    assert.deepEqual([values.length, values.filter((n) => n !== null).length], [listed, numbered], section);
  }
});

test("textToNumber agrees with the phrase file's closed world", () => {
  // A listed phrase gives its number; every phrase not listed is refused.
  // The second half is what the vectors cannot state.
  const wrong = [];
  const built = new Set();
  for (const text of everyPhrase()) {
    built.add(text);
    const expected = text in phrases.accepted ? Number(phrases.accepted[text]) : null;
    const got = answer(text);
    if (got !== expected) wrong.push([text, expected, got]);
  }
  assert.deepEqual(wrong.slice(0, 10), []);
  // A listed phrase the loop never builds would never be checked.
  assert.deepEqual(Object.keys(phrases.accepted).filter((t) => !built.has(t)), []);
});

for (const section of ["one_slip", "stacked"]) {
  test(`textToNumber agrees with the phrase file's ${section} phrases`, () => {
    // Longer phrases, each listed with its number or null: where a parser
    // that agrees on every short phrase can still differ. Some take greed
    // past the first number of a rank, which no phrase of the closed world
    // needs, and one catches ranks compared as text.
    const wrong = [];
    for (const [text, number] of Object.entries(phrases[section])) {
      const expected = number === null ? null : Number(number);
      const got = answer(text);
      if (got !== expected) wrong.push([text, expected, got]);
    }
    assert.deepEqual(wrong.slice(0, 10), []);
  });
}
