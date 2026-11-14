// What the shared files never reach, which docs/interpreter-contract.md
// ("What each target tests") asks each target to test itself. Several are
// the Python package's tests of the same name, written again here: the two
// implementations are independent, and no vector joins them on these.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import * as mizo from "../_mizo.js";
import { NumberWordsError, numberToText, textToNumber } from "../index.js";
import { makeConverter } from "../render.js";

const converter = makeConverter(mizo);
const codePoints = function* () {
  for (let c = 0; c <= 0x10ffff; c++) yield String.fromCodePoint(c);
};
const label = (ch) => `U+${ch.codePointAt(0).toString(16).toUpperCase().padStart(4, "0")}`;

// --- whitespace, ignorable characters and the fold table -------------------

test("the shipped whitespace is Unicode's White_Space", () => {
  // Stated independently of the engine: JavaScript's \s also matches U+FEFF,
  // and \p{White_Space} is the property itself.
  const derived = [...codePoints()].filter((ch) => /\p{White_Space}/u.test(ch));
  assert.deepEqual([...mizo.WHITESPACE].sort(), derived.sort());
  assert.equal(mizo.WHITESPACE.length, 25);
});

test("the renderer does not trust the declared separators alone", () => {
  // The spec declares only "-"; whitespace has to come from WHITESPACE.
  assert.ok(!mizo.PARSE.word_separators.includes(" "));
  assert.equal(textToNumber("sawm nga pariat"), 58);
});

for (const ch of mizo.WHITESPACE) {
  test(`${label(ch)}, shipped whitespace, separates words`, () => {
    assert.equal(textToNumber("sawm" + ch + "nga pariat"), 58);
  });
}

test("nothing but the shipped whitespace and declared separators splits words", () => {
  const splits = [...codePoints()].filter((ch) => converter.tokenize("a" + ch + "b").length === 2);
  const expected = [...mizo.WHITESPACE, ...mizo.PARSE.word_separators.filter((s) => s.length === 1)];
  assert.deepEqual(splits.sort(), expected.sort());
});

for (const ch of ["\x1c", "\x1d", "\x1e", "\x1f"]) {
  test(`${label(ch)}, which Python's isspace() takes for a space, is refused`, () => {
    assert.throws(() => textToNumber("sawm" + ch + "nga pariat"), NumberWordsError);
  });
}

// Enumerated by position, as in the engine and the Python package (#56).
const IGNORABLE_POSITIONS = {
  "start of the string": "﻿sawm nga pariat",
  "end of the string": "sawm nga pariat﻿",
  "start of an inner word": "sawm ﻿nga pariat",
  "end of an inner word": "sawm⁠ nga pariat",
  "inside a word": "sa\xadwm nga pariat",
  "standing alone between separators": "sawm ​ nga pariat",
  "standing alone, two of them": "sawm ​﻿ nga pariat",
  "standing alone at the end": "sawm nga pariat ­",
};

for (const [position, text] of Object.entries(IGNORABLE_POSITIONS)) {
  test(`an ignorable character is stripped: ${position}`, () => {
    assert.equal(textToNumber(text), 58);
  });
}

for (const ch of mizo.IGNORABLE) {
  test(`${label(ch)}, shipped ignorable, is stripped inside a word`, () => {
    assert.equal(textToNumber("sa" + ch + "wm nga pariat"), 58);
  });
}

test("nothing but the shipped ignorable characters and folded marks is stripped", () => {
  // The fold table maps a combining mark to "", so those come out empty too;
  // anything else that did would be a character the package removed itself.
  const marks = Object.entries(mizo.FOLD).filter(([, folded]) => folded === "").map(([ch]) => ch);
  const stripped = [...codePoints()].filter((ch) => converter.normalizeWord(ch) === "");
  assert.deepEqual(stripped.sort(), [...mizo.IGNORABLE, ...marks].sort());
});

test("every shipped fold entry is applied", () => {
  const wrong = Object.entries(mizo.FOLD).filter(([ch, folded]) => converter.normalizeWord(ch) !== folded);
  assert.deepEqual(wrong, []);
});

test("nothing but the shipped fold table changes a character", () => {
  // No toLowerCase and no normalize() of the package's own: both follow the
  // runtime's Unicode version, which the table exists to keep out.
  const ignorable = new Set(mizo.IGNORABLE);
  const changed = [...codePoints()].filter(
    (ch) => !ignorable.has(ch) && converter.normalizeWord(ch) !== ch,
  );
  assert.deepEqual(changed.sort(), Object.keys(mizo.FOLD).sort());
});

