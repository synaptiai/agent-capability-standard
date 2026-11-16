/**
 * Model families (STANDARD v1.2.0 §5.15): the lowercase name of a
 * provider's line of models, compared by exact (code-point) equality, and
 * derived from a model identifier by one rule
 * (`tests/conformance/families/derive.json` pins it).
 */

const FAMILY = /^[a-z][a-z0-9_-]*$/;

/** Whether `value` is written as a model family: `[a-z][a-z0-9_-]*`. */
export function isModelFamily(value: string): boolean {
  return FAMILY.test(value);
}

/**
 * The model family a host derives from a model identifier: (1) the part
 * after its last `/`; (2) of that, the part after the last `.` or `:` that
 * is followed by an ASCII letter and comes before its first ASCII digit or
 * `-`; when it has neither, after the last `.` followed by a letter (a `:`
 * there starts a tag, as in `acme:latest`); (3) the leading run of ASCII
 * letters of the rest, lowercased. `null` when that run is empty: the host
 * attests no family.
 */
export function modelFamily(modelId: string): string | null {
  let rest = modelId.slice(modelId.lastIndexOf('/') + 1);
  const stop = rest.search(/[0-9-]/);
  const head = stop < 0 ? rest : rest.slice(0, stop);
  const separators = stop < 0 ? '.' : '.:';
  for (let cut = head.length - 1; cut >= 0; cut--) {
    if (separators.includes(head[cut]!) && /^[A-Za-z]/.test(rest.slice(cut + 1, cut + 2))) {
      rest = rest.slice(cut + 1);
      break;
    }
  }
  const letters = /^[A-Za-z]*/.exec(rest)?.[0] ?? '';
  return letters === '' ? null : letters.toLowerCase();
}
