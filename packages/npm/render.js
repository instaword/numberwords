// Interprets a compiled spec such as _mizo.js.
//
// The JavaScript counterpart to packages/python/src/numberwords/_render.py,
// written from docs/interpreter-contract.md: the reference engine
// (reference/engine.py) is the oracle, and vectors/mizo.json and
// vectors/mizo.phrases.json hold this file and the Python package to it.
// Each comment says which part of the contract the code implements, rather
// than restating the code.

export class NumberWordsError extends Error {
  constructor(message) {
    super(message);
    this.name = "NumberWordsError";
  }
}

const COMPARISONS = {
  "==": (a, b) => a === b,
  "!=": (a, b) => a !== b,
  ">": (a, b) => a > b,
  ">=": (a, b) => a >= b,
  "<": (a, b) => a < b,
  "<=": (a, b) => a <= b,
};

// Conditions arrive as data (contract, "Conditions"): "var" and "int" only
// ever appear inside a "cmp", so "and"/"or" combine true/false values and
// every comparison compares two integers. Chains arrive as an explicit "and".
function evaluate(tree, variables) {
  switch (tree[0]) {
    case "cmp":
      return COMPARISONS[tree[1]](evaluate(tree[2], variables), evaluate(tree[3], variables));
    case "and":
      return tree.slice(1).every((t) => evaluate(t, variables));
    case "or":
      return tree.slice(1).some((t) => evaluate(t, variables));
    case "var":
      return variables[tree[1]];
    case "int":
      return tree[1];
    default:
      // Unreachable from a compiled spec: the engine checked every condition
      // when it loaded. A plain Error, not NumberWordsError, because this
      // would be a fault in the package rather than in the caller's input.
      throw new Error(`unknown condition data: ${JSON.stringify(tree)}`);
  }
}

// Ranks compare element by element, and where one is the start of the
// other, the shorter is lower (contract, "Rank"). Never with `>` on the
// arrays themselves: that compares them as text, so [2] > [10].
function compareRanks(a, b) {
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
  }
  return a.length - b.length;
}

// Escaped for a regular expression, with no capturing group, so a declared
// separator is matched as itself and never ends up in the split result. The
// pattern uses the `u` flag, which allows an escape only where the character
// needs one, so inside and outside a character class differ: `\-` is legal
// only inside one.
const escapeOutsideClass = (s) => s.replace(/[\^$\\.*+?()[\]{}|/]/g, "\\$&");
const escapeInClass = (ch) => (/[\\\]\[^-]/.test(ch) ? "\\" + ch : ch);

const quote = (text) => JSON.stringify(text);

function describe(value) {
  if (value === null) return "null";
  if (typeof value === "number") return String(value);
  return typeof value;
}

