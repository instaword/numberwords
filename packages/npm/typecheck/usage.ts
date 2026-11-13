// Type-checked by `npm run typecheck` (tsc --noEmit), never run: a typed use
// of every export, so index.d.ts cannot drift from what callers write (#75).
// The package's tests check that index.d.ts names what index.js exports.

import { NumberWordsError, numberToText, textToNumber } from "../index.js";

const text: string = numberToText(58);
const n: number = textToNumber(text);
const error: Error = new NumberWordsError("x");
const named: string = error.name;

// @ts-expect-error -- numberToText takes a number
numberToText("58");
// @ts-expect-error -- textToNumber takes a string
textToNumber(58);
// @ts-expect-error -- numberToText returns a string
const wrong: number = numberToText(n);

export { named, wrong };
