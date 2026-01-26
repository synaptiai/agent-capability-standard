# Alternative Ontology Approaches

**Document Status**: Discussion Document
**Last Updated**: 2026-01-26
**Purpose**: Explore alternative organizational approaches before deciding

---

## The Central Question

> What is the right way to organize agent capabilities?

This document explores multiple valid approaches, each with different trade-offs.

---

## Approach A: First-Principles Atomic (39 Capabilities)

**Philosophy**: Derive the minimal complete set of irreducible operations.

**Structure**:
- 8 DIS verbs as semantic foundation
- Domain specialization via parameters
- Strict atomicity requirement

**Count**: 39 capabilities

**Pros**:
- Intellectually rigorous
- No redundancy
- Defensible derivation
- Smaller, cleaner set

**Cons**:
- May be too abstract for users
- Parameters can be confusing (what domains are valid?)
- Loses discoverability of explicit specializations
- DIS '23 may not be the right foundation

---

## Approach B: Pragmatic Layered (Current 99, Cleaned)

**Philosophy**: Keep the current structure but fix identified problems.

**Structure**:
- 8 layers as primary organization
- Domain specializations as explicit capabilities
- Remove only clear redundancies

**Changes from current**:
- Merge redundant: validate→verify, decide→compare, etc. (~10 removals)
- Demote compositions: mitigate, improve, optimize, digital-twin (~4 removals)
- Keep domain specializations as explicit capabilities

**Count**: ~85 capabilities

**Pros**:
- Minimal disruption
- Explicit capabilities are discoverable
- Users see available options
- Preserves existing documentation/workflows

**Cons**:
- Still some redundancy
- "85" is still arbitrary
- Domain explosion continues if we add more domains

---

## Approach C: Verb × Domain Matrix (Structured Expansion)

**Philosophy**: Systematically define the cross-product of verbs and domains.

**Structure**:
```
       | entity | activity | risk | state | attribute | ...
-------|--------|----------|------|-------|-----------|----
detect |   ✓    |    ✓     |  ✓   |   ✓   |     ✓     |
identify|  ✓    |    ✓     |  ✓   |   ✓   |     ✓     |
estimate|  ✓    |    ✓     |  ✓   |   ✓   |     ✓     |
...    |        |          |      |       |           |
```

**Count**: 8 verbs × N domains + operational additions

**Pros**:
- Systematic and complete
- Clear what's covered and what's not
- Easy to extend (add row or column)

**Cons**:
- Can explode (8 verbs × 10 domains = 80 just for that)
- Many cells may be unused
- Forces artificial completeness

---

## Approach D: User-Goal Oriented (Task Taxonomy)

**Philosophy**: Organize by what users want to accomplish, not operations.

**Structure**:
```
UNDERSTAND THE WORLD
├── observe (inspect, search, receive)
├── analyze (detect, identify, estimate)
├── model (world-state, causal-model, simulation)
└── predict (forecast)

DECIDE WHAT TO DO
├── compare (compare, critique)
├── plan (plan, decompose)
└── choose (decide, prioritize)

CHANGE THE WORLD
├── act (act-plan, transform, send)
├── coordinate (delegate, synchronize)
└── persist (persist, recall)

ENSURE CORRECTNESS
├── verify (verify, validate)
├── protect (checkpoint, rollback, constrain)
└── record (audit, grounding)
```

**Count**: ~25-40 depending on granularity

**Pros**:
- User-centric organization
- Matches mental models
- Clear purpose for each category

**Cons**:
- Subjective categorization
- Same capability might fit multiple goals
- Harder to derive systematically

---

## Approach E: Minimal Core + Extensions

**Philosophy**: Define a small core that must be implemented, with optional extensions.

**Structure**:
```
CORE (must implement): ~15 capabilities
├── detect, identify, estimate, forecast
├── compare, plan
├── act, generate
├── verify, checkpoint, rollback
├── persist, recall
└── audit

EXTENSIONS (optional modules):
├── World Modeling: world-state, state-transition, causal-model, simulation
├── Multi-Agent: delegate, synchronize
├── Advanced Reasoning: decompose, critique, explain
├── Content Generation: generate-text, generate-code, generate-image
```

**Count**: 15 core + extensions

**Pros**:
- Clear minimum viable implementation
- Modular adoption
- Extensions are optional

**Cons**:
- Which is "core"? Subjective
- May fragment implementations
- Extensions could diverge

---

## Approach F: Capability Algebra (Combinatorial)

