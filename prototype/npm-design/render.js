// Prototype JS port of packages/python/src/numberwords/_render.py (#75).
// makeConverter(S, options) takes either compiled variant from emit_js.py.
// options.fold: the fold table (out/fold.json) in place of the runtime's
// toLowerCase / NFD / \p{M}.

export class NumberWordsError extends Error {
  constructor(message) { super(message); this.name = "NumberWordsError"; }
}

const WHITESPACE =
  "\t\n\v\f\r \x85\xa0        " +
  "        　";
const IGNORABLE = /[​﻿⁠‌‍­]/g;
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\\/-]/g, "\\$&");

function evalTree(t, v) {
  switch (t[0]) {
    case "and": return t.slice(1).every((x) => evalTree(x, v));
    case "or": return t.slice(1).some((x) => evalTree(x, v));
    case "var": return v[t[1]];
    case "int": return t[1];
    case "cmp": {
      const a = evalTree(t[2], v), b = evalTree(t[3], v);
      switch (t[1]) {
        case ">": return a > b; case ">=": return a >= b;
        case "<": return a < b; case "<=": return a <= b;
        case "==": return a === b; case "!=": return a !== b;
      }
    }
  }
  throw new Error("bad condition " + JSON.stringify(t));
}

// Python tuple ordering.
function cmpRank(a, b) {
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
  }
  return a.length - b.length;
}