for (const [name, text] of [
  ["uppercase with the accent", "SÂWM"],
  ["another accent", "sáwm"],
  ["a separate circumflex", "sâwm"],
]) {
  test(`a folded spelling parses: ${name}`, () => assert.equal(textToNumber(text), 10));
}

for (const [name, mark] of [["a Hebrew point", "ְ"], ["a low line", "̲"]]) {
  test(`a mark no accented Latin letter uses is not ignored: ${name}`, () => {
    assert.throws(() => textToNumber("sâwm" + mark), NumberWordsError);
  });
}

// --- hand-built tables, for what Mizo never does ---------------------------

// A compiled spec from a few hand-written rules: Mizo's whitespace and
// ignorable characters, and nothing else declared.
function table({ supports, lexicon, rules }) {
  const rule = { multiplier: null, condition: null, emit: true, whole_only: false, stacks: false };
  return {
    SUPPORTS: supports,
    LEXICON: Object.fromEntries(
      Object.entries(lexicon).map(([t, entries]) => [t, Object.entries(entries).map(([k, e]) => [Number(k), e])]),
    ),
    RULES: rules.map((r) => ({ ...rule, ...r })),
    CONNECTOR: null,
    PARSE: { case_insensitive: false, strip_diacritics: false, word_separators: [], accepted_forms: {}, connectors: [], aliases: {} },
    WHITESPACE: mizo.WHITESPACE,
    IGNORABLE: mizo.IGNORABLE,
    FOLD: {},
  };
}
const word = ["lex", "units", "multiplier", "w"];

test("a tie at the top rank is refused as ambiguous", () => {
  // "one ten" is 10 by `tens` and 100 by `hundred`. Neither stacks, so they
  // tie, and greed must not settle it.
  const { textToNumber: parse } = makeConverter(table({
    supports: [0, 1000],
    lexicon: { units: { 1: { w: "one" } }, scales: { 10: { w: "ten" } } },
    rules: [
      { name: "units", scale: 1, output: [word] },
      { name: "tens", scale: 10, output: [word, " ", ["lex", "scales", 10, "w"]] },
      { name: "hundred", scale: 100, multiplier: 1, output: [["lex", "units", 1, "w"], " ", ["lex", "scales", 10, "w"]] },
    ],
  }));
  assert.throws(() => parse("one ten"), { name: "NumberWordsError", message: '"one ten" is ambiguous: matches [10, 100]' });
});

test("a reading below the range is refused, naming it", () => {
  const { textToNumber: parse } = makeConverter(table({
    supports: [5, 5],
    lexicon: { units: { 3: { w: "three" }, 5: { w: "five" } } },
    rules: [{ name: "units", scale: 1, output: [word] }],
  }));
  assert.throws(() => parse("three"), { message: '"three" reads as 3, outside the supported range [5, 5]' });
  assert.equal(parse("five"), 5);
});

// Beyond the contract's list: three of its runtime traps, and one rule
// kind, where Mizo's data gives the same answers whether the code is right
// or wrong. Its one separator is "-", plain text in a pattern; it ships no
// character outside the BMP; and its one emit: never rule comes after an
// emitting rule that covers every number it would.

test("a declared separator that is a pattern character splits only where it stands", () => {
  // Left unescaped, "." would match every character and split each word
  // into nothing.
  const data = table({
    supports: [0, 100],
    lexicon: { units: { 2: { w: "two" } }, scales: { 10: { w: "ten" } } },
    rules: [{ name: "tens", scale: 10, output: [word, " ", ["lex", "scales", 10, "w"]] }],
  });
  data.PARSE = { ...data.PARSE, word_separators: ["."] };
  const { textToNumber: parse } = makeConverter(data);
  assert.equal(parse("two.ten"), 20);
  assert.equal(parse("two ten"), 20);
});

test("a character outside the BMP is removed or folded whole", () => {
  // U+1D173 is ignorable, and U+1D428 (bold small o) folds to "o" here.
  // Walked by UTF-16 unit, each is two halves that neither table holds.
  const data = table({
    supports: [0, 100],
    lexicon: { units: { 2: { w: "two" } }, scales: { 10: { w: "ten" } } },
    rules: [{ name: "tens", scale: 10, output: [word, " ", ["lex", "scales", 10, "w"]] }],
  });
  data.IGNORABLE = mizo.IGNORABLE + "\u{1D173}";
  data.FOLD = { "\u{1D428}": "o" };
  const { textToNumber: parse } = makeConverter(data);
  assert.equal(parse("tw\u{1D428} t\u{1D173}en"), 20);
});