// `options.multiply` is the one product the parser computes, so that a test
// can hand in one that refuses a product above max + 1, as a fixed-size
// target would have to (contract, "What each target tests").
export function makeConverter(data, { multiply = (a, b) => a * b } = {}) {
  const [low, high] = data.SUPPORTS;
  // Checked when the data loads (zoramt on #101), as well as when the file
  // is built (compile_spec.py): no reading ever holds more than max + 1.
  // Not as `high + 1 <= 2 ** 53`, which is the very trap: at high = 2^53 the
  // sum rounds back to 2^53 and passes. max + 1 <= 2^53 is max <= 2^53 - 1,
  // which is what a safe integer is.
  if (!Number.isSafeInteger(high)) {
    throw new Error(`supports.max is ${high}: max + 1 is above 2^53, which a JavaScript number does not hold exactly`);
  }
  const over = high + 1;

  // Each lexicon table arrives as [key, entry] pairs: an object's keys are
  // strings, and a key read from one would be "5" where it has to be 5.
  const LEXICON = Object.fromEntries(
    Object.entries(data.LEXICON).map(([table, pairs]) => [table, new Map(pairs)]),
  );
  const RULES = data.RULES;
  const CONNECTOR = data.CONNECTOR;
  const PARSE = data.PARSE;

  // The characters of WHITESPACE, never the runtime's \s, which also matches
  // U+FEFF; declared separators tried first (contract, "Words").
  const SEPARATOR = new RegExp(
    [
      ...PARSE.word_separators.map(escapeOutsideClass),
      "[" + Array.from(data.WHITESPACE, escapeInClass).join("") + "]",
    ].join("|"),
    "u",
  );
  const IGNORABLE = new Set(data.IGNORABLE);
  const FOLD = new Map(Object.entries(data.FOLD));

  // Per code point, never per UTF-16 unit: remove IGNORABLE, then apply
  // FOLD, and nothing else -- no lowercasing, no Unicode normalisation.
  function normalizeWord(word) {
    let out = "";
    for (const ch of word) {
      if (!IGNORABLE.has(ch)) out += FOLD.get(ch) ?? ch;
    }
    return out;
  }

  // Already normalised by the compiler; normalising again changes nothing.
  const CONNECTORS = new Set(PARSE.connectors.map(normalizeWord));
  const ALIASES = new Map(
    Object.entries(PARSE.aliases).map(([a, b]) => [normalizeWord(a), normalizeWord(b)]),
  );

  const EMITTING = [...new Set(RULES.filter((r) => r.emit).map((r) => r.scale))].sort(
    (a, b) => b - a,
  );

  function ruleApplies(rule, multiplier, remainder) {
    if (rule.multiplier !== null && rule.multiplier !== multiplier) return false;
    if (rule.condition === null) return true;
    return evaluate(rule.condition, { multiplier, remainder });
  }

  // --- number -> text ----------------------------------------------------

  // The largest emitting scale not above n (not above 1, for 0), or the
  // smallest if none is; then the first rule there that applies.
  function findRule(n) {
    const below = EMITTING.filter((s) => s <= Math.max(n, 1));
    const scale = below.length ? below[0] : EMITTING[EMITTING.length - 1];
    const remainder = n % scale;
    const multiplier = (n - remainder) / scale;
    for (const rule of RULES) {
      if (rule.scale === scale && rule.emit && ruleApplies(rule, multiplier, remainder)) {
        return rule;
      }
    }
    throw new NumberWordsError(`no grammar rule matches n=${n}`);
  }

  // Returns [text, boundaries]: the offsets where each ("remainder")
  // expansion starts, outermost first. The last one is the final addend.
  function render(rule, n) {
    const remainder = n % rule.scale;
    const values = { multiplier: (n - remainder) / rule.scale, remainder };
    let text = "";
    const boundaries = [];
    const walk = (items) => {
      for (const item of items) {
        if (typeof item === "string") {
          text += item;
        } else if (item[0] === "lex") {
          const [, table, key, field] = item;
          text += LEXICON[table].get(typeof key === "number" ? key : values[key])[field];
        } else if (item[0] === "remainder") {
          const start = text.length;
          const [inner, innerBoundaries] = render(findRule(remainder), remainder);
          boundaries.push(start, ...innerBoundaries.map((b) => start + b));
          text += inner;
        } else if (remainder > 0) {
          walk(item[1]); // ["optional", items]
        }
      }
    };
    walk(rule.output);
    return [text, boundaries];
  }

  // The connector's word and one space, where the innermost remainder
  // expansion begins; the space is written, not taken from the separators.
  function withConnector(n, text, boundaries) {
    if (CONNECTOR === null || n < CONNECTOR.min || !boundaries.length) return text;
    const at = boundaries[boundaries.length - 1];
    return text.slice(0, at) + CONNECTOR.word + " " + text.slice(at);
  }

  function numberToText(n) {
    if (typeof n !== "number" || !Number.isSafeInteger(n)) {
      throw new NumberWordsError(`expected an integer, got ${describe(n)}`);
    }
    if (Object.is(n, -0)) n = 0;
    if (!(low <= n && n <= high)) {
      throw new NumberWordsError(`${n} is outside the supported range [${low}, ${high}]`);
    }
    const [text, boundaries] = render(findRule(n), n);
    return withConnector(n, text, boundaries);
  }

  // --- text -> number ----------------------------------------------------

  // Split, normalise each piece, drop the empty ones after normalising, drop
  // connectors, resolve aliases (contract, "Words").
  function tokenize(text) {
    return text
      .split(SEPARATOR)
      .map(normalizeWord)
      .filter((w) => w !== "")
      .filter((w) => !CONNECTORS.has(w))
      .map((w) => ALIASES.get(w) ?? w);
  }

  // Every number some derivation of `tokens` gives, mapped to its best rank
  // (contract, "Readings" and "Rank"). Every reading above the range is the
  // one value max + 1.
  function parseReadings(tokens) {
    const single = tokens.length === 1;
    const cache = new Map();

    function span(start, end, whole, below) {
      const key = `${start},${end},${whole},${below}`;
      let readings = cache.get(key);
      if (readings !== undefined) return readings;
      readings = new Map();
      for (const rule of RULES) {
        if (below !== null && rule.scale >= below) continue;
        if (rule.whole_only && !whole) continue;
        const initial = rule.multiplier !== null ? { multiplier: rule.multiplier } : {};
        for (const bound of match(rule.output, start, end, initial, rule, whole)) {
          if (!("multiplier" in bound)) continue;
          const multiplier = bound.multiplier;
          const remainder = bound.remainder ?? 0;
          if (!ruleApplies(rule, multiplier, remainder)) continue;
          let rank = bound.remainderRank ?? [];
          if (rule.stacks) {
            rank = [bound.multiplierWords ?? 0, ...(bound.multiplierRank ?? []), ...rank];
          }
          // The remainder first, so the division never sees a negative
          // number; floor division, and before multiplying (contract,
          // "Arithmetic").
          const value =
            remainder > high || multiplier > Math.floor((high - remainder) / rule.scale)
              ? over
              : multiply(multiplier, rule.scale) + remainder;
          const best = readings.get(value);
          if (best === undefined || compareRanks(rank, best) > 0) readings.set(value, rank);
        }
      }
      cache.set(key, readings);
      return readings;
    }

    function bind(bound, name, value) {
      if (name in bound && bound[name] !== value) return null;
      return { ...bound, [name]: value };
    }

    function* match(items, position, end, bound, rule, whole) {
      if (!items.length) {
        if (position === end) yield bound;
        return;
      }
      const [item, ...rest] = items;
      if (typeof item === "string") {
        yield* match(rest, position, end, bound, rule, whole);
      } else if (item[0] === "lex") {
        if (position >= end) return;
        const [, table, key, field] = item;
        const token = tokens[position];
        if (typeof key === "number") {
          if (normalizeWord(LEXICON[table].get(key)[field]) === token) {
            yield* match(rest, position + 1, end, bound, rule, whole);
          }
          return;
        }
        // The fields PARSE.accepted_forms lists, only when the whole input
        // is a single word.
        const extras = single && whole ? (PARSE.accepted_forms[table] ?? []) : [];
        const fields = [field, ...extras.filter((f) => f !== field)];
        for (const [entryKey, entry] of LEXICON[table]) {
          if (fields.some((f) => f in entry && normalizeWord(entry[f]) === token)) {
            const rebound = bind(bound, key, entryKey);
            if (rebound !== null) {
              if (key === "multiplier") rebound.multiplierWords = 1;
              yield* match(rest, position + 1, end, rebound, rule, whole);
            }
          }
        }
        if (key === "multiplier" && rule.stacks) {
          // A numeral read by the rules below this scale. A value the table
          // has a word for is the word's to fill, but the capped value never
          // is (contract, "Readings").
          for (let stop = position + 1; stop <= end; stop++) {
            for (const [value, rank] of span(position, stop, false, rule.scale)) {
              if (value <= high && LEXICON[table].has(value)) continue;
              const rebound = bind(bound, "multiplier", value);
              if (rebound !== null) {
                rebound.multiplierWords = stop - position;
                rebound.multiplierRank = rank;
                yield* match(rest, stop, end, rebound, rule, whole);
              }
            }
          }
        }
      } else if (item[0] === "remainder") {
        for (let stop = position + 1; stop <= end; stop++) {
          for (const [value, rank] of span(position, stop, false, rule.scale)) {
            if (0 < value && value < rule.scale) {
              const rebound = bind(bound, "remainder", value);
              if (rebound !== null) {
                rebound.remainderRank = rank;
                yield* match(rest, stop, end, rebound, rule, whole);
              }
            }
          }
        }
      } else if (item[0] === "optional") {
        const absent = bind(bound, "remainder", 0);
        if (absent !== null) yield* match(rest, position, end, absent, rule, whole);
        yield* match([...item[1], ["present"], ...rest], position, end, bound, rule, whole);
      } else if (item[0] === "present") {
        if ((bound.remainder ?? 0) > 0) yield* match(rest, position, end, bound, rule, whole);
      }
    }

    if (!tokens.length) return new Map();
    return span(0, tokens.length, true, null);
  }

  // The top rank wins; a tie at the top is refused, and so is a winner
  // outside the range, never swapped for a lower reading (contract,
  // "Choosing").
  function textToNumber(text) {
    if (typeof text !== "string") {
      throw new NumberWordsError(`expected a string, got ${describe(text)}`);
    }
    const readings = parseReadings(tokenize(text));
    if (!readings.size) {
      throw new NumberWordsError(`${quote(text)} does not match any number in the supported range`);
    }
    let top = null;
    for (const rank of readings.values()) {
      if (top === null || compareRanks(rank, top) > 0) top = rank;
    }
    const winners = [...readings]
      .filter(([, rank]) => compareRanks(rank, top) === 0)
      .map(([value]) => value)
      .sort((a, b) => a - b);
    if (winners.length > 1) {
      const named = winners.map((n) => (n > high ? `more than ${high}` : String(n))).join(", ");
      throw new NumberWordsError(`${quote(text)} is ambiguous: matches [${named}]`);
    }
    const n = winners[0];
    if (n > high) {
      throw new NumberWordsError(
        `${quote(text)} reads as more than ${high}, outside the supported range [${low}, ${high}]`,
      );
    }
    if (n < low) {
      throw new NumberWordsError(
        `${quote(text)} reads as ${n}, outside the supported range [${low}, ${high}]`,
      );
    }
    return n;
  }

  return { numberToText, textToNumber, tokenize, parseReadings, normalizeWord };
}