**Philosophy**: Define primitive operations that compose algebraically.

**Structure**:
```
PRIMITIVES (~10):
├── observe (→ data)
├── transform (data → data')
├── compare (data × data → ordering)
├── select (options → choice)
├── store (data → ref)
├── load (ref → data)
├── send (data → external)
├── receive (external → data)
├── verify (data × criteria → bool)
└── checkpoint/rollback (→ recovery)

COMPOUNDS (defined as compositions):
├── detect = observe + transform(filter)
├── identify = detect + transform(classify)
├── plan = compare + select (iterative)
├── mitigate = plan + act
```

**Count**: ~10 primitives + N compounds

**Pros**:
- Maximum reuse
- True atomic operations
- Algebraic properties (composition, associativity)

**Cons**:
- Too abstract for practical use
- Users don't think in primitives
- Implementation complexity

---

## Comparison Matrix

| Approach | Count | Derivability | Usability | Extensibility | Migration |
|----------|-------|--------------|-----------|---------------|-----------|
| A. First-Principles | 39 | High | Medium | Easy | Breaking |
| B. Pragmatic Layered | ~85 | Medium | High | Medium | Minimal |
| C. Verb × Domain | Variable | High | Medium | Easy | Breaking |
| D. User-Goal | ~30 | Low | High | Medium | Breaking |
| E. Core + Extensions | 15 + ext | Medium | High | Easy | Gradual |
| F. Capability Algebra | ~10 | High | Low | Hard | Breaking |

---

## Key Trade-offs

### 1. Atomicity vs. Usability

**More atomic** (Approaches A, F):
- Fewer capabilities
- No redundancy
- Harder to use (must compose)

**More usable** (Approaches B, D):
- More capabilities
- Some redundancy
- Easier to use (find what you need)

### 2. Systematic vs. Pragmatic

**Systematic** (Approaches A, C):
- Derived from principles
- Complete and consistent
- May include unused capabilities

**Pragmatic** (Approaches B, E):
- Based on actual use cases
- May miss edge cases
- Proven useful

### 3. Fixed vs. Extensible

**Fixed** (Approaches A, F):
- Stable capability set
- Clear boundaries
- Hard to add new ones

**Extensible** (Approaches C, E):
- Easy to add new capabilities
- Risk of unbounded growth
- Versioning complexity

---

## Questions to Resolve

1. **Who is the primary user?**
   - Developers building agents → more atomic is better
   - End users configuring workflows → more usable is better

2. **What is the stability requirement?**
   - Research/exploration → extensible is fine
   - Production standard → fixed is better

3. **How do we handle domain specialization?**
   - Parameters → fewer capabilities, harder discovery
   - Explicit → more capabilities, easier discovery

4. **Is DIS '23 the right foundation?**
   - Yes → Approach A/C
   - No → Need alternative derivation

5. **What about the existing 99?**
   - Breaking change acceptable → any approach
   - Minimize disruption → Approach B

---

## My Assessment

After analysis, I see value in a **hybrid approach**:

### Proposed Hybrid: Layered Core with Parameterized Verbs

```
CORE VERBS (8, parameterized):
├── detect(domain)
├── identify(domain)
├── estimate(target)
├── forecast(target)
├── compare(target)
├── discover(target)
├── generate(modality)
└── act

DISTINCT SPECIALIZATIONS (3, kept explicit):
├── detect-anomaly (semantically distinct)
├── estimate-risk (probability × impact)
└── act-plan (structured execution)

PERCEPTION (4):
├── retrieve, inspect, search, receive

SAFETY (5):
├── verify, checkpoint, rollback, audit, constrain

REASONING (4):
├── plan, decompose, critique, explain

WORLD MODELING (8):
├── world-state, state-transition, causal-model, grounding
├── identity-resolution, simulation, model-schema, integrate

ACTION (2):
├── transform, send

COORDINATION (3):
├── delegate, synchronize, invoke-workflow

MEMORY (2):
├── persist, recall

TOTAL: 39 capabilities
BUT with explicit domain documentation showing valid parameters
```

This gives us:
- **Atomic foundation** (39)
- **Clear documentation** of valid domains/parameters
- **Discoverability** through parameter enums
- **Extensibility** by adding parameter values, not capabilities

---

---

## Approach G: Tool-Aligned (Research-Derived)

**Philosophy**: Align with how agents actually work based on industry research.

