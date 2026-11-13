// The package's public surface: three names, their argument checks and the
// error they raise.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import * as numberwords from "../index.js";
import { NumberWordsError, numberToText, textToNumber } from "../index.js";

const MAX = 9999999999999;

test("the public names are exactly the three agreed (#75)", () => {
  assert.deepEqual(Object.keys(numberwords).sort(), ["NumberWordsError", "numberToText", "textToNumber"]);
});

test("index.d.ts declares exactly what index.js exports", () => {
  // `npm run typecheck` checks a typed use of each declaration; this checks
  // the declarations and the module name the same things.
  const declarations = readFileSync(new URL("../index.d.ts", import.meta.url), "utf8");
  const declared = [...declarations.matchAll(/^export declare (?:function|class) (\w+)/gm)].map((m) => m[1]);
  assert.deepEqual(declared.sort(), Object.keys(numberwords).sort());
});

test("it converts both ways", () => {
  assert.equal(numberToText(58), "sawm nga pariat");
  assert.equal(textToNumber("sawm nga pariat"), 58);
});

for (const n of [-1, MAX + 1]) {
  test(`${n} is outside the supported range`, () => {
    assert.throws(() => numberToText(n), {
      name: "NumberWordsError",
      message: `${n} is outside the supported range [0, ${MAX}]`,
    });
  });
}

for (const [name, n] of [
  ["5.5", 5.5], ["NaN", NaN], ["Infinity", Infinity], ["2^53", 2 ** 53], ["a string", "5"],
  ["a BigInt", 5n], ["a boolean", true], ["null", null], ["undefined", undefined], ["an object", {}],
]) {
  test(`numberToText refuses ${name}`, () => {
    assert.throws(() => numberToText(n), { name: "NumberWordsError", message: /^expected an integer, got / });
  });
}

test("numberToText accepts 5.0, which is the number 5 in JavaScript", () => {
  // Python refuses 5.0, but JavaScript cannot tell it from 5 (#75).
  assert.equal(numberToText(5.0), numberToText(5));
});

for (const [name, text] of [["a number", 5], ["null", null], ["undefined", undefined], ["an array", ["sawm"]]]) {
  test(`textToNumber refuses ${name}`, () => {
    assert.throws(() => textToNumber(text), { name: "NumberWordsError", message: /^expected a string, got / });
  });
}

for (const text of ["", "   ", "hello", "pakhat pakhat"]) {
  test(`${JSON.stringify(text)} names no number`, () => {
    assert.throws(() => textToNumber(text), {
      message: `${JSON.stringify(text)} does not match any number in the supported range`,
    });
  });
}

test("text above the range is refused, naming the bound", () => {
  assert.throws(() => textToNumber("huau sawm"), {
    message: `"huau sawm" reads as more than ${MAX}, outside the supported range [0, ${MAX}]`,
  });
});

test("the error is an Error, named for what it is", () => {
  const error = new NumberWordsError("x");
  assert.ok(error instanceof Error);
  assert.equal(error.name, "NumberWordsError");
  assert.equal(error.message, "x");
});
