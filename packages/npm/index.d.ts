// Hand-written to match index.js (#75). `npm run typecheck` checks a typed
// use of every export against these, and the package's tests check that
// these name exactly what index.js exports.

/**
 * The Mizo words for `n`.
 *
 * Throws NumberWordsError if `n` is outside the supported range, or is not
 * a safe integer. `5.0` is the same number as `5` in JavaScript, so it is
 * accepted.
 */
export declare function numberToText(n: number): string;

/**
 * The number the Mizo `text` names.
 *
 * Accepts more spellings than numberToText() writes: case and diacritics are
 * ignored, "-" works as a word separator, the connector "leh" is dropped, and
 * a lone digit may be given in either of its forms ("khat" as well as
 * "pakhat"). Throws NumberWordsError if the text names no number in the
 * supported range, or is not a string.
 */
export declare function textToNumber(text: string): number;

/** Raised for a number outside the supported range, for text that names no number in it, and for an argument of the wrong type. */
export declare class NumberWordsError extends Error {
  constructor(message: string);
}
