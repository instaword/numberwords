// numberwords -- bidirectional text <-> number conversion, starting with
// Mizo (Lushai).
//
// The language behaviour is not written here. It is compiled from
// languages/mizo.yaml into _mizo.js by reference/compile_spec.py, and
// interpreted by render.js, as docs/interpreter-contract.md describes.
//
// See https://github.com/instaword/numberwords

import * as mizo from "./_mizo.js";
import { NumberWordsError, makeConverter } from "./render.js";

const mizoConverter = makeConverter(mizo);

/** The Mizo words for `n`. Throws NumberWordsError outside the supported range, or if `n` is not a safe integer. */
export function numberToText(n) {
  return mizoConverter.numberToText(n);
}

/** The number the Mizo `text` names. Throws NumberWordsError if it names none in the supported range, or is not a string. */
export function textToNumber(text) {
  return mizoConverter.textToNumber(text);
}

export { NumberWordsError };