**Research Basis**: Analysis of LangChain, AutoGPT, CrewAI, MCP, and ReAct patterns shows that:
- Agents use **explicit, named tools**, not parameterized verbs
- Industry standards (MCP) expose **concrete capabilities**
- The dominant pattern is **Thought → Action → Observation**

**Structure**:
```
PERCEPTION (4): retrieve, search, inspect, receive
UNDERSTANDING (6): detect, classify, measure, predict, compare, discover
REASONING (4): plan, decompose, critique, explain
WORLD_MODELING (6): world-state, state-transition, causal-model, ground, resolve-identity, simulate
SYNTHESIS (3): generate, transform, integrate
EXECUTION (2): act, send
SAFETY (5): verify, checkpoint, rollback, constrain, audit
MEMORY (2): persist, recall
COORDINATION (3): delegate, synchronize, invoke
```

**Count**: 35 capabilities

**Key differences from Approach A (39)**:
- `identify` → `classify` (clearer, industry-standard term)
- `estimate` → `measure` (clearer)
- `forecast` → `predict` (standard)
- `grounding` → `ground` (verb form)
- No special cases (`detect-anomaly`, `estimate-risk`, `act-plan` removed)
- `model-schema` removed (tool-specific)

**Pros**:
- Based on empirical research of agent patterns
- Aligned with MCP and emerging standards
- No exception capabilities (every capability follows same rules)
- Clear, verb-first naming
- Defensibility: HIGH

**Cons**:
- Departs from DIS '23 foundation
- 35 is still somewhat arbitrary (but empirically grounded)

See [AGENT_ARCHITECTURE_RESEARCH.md](AGENT_ARCHITECTURE_RESEARCH.md) for full research.

---

## Updated Comparison Matrix

| Approach | Count | Derivability | Usability | Extensibility | Migration | Industry Alignment |
|----------|-------|--------------|-----------|---------------|-----------|-------------------|
| A. First-Principles | 39 | High | Medium | Easy | Breaking | Medium |
| B. Pragmatic Layered | ~85 | Medium | High | Medium | Minimal | Low |
| C. Verb × Domain | Variable | High | Medium | Easy | Breaking | Low |
| D. User-Goal | ~30 | Low | High | Medium | Breaking | Medium |
| E. Core + Extensions | 15 + ext | Medium | High | Easy | Gradual | Medium |
| F. Capability Algebra | ~10 | High | Low | Hard | Breaking | Low |
| **G. Tool-Aligned** | **35** | **High** | **High** | **Easy** | **Breaking** | **High** |

---

## Research-Informed Assessment

After comprehensive research on agent architectures ([full research](AGENT_ARCHITECTURE_RESEARCH.md)), we found:

### Key Finding 1: Industry Uses Explicit Tools

LangChain, AutoGPT, CrewAI, and MCP all expose **explicit, named tools**—not parameterized verbs:

```
Industry Pattern:
├── search_web()        ← explicit tool
├── read_file()         ← explicit tool
├── query_database()    ← explicit tool

NOT:
├── retrieve(domain: web|file|database)
```

### Key Finding 2: DIS '23 Is Not a Standard

The "DIS '23" foundation (Yildirim et al.) is actually a CHI 2023 paper about design ideation for AI UX—not an agent capability standard. The 8 verbs are a useful synthesis but not industry-recognized.

### Key Finding 3: ReAct Is Dominant

The **Thought → Action → Observation** loop is how modern LLM agents work. Capabilities should align with this pattern.

### Key Finding 4: MCP Is Becoming Standard

Model Context Protocol (MCP), now backed by Anthropic, OpenAI, and the Linux Foundation, uses explicit tool definitions—not verb hierarchies.

---

## Recommended Approach: G (Tool-Aligned)

Based on research, **Approach G (35 capabilities)** is recommended:

1. **Highest defensibility**: Based on empirical patterns, not theoretical framework
2. **Industry-aligned**: Matches MCP, LangChain, ReAct
3. **No exceptions**: Every capability follows the same rules
4. **Clear naming**: Verb-first, common terminology

See [ONTOLOGY_DECISION_MATRIX.md](ONTOLOGY_DECISION_MATRIX.md) for detailed comparison.

---

## What Do You Think?

Before proceeding, consider:

1. Does the 35-capability tool-aligned approach resonate better than the 39-capability DIS-derived approach?
2. Are you comfortable departing from the DIS '23 foundation given the research findings?
3. Do the name changes (identify→classify, estimate→measure, forecast→predict) make sense?
4. Should we validate against more workflows before deciding?