test("an emit: never rule is never written, even where it comes first", () => {
  const data = table({
    supports: [0, 100],
    lexicon: { units: { 2: { w: "two" } }, scales: { 10: { w: "ten" } } },
    rules: [
      { name: "tens_reversed", scale: 10, emit: false, output: [["lex", "scales", 10, "w"], " ", word] },
      { name: "tens", scale: 10, output: [word, " ", ["lex", "scales", 10, "w"]] },
    ],
  });
  const { numberToText: render, textToNumber: parse } = makeConverter(data);
  assert.equal(render(20), "two ten");
  assert.equal(parse("ten two"), 20);
});

// A product the parser computes, refused above `limit`, as a target with
// fixed-size integers would have to (#102). Where it does not throw it gives
// the same product as plain multiplication.
const checked = (limit) => (a, b) => {
  const product = a * b;
  if (product > limit) throw new RangeError(`${a} x ${b} is above ${limit}`);
  return product;
};

test("a capped multiplier is never taken for a word", () => {
  // "big" is the key max + 1, the capped value; "two hundred thousand"
  // (stacked, 200 x 1000) must still read as above the range.
  const data = table({
    supports: [0, 150],
    lexicon: { units: { 1: { w: "one" }, 2: { w: "two" }, 151: { w: "big" } }, scales: { 100: { w: "hundred" }, 1000: { w: "thousand" } } },
    rules: [
      { name: "units", scale: 1, output: [word] },
      { name: "hundreds", scale: 100, output: [word, " ", ["lex", "scales", 100, "w"]] },
      { name: "thousands", scale: 1000, stacks: true, output: [word, " ", ["lex", "scales", 1000, "w"]] },
    ],
  });
  const { textToNumber: parse } = makeConverter(data, { multiply: checked(151) });
  assert.throws(() => parse("two hundred thousand"), { message: /reads as more than 150, outside/ });
});

test("a capped remainder with a zero multiplier is above the range", () => {
  // With max 50, "seventy" is a remainder capped at 51. The remainder is
  // checked before any division, which floor and truncation agree on then.
  const data = table({
    supports: [0, 50],
    lexicon: { units: { 0: { w: "zero" }, 1: { w: "one" }, 70: { w: "seventy" } }, scales: { 100: { w: "hundred" } } },
    rules: [
      { name: "units", scale: 1, output: [word] },
      { name: "hundreds", scale: 100, output: [word, " ", ["lex", "scales", 100, "w"], ["optional", [" ", ["remainder"]]]] },
    ],
  });
  const c = makeConverter(data, { multiply: checked(51) });
  assert.deepEqual([...c.parseReadings(["zero", "hundred", "seventy"]).keys()], [51]);
  assert.throws(() => c.textToNumber("zero hundred seventy"), { message: /reads as more than 50, outside/ });
});

// --- arithmetic --------------------------------------------------------------

const phrases = JSON.parse(readFileSync(new URL("../../../vectors/mizo.phrases.json", import.meta.url), "utf8"));
const answer = (parse, text) => {
  try {
    return parse(text);
  } catch (error) {
    if (error instanceof NumberWordsError) return null;
    throw error;
  }
};

test("no phrase needs a product above max + 1", () => {
  // Every listed phrase and every one of the closed world's accepted
  // phrases, parsed with the checked product: none needs more, and the
  // answers are the plain ones.
  const limit = mizo.SUPPORTS[1] + 1;
  const { textToNumber: parse } = makeConverter(mizo, { multiply: checked(limit) });
  const texts = [...Object.keys(phrases.accepted), ...Object.keys(phrases.one_slip), ...Object.keys(phrases.stacked)];
  const differ = texts.filter((text) => answer(parse, text) !== answer(textToNumber, text));
  assert.deepEqual(differ, []);
});

for (let words = 2; words <= 5; words++) {
  test(`a chain of ${words} scale words and a digit holds no more than max + 1`, () => {
    // Uncapped, six such words read 9 x 10^35.
    const chain = ["tlûklehdingâwn", "vaibêlchhetak", "vaibêlchhe", "maktaduai", "nuai"];
    const c = makeConverter(mizo, { multiply: checked(mizo.SUPPORTS[1] + 1) });
    const readings = c.parseReadings(c.tokenize([...chain.slice(0, words), "kua"].join(" ")));
    assert.equal(Math.max(...readings.keys()), mizo.SUPPORTS[1] + 1);
  });
}

test("a range whose max + 1 a JavaScript number cannot hold is refused when it loads", () => {
  // zoramt on #101: checked when the data loads, as well as when
  // compile_spec.py writes it.
  assert.throws(() => makeConverter({ ...mizo, SUPPORTS: [0, 2 ** 53] }), /max \+ 1 is above 2\^53/);
  makeConverter({ ...mizo, SUPPORTS: [0, 2 ** 53 - 1] });
});

test("negative zero is zero", () => {
  assert.equal(numberToText(-0), numberToText(0));
});
