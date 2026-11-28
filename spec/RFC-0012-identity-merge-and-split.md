# RFC-0012: Identity merge and split checks
**Status:** Draft
**Target:** Standard v1.3.0
**Date:** 2026-11-27
**Tracking issue:** [#150](https://github.com/synaptiai/agent-capability-standard/issues/150)

## Summary

This RFC proposes, for Standard 1.3.0, that §7.3 (merge and split rules)
state its three constraints as checks with defined inputs and outcomes, and
that §7.2 (alias confidence scoring) become informative. Under the proposed
§7.3 a merge is refused when its records are of different classes of the
entity taxonomy or give a unique attribute different values; a split is
refused when it keeps the split record's id or changes its class; and an
allowed merge or split gives a lineage record that the host keeps as an
action record of the world state. The checks are deterministic, and the
vectors `tests/conformance/entities/merge.json` fix them.

§7.2 keeps its feature table as guidance, and points at
`schemas/identity_resolution_policy.yaml` as a default heuristic, not a
requirement.

The RFC is a Draft. Standard 1.2.0 is not changed by it: in 1.2.0, §7.2 and
§7.3 remain as written, and `spec/SECURITY.md` §1.4 states that the merge
constraints are a requirement on a host that merges or splits entities,
which the reference layers do not enforce. The Python package
`grounded_agency` implements the proposed checks (`check_merge`,
`check_split` in `grounded_agency/entities.py`), and `tests/test_entities.py`
runs them against the vectors. No reference layer performs a merge or a
split, so nothing calls them yet.

## Motivation

Standard 1.2.0 §7.2 says "Alias matching MUST use weighted feature scoring"
and gives four features with weight ranges. It does not say how the
weights combine into a score, so no implementation can be tested against
it, and no vector can be written for it. The one artifact §11.7 names for
it, `schemas/identity_resolution_policy.yaml`, lists eight features rather
than four. Their weights sum to 2.1 on a score range of 0 to 1, and its
thresholds (auto merge 0.9, suggest 0.75, no merge 0.6, split review 0.4)
leave a score between 0.4 and 0.6 without an action. This repository
holds no code that computes the score and no evaluation of the weights.
Requiring them would make an untested heuristic a rule of the Standard.

§7.3 lists three hard constraints that "MUST NOT be violated": never merge
entities with conflicting unique identifiers, never merge across
incompatible entity types, always record a merge or split in lineage. None
of the three terms is defined:

- The world state's `attributes` is a free-form object, and nothing says
  which attributes are unique identifiers.
- Nothing says when two entity types are compatible. The policy file allows
  "a subtype alias mapping", while the taxonomy separates aliases (`svc` for
  `service`) from subtypes (`api`, `worker`).
- `meta.lineage` in `schemas/world_state_schema.yaml` is the list of
  ancestor snapshot versions, not a record of what was merged.

The policy file's own three hard constraints differ from §7.3's. They add a
rule on organisation namespaces, and they speak of "high-signal
attributes" (ip, url, serial, employee_id) rather than unique identifiers.

`spec/SECURITY.md` §1.4 presents the merge constraints as a core safety
invariant. They are the only rule in the Standard against conflating two
entities, which corrupts every later claim about either one. They can be
checked deterministically from the records and the taxonomy. This RFC gives
them the definitions that make the check possible, and leaves the scoring,
which cannot be checked, as guidance.

## Goals

- Define the class of an entity record, and when two records' classes are
  compatible, in terms of `schemas/entity_taxonomy.yaml`.
- Define a unique identifier and a conflict between two records' values.
- Define what a split may and may not produce.
- Define the lineage record of a merge or split in types the world state
  already has.
- Give each refusal a reason token and fix the order in which the
  constraints are checked, so two implementations refuse a merge for the
  same reason.
- Publish vectors for every constraint, and a reference implementation that
  passes them.
- Make §7.2 informative, and state what the policy file's weights and
  thresholds are.

## Non-goals

- A scoring arithmetic for alias confidence. §7.2 becomes guidance; a host
  chooses its own scoring and thresholds.
- Deciding whether two records denote the same entity. The checks say only
  whether a merge or split that a host or a person proposes violates a
  constraint.
- Performing a merge: combining attributes and aliases, rewiring
  relationships. The policy file's merge and split strategies stay
  guidance.
- A diagnostic code of §9. No executor or safety layer merges entities, so
  the checks report reason tokens, as §5.19.7 does.
- The TypeScript package. RFC-0010's open question 5 asks whether it should
  carry entity ids and the trust arithmetic; the same answer applies here.
- Any change to Standard 1.2.0.

## Key decisions

### 1) §7.3 becomes checks with defined inputs and outcomes

The proposed text of §7.3 for Standard 1.3.0:

> **7.3 Merge and Split Rules**
>
> A *merge* combines two or more entity records into one; a *split* divides
> one entity record into two or more. A record is a world-state `Entity`:
> an `id` (§7.1), a `type` and `attributes`.
>
> The *class* of a record is the class its `type` denotes: the class itself
> for a class name of `entity_taxonomy.yaml`, the class an alias belongs to
> for an alias (`svc` denotes `service`, `node` denotes `host`), and the
> type itself for a vendor class (`x-` …). A subtype of the taxonomy
> (`employee`, `api`) is not a class, and a record whose `type` is neither
> a class, an alias nor a vendor class is invalid (`unknown_class`). An id
> whose class part is neither a class, an alias nor a vendor class is not an
> id of §7.1 (`invalid_entity_id`). The class part of the record's id MUST
> denote the same class as its `type` (`class_mismatch`). Two records are of compatible types exactly when they
> are of the same class.
>
> A *unique attribute* is an attribute key whose value identifies an entity
> by itself, such as a serial number or an employee number. The host
> supplies the list of unique attributes; `identity_resolution_policy.yaml`
> gives a default (`merge_rules.unique_attributes`). Two records *conflict*
> on a unique attribute when both give it a value and the values differ. A
> missing value or `null` conflicts with none. Values are compared as JSON
> values: numbers by value, strings exactly, and a boolean is not a number.
> A host that means `SN-12` and `sn-12` to match normalises them before the
> check.
>
> A host that merges entity records MUST refuse the merge when:
> - fewer than two records are merged (`too_few_entities`);
> - a record is not an entity record (`invalid_entity`), its id is not an id
>   of §7.1 (`invalid_entity_id`), or its class is invalid as above;
> - two records have the same id (`duplicate_id`);
> - the records are not all of one class (`incompatible_types`);
> - two records conflict on a unique attribute (`conflicting_identifier`);
> - the merged record's id is not an id of §7.1 (`invalid_entity_id`) or
>   does not denote the records' class (`class_mismatch`).
>   It is one of the merged ids or a new one.
>
> A host that splits an entity record MUST refuse the split when:
> - the record split is invalid as above;
> - it gives fewer than two records (`too_few_entities`);
> - a record it gives is invalid as above;
> - two records it gives have the same id (`duplicate_id`);
> - a record it gives keeps the split record's id (`reused_id`);
> - a record it gives is not of the split record's class
>   (`incompatible_types`).
>
> A split has no unique-attribute constraint: it separates records that a
> unique attribute tells apart.
>
> The constraints are checked in the order listed, and a refusal gives the
> token of the first one violated. The merge and split vectors (§10.3) fix
> them.

The order matters only when one operation violates two constraints, as in
the vector `type_before_identifier`. The class constraint is listed first
because it needs no host input.

### 2) Unique attributes are a host input with a default in the policy

The Standard cannot know which attributes of a deployment's entities are
unique. A serial number is unique for assets, and an employee number for
people, but an IP address or a URL is reassigned and shared. The check
therefore takes the list as an input.

On acceptance, `schemas/identity_resolution_policy.yaml` 1.1.0 gains
`merge_rules.unique_attributes: [serial, employee_id]` as the default. The
policy's `ip` and `url` stay scoring features of `attribute_value_match`:
two records with different IP addresses can be one host that moved.

### 3) The lineage record is an action record

An allowed merge or split gives a lineage record with four members:

| Member | Holds |
|--------|-------|
| `operation` | `merge` or `split` |
| `class` | The class of every record involved |
| `from` | The ids merged, or the id split, in the order given |
| `into` | The id of the merged record, or the ids of the records the split gives, in the order given |

The proposed §7.3 continues:

> A host that merges or splits entity records MUST append an
> `ActionRecord` to the world state's `actions` whose
> `details.identity_change` is the lineage record of the operation, and
> whose `anchors` cite the evidence the operation rests on. After a merge,
> the merged record SHOULD list the other merged ids in its `aliases`.

The record uses fields the world state already has (`ActionRecord.details`
and `anchors`), so `schemas/world_state_schema.yaml` needs no new type.
`meta.lineage` keeps its meaning: the snapshot versions a world state
derives from.

### 4) §7.2 becomes informative

The proposed text of §7.2 for Standard 1.3.0:

> **7.2 Alias Confidence Scoring (informative)**
>
> A host that proposes merges usually scores how likely two records are to
> denote one entity, from features such as these:
>
> | Feature | Description |
> |---------|-------------|
> | Exact match | Identical identifiers |
> | Fuzzy match | Similar but not identical |
> | Cross-reference | Linked by another source |
> | Temporal proximity | Close in time |
>
> `identity_resolution_policy.yaml` gives one heuristic: eight features
> with weights and four thresholds. Its weights are not normalised: they
> sum to 2.1, so the policy alone does not give a score from 0 to 1, and a
> host that uses it chooses how to combine them. Its thresholds leave
> scores from 0.4 to 0.6 without an action. A host chooses its own
> features, weights and thresholds. Whatever score proposes a merge, the
> merge is subject to §7.3.

On acceptance, the policy file 1.1.0 gains `status: informative` beside its
scoring section, and a comment saying that the weights are not normalised
and that the band from 0.4 to 0.6 has no action.
`tools/validate_canonical_schemas.py` then checks the shape of
`merge_rules.unique_attributes` (a list of distinct strings).

### 5) The policy's own hard constraints

The policy's three hard constraints map to the proposed §7.3 as follows:

| Policy constraint | Proposed §7.3 |
|-------------------|---------------|
| Do not merge different entity types unless one is a subtype alias mapping | `incompatible_types`, with aliases mapped to their class. A subtype is not a type a record can have. |
| Do not merge different org namespaces unless exact stable identifiers match | Not a constraint. It stays in the policy as guidance; see open question 1. |
| Do not merge if both entities have conflicting high-signal attributes | `conflicting_identifier`, over the unique attributes the host supplies |

### 6) A reference implementation before acceptance

`grounded_agency/entities.py` implements the checks as `check_merge` and
`check_split`, and gives the class map with `class_index`. They are pure
functions over the records, the class map and the unique attributes, and
use the standard library only. They follow §7.1's entity id code in the
same module. The vectors are marked `"status": "proposed"` and name this
RFC. On acceptance they become normative for §7.3 in Standard 1.3.0.

### 7) Changes on acceptance

When this RFC is Accepted, these change with Standard 1.3.0:

- The Standard: §7.2 and §7.3 as quoted above. §10.3 names the merge and
  split vectors as normative for §7.3. §11.7 names policy 1.1.0. The
  changes appendix lists both sections.
- `schemas/identity_resolution_policy.yaml` 1.1.0, and its check in
  `tools/validate_canonical_schemas.py`, as in decisions 2 and 4.
- `tests/conformance/entities/merge.json`: `status` becomes `normative`.
- `spec/SECURITY.md` §1.4 and §2.2.2: the merge constraints are checks of
  the Standard, and the reference implementation that passes their vectors
  is named.
- `docs/GROUNDED_AGENCY.md` §6.3 and §6.4, and the "Identity Resolution"
  entry of `docs/GLOSSARY.md`: the scoring is a default heuristic, and the
  hard constraints are those of §7.3.
- `spec/CONFORMANCE.md`: the merge and split vectors are listed beside the
  entity id vectors.

## Backward compatibility

The RFC changes nothing in Standard 1.2.0. A 1.2.0 host keeps 1.2.0's §7.2
and §7.3.

For Standard 1.3.0, a MINOR version:

- **§7.2.** Removing the MUST loosens the text. No implementation scored
  aliases under 1.2.0, so nothing breaks.
- **§7.3.** The three constraints were already MUST NOT in 1.2.0. The RFC
  defines their terms, and the definitions can go either way for a host
  that read them differently. Mapping aliases to classes allows a merge of
  `svc` and `service` records, which string equality of types refused. A
  `type` that is a subtype or an unknown name is now refused. No reference
  implementation and no host known to the project merges entities, so the
  change affects no known deployment.
- **The lineage record.** 1.2.0 required merges and splits to be recorded
  in lineage without saying where. A host that recorded them another way
  adds the action record. This is a requirement on hosts that merge
  entities, which the RFC treats as the definition of an existing MUST.
- **Unique attributes.** The list is a host input. A host that supplies an
  empty list gets no identifier constraint, which is the behaviour of a
  host that never named a unique identifier under 1.2.0.
- **The policy file.** 1.1.0 only adds members, so a reader of 1.0.0
  ignores them.
- **Entity ids.** §7.1 and its vectors are unchanged. The checks use the
  same parser.

## Conformance test updates

- New: `tests/conformance/entities/merge.json`, with merge vectors and
  split vectors, self-contained like `tests/conformance/entities/ids.json`.
  It lists the taxonomy's class names and aliases with the class each
  denotes, and each merge vector states its unique attributes. Every
  refusal reason has a vector, and so does the order of two violated
  constraints.
- New tests in `tests/test_entities.py`. They run every vector against
  `grounded_agency/entities.py`, and check that the file's class map is the
  taxonomy's and that every reason token is covered.
- On acceptance, §10.3 names the vectors as normative for §7.3, and
  `status` becomes `normative`.
- None for §7.2, which states no requirement.

## Alternatives considered

- **Make both sections informative.** This is the cheapest option and
  matches RFC-0010's non-goal. It removes the only rule in the Standard
  against an unsafe merge, which `spec/SECURITY.md` presents as a safety
  invariant. Rejected for §7.3, taken for §7.2.
- **Make both normative.** This needs a scoring arithmetic: a weighted sum
  divided by the sum of the weights, in decimal, with an action for every
  band of scores. It would also need the Standard's four features
  reconciled with the policy's eight. Every number in it would be a
  heuristic with no evaluation behind it. Rejected.
- **Fixed unique attributes in the Standard.** A list such as serial and
  employee number cannot fit every domain, and the policy's ip and url
  would refuse legitimate merges of a host that moved. Rejected in favour of
  a host input with a default.
- **Subtype compatibility.** The policy speaks of "a subtype alias
  mapping". The taxonomy's subtypes (`api`, `worker`) are kinds within a
  class, not values a record's `type` takes (§7.1 says the type is a class
  or an alias), so they cannot make two records' types compatible. Rejected.
- **A new lineage type in the world-state schema.** A dedicated
  `IdentityChange` type would be clearer to read, but it changes a
  canonical schema for a record that `ActionRecord.details` already holds.
  Rejected for this version; see open question 4.
- **Amend Standard 1.2.0.** The maintainer's decision places identity
  resolution in 1.3.0, so that 1.2.0's release does not wait on it. 1.2.0
  instead labels the constraints a host requirement.

## Open questions

1. Should the policy's organisation-namespace rule (no merge across
   organisation namespaces unless stable identifiers match) become a
   constraint, and how would the check know which namespace segment names
   the organisation, when §7.1 only recommends the order of the segments?
2. Should a refused merge have a diagnostic code of §9, for an executor
   that one day performs merges as steps?
3. Should a check take the world state after the operation, so that it can
   also verify that the merged ids are in the merged record's `aliases` and
   that the split record no longer appears?
4. Should the lineage record become its own type in the world-state schema,
   rather than a member of `ActionRecord.details`?
5. Should the vectors cover the normalisation of identifier values (case,
   white space, Unicode forms), or does that stay the host's?