export function makeConverter(S, { foldDiacritics, fold } = {}) {
  const FOLD = fold ? new Map(Object.entries(fold)) : null;
  const { LEXICON, RULES, CONNECTOR, PARSE, SUPPORTS } = S;
  const LEX = Object.fromEntries(
    Object.entries(LEXICON).map(([t, pairs]) => [t, new Map(pairs)]));

  const SEP = new RegExp(
    [...PARSE.word_separators.map(esc), "[" + esc(WHITESPACE) + "]"].join("|"));

  const stripMarks = foldDiacritics ??
    ((w) => w.normalize("NFD").replace(/\p{M}/gu, ""));

  function normalizeWord(word) {
    word = word.replace(IGNORABLE, "");
    if (FOLD) return Array.from(word, (ch) => FOLD.get(ch) ?? ch).join("");
    if (PARSE.case_insensitive) word = word.toLowerCase();
    if (PARSE.strip_diacritics) word = stripMarks(word);
    return word;
  }

  const CONNECTORS = new Set(PARSE.connectors.map(normalizeWord));
  const ALIASES = new Map(Object.entries(PARSE.aliases)
    .map(([a, c]) => [normalizeWord(a), normalizeWord(c)]));
  const EMITTING = [...new Set(RULES.filter((r) => r.emit).map((r) => r.scale))]
    .sort((a, b) => b - a);

  function ruleApplies(rule, multiplier, remainder) {
    if (rule.multiplier !== null && rule.multiplier !== multiplier) return false;
    const c = rule.condition;
    if (c === null) return true;
    const v = { multiplier, remainder };
    return typeof c === "function" ? Boolean(c(v)) : evalTree(c, v);
  }

  function divmod(n, d) { const r = n % d; return [(n - r) / d, r]; }

  function findRule(n) {
    const cands = EMITTING.filter((s) => s <= Math.max(n, 1));
    const scale = cands.length ? cands[0] : EMITTING[EMITTING.length - 1];
    const [m, r] = divmod(n, scale);
    for (const rule of RULES) {
      if (rule.scale === scale && rule.emit && ruleApplies(rule, m, r)) return rule;
    }
    throw new NumberWordsError(`no grammar rule matches n=${n}`);
  }

  function render(rule, n) {
    const [multiplier, remainder] = divmod(n, rule.scale);
    const values = { multiplier, remainder };
    let text = "";
    const boundaries = [];
    const walk = (items) => {
      for (const item of items) {
        if (typeof item === "string") text += item;
        else if (item[0] === "lex") {
          const [, table, key, field] = item;
          text += LEX[table].get(key in values ? values[key] : key)[field];
        } else if (item[0] === "remainder") {
          const start = text.length;
          const [sub, subB] = render(findRule(remainder), remainder);
          boundaries.push(start, ...subB.map((b) => start + b));
          text += sub;
        } else if (remainder) walk(item[1]);
      }
    };
    walk(rule.output);
    return [text, boundaries];
  }

  function withConnector(n, text, boundaries) {
    if (CONNECTOR === null || n < CONNECTOR.min || !boundaries.length) return text;
    const at = boundaries[boundaries.length - 1];
    return text.slice(0, at) + CONNECTOR.word + " " + text.slice(at);
  }

  function tokenize(text) {
    return text.split(SEP).map(normalizeWord).filter((w) => w)
      .filter((w) => !CONNECTORS.has(w)).map((w) => ALIASES.get(w) ?? w);
  }

  function acceptableFields(table, named, lenient) {
    if (!lenient) return [named];
    const extras = PARSE.accepted_forms[table] ?? [];
    return [named, ...extras.filter((f) => f !== named)];
  }

  function parseReadings(tokens) {
    const lenient = tokens.length === 1;
    const cache = new Map();

    function span(start, end, whole, below) {
      const key = `${start},${end},${whole},${below}`;
      if (!cache.has(key)) {
        const readings = new Map();
        for (const rule of RULES) {
          if (below !== null && rule.scale >= below) continue;
          if (rule.whole_only && !whole) continue;
          const initial = {};
          if (rule.multiplier !== null) initial.multiplier = rule.multiplier;
          for (const bound of match(rule.output, start, end, initial, rule, whole)) {
            if (!("multiplier" in bound)) continue;
            const m = bound.multiplier, r = bound.remainder ?? 0;
            if (!ruleApplies(rule, m, r)) continue;
            let rank = bound._remainder_rank ?? [];
            if (rule.stacks) {
              rank = [bound._multiplier_words ?? 0, ...(bound._multiplier_rank ?? []), ...rank];
            }
            const value = m * rule.scale + r;
            if (!readings.has(value) || cmpRank(rank, readings.get(value)) > 0) {
              readings.set(value, rank);
            }
          }
        }
        cache.set(key, readings);
      }
      return cache.get(key);
    }

    function bind(bound, name, value) {
      if (name in bound && bound[name] !== value) return null;
      return { ...bound, [name]: value };
    }

    function* match(items, pos, end, bound, rule, whole) {
      if (!items.length) { if (pos === end) yield bound; return; }
      const [item, ...rest] = items;
      if (typeof item === "string") { yield* match(rest, pos, end, bound, rule, whole); return; }
      if (item[0] === "lex") {
        if (pos >= end) return;
        const [, table, key, field] = item;
        const token = tokens[pos];
        if (typeof key === "number") {
          if (normalizeWord(LEX[table].get(key)[field]) === token) {
            yield* match(rest, pos + 1, end, bound, rule, whole);
          }
          return;
        }
        const stacks = key === "multiplier" && rule.stacks;
        const fields = acceptableFields(table, field, lenient && whole);
        for (const [entryKey, entry] of LEX[table]) {
          if (fields.some((f) => f in entry && normalizeWord(entry[f]) === token)) {
            const rb = bind(bound, key, entryKey);
            if (rb !== null) {
              if (key === "multiplier") rb._multiplier_words = 1;
              yield* match(rest, pos + 1, end, rb, rule, whole);
            }
          }
        }
        if (stacks) {
          for (let stop = pos + 1; stop <= end; stop++) {
            for (const [value, rank] of span(pos, stop, false, rule.scale)) {
              if (LEX[table].has(value)) continue;
              const rb = bind(bound, "multiplier", value);
              if (rb !== null) {
                rb._multiplier_words = stop - pos;
                rb._multiplier_rank = rank;
                yield* match(rest, stop, end, rb, rule, whole);
              }
            }
          }
        }
      } else if (item[0] === "remainder") {
        for (let stop = pos + 1; stop <= end; stop++) {
          for (const [value, rank] of span(pos, stop, false, rule.scale)) {
            if (0 < value && value < rule.scale) {
              const rb = bind(bound, "remainder", value);
              if (rb !== null) {
                rb._remainder_rank = rank;
                yield* match(rest, stop, end, rb, rule, whole);
              }
            }
          }
        }
      } else if (item[0] === "optional") {
        const rb = bind(bound, "remainder", 0);
        if (rb !== null) yield* match(rest, pos, end, rb, rule, whole);
        yield* match([...item[1], ["end_optional"], ...rest], pos, end, bound, rule, whole);
      } else if (item[0] === "end_optional") {
        if ((bound.remainder ?? 0) > 0) yield* match(rest, pos, end, bound, rule, whole);
      }
    }

    if (!tokens.length) return new Map();
    return new Map(span(0, tokens.length, true, null));
  }

  function numberToText(n) {
    if (typeof n !== "number" || !Number.isSafeInteger(n)) {
      throw new NumberWordsError(`expected an integer, got ${typeof n === "number" ? n : typeof n}`);
    }
    if (Object.is(n, -0)) n = 0;
    const [low, high] = SUPPORTS;
    if (!(low <= n && n <= high)) {
      throw new NumberWordsError(`${n} is outside the supported range [${low}, ${high}]`);
    }
    const [text, b] = render(findRule(n), n);
    return withConnector(n, text, b);
  }

  function textToNumber(text) {
    if (typeof text !== "string") throw new NumberWordsError(`expected a string, got ${typeof text}`);
    const readings = parseReadings(tokenize(text));
    if (!readings.size) {
      throw new NumberWordsError(`${JSON.stringify(text)} does not match any number in the supported range`);
    }
    let top = null;
    for (const r of readings.values()) if (top === null || cmpRank(r, top) > 0) top = r;
    const winners = [...readings].filter(([, r]) => cmpRank(r, top) === 0)
      .map(([n]) => n).sort((a, b) => a - b);
    if (winners.length > 1) {
      throw new NumberWordsError(`${JSON.stringify(text)} is ambiguous: matches ${winners}`);
    }
    const n = winners[0], [low, high] = SUPPORTS;
    if (!(low <= n && n <= high)) {
      throw new NumberWordsError(`${JSON.stringify(text)} reads as ${n}, outside the supported range [${low}, ${high}]`);
    }
    return n;
  }

  return { numberToText, textToNumber, tokenize, normalizeWord };
}
