// The generated Draft 2020-12 rendering of the contracts (Standard 1.2.0
// section 4.1.2) compiles under a strict JSON Schema validator, with
// x-acs-type known as an annotation.
import { describe, expect, it } from 'vitest';
import Ajv2020 from 'ajv/dist/2020.js';
import doc from '../../../schemas/generated/capability_contracts.schema.json' with { type: 'json' };

describe('the strict rendering of the contracts', () => {
  it('compiles every $defs entry under ajv strict mode', () => {
    // Type lists are the rendering of the dialect's unions (section 4.1.2).
    // `format` is an annotation in Draft 2020-12 (format-annotation vocabulary).
    const ajv = new Ajv2020({ strict: true, allErrors: true, allowUnionTypes: true, validateFormats: false });
    ajv.addKeyword({ keyword: 'x-acs-type', schemaType: 'string' });
    ajv.addSchema(doc as object);
    const defs = Object.keys((doc as { $defs: Record<string, unknown> }).$defs);
    expect(defs.length).toBe(72);
    for (const name of defs) {
      const ref = `${(doc as { $id: string }).$id}#/$defs/${encodeURIComponent(name)}`;
      expect(ajv.getSchema(ref), name).toBeTypeOf('function');
    }
  });
});
