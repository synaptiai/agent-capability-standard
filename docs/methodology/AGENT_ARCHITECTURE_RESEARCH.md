# Agent Architecture Research: Foundation Alternatives

**Document Status**: Historical (Informative)
**Last Updated**: 2026-01-26
**Purpose**: Evaluate alternative foundations for agent capability ontology

> **⚠️ Historical Document**: This document captures research that informed the final 35-capability model. The capability counts and proposals here reflect exploration of alternatives. For the authoritative ontology, see [`schemas/capability_ontology.json`](../../schemas/capability_ontology.json) and [`FIRST_PRINCIPLES_REASSESSMENT.md`](FIRST_PRINCIPLES_REASSESSMENT.md).

---

## Executive Summary

This document synthesizes research on how real-world agent systems organize their capabilities, examining whether explicit capabilities or parameterized primitives better align with agent infrastructure.

**Key Findings:**

| Aspect | Industry Trend | Implication for Grounded Agency |
|--------|----------------|--------------------------------|
| **Capability Organization** | Tool-based, not verb-based | DIS verbs may be too abstract |
| **Granularity** | Fine-grained primitives | Smaller atomic set is better |
| **Extensibility** | Plugin/MCP model | Parameters + extensions |
| **Foundation** | ReAct loop, not cognitive architecture | Simpler foundation may suffice |

**Recommendation**: Adopt a **Tool-Primitive Foundation** rather than DIS verbs, with explicit capabilities for common patterns and parameterization for domains.

---

## 1. How Real Agent Systems Organize Capabilities

### 1.1 LangChain / LangGraph

**Architecture**: Graph-based with nodes as actions, edges as transitions.

**Capability Organization**:
- **Tools** are explicit, named functions (not parameterized verbs)
- Each tool has: `name`, `description`, `function signature`
- Tools are grouped into **toolkits** by domain (code, web, data)

**Key Insight**: LangChain doesn't use abstract verbs like "detect" or "identify." Instead, it exposes concrete tools like `search_web`, `run_python`, `query_database`.

```
LangChain Approach:
├── search_web()        ← explicit tool
├── run_python()        ← explicit tool
├── query_database()    ← explicit tool
└── NOT: detect(domain: web|python|database)
```

**Source**: [LangChain Agents Guide 2025](https://www.leanware.co/insights/langchain-agents-complete-guide-in-2025)

### 1.2 AutoGPT

**Architecture**: Block-based with single-action blocks.

**Capability Organization**:
- **Blocks** are explicit actions (not abstract verbs)
- Each block performs **one action**
- Blocks connect to form workflows

**Key Insight**: AutoGPT's "you build your agent by connecting blocks, where each block performs a single action" aligns with explicit capabilities, not parameterized verbs.

**Source**: [AutoGPT Architecture](https://agpt.co/blog/introducing-the-autogpt-platform)

### 1.3 CrewAI

**Architecture**: Role-based agents with explicit tool assignment.

**Capability Organization**:
- **Tools** are skills/functions (80+ in crewai-tools)
- Agents are configured with specific tools at creation
- Tools can be overridden per task

**Key Insight**: CrewAI exports 80+ tools across categories—not 8 verbs with parameters. Explicit tools are how agents actually work.

**Source**: [CrewAI Tools Documentation](https://docs.crewai.com/en/concepts/tools)

### 1.4 OpenAI Agents SDK

**Architecture**: Agent loop with tool calling.

**Capability Organization**:
- **Function tools**: Any Python function becomes a tool
- **Hosted tools**: OpenAI-provided capabilities
- **Agents as tools**: Hierarchical composition

**Key Insight**: OpenAI's SDK emphasizes "few enough primitives to make it quick to learn." The primitives are:
- Models
- Tools (explicit, typed)
- State/Memory
- Orchestration

**Source**: [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)

### 1.5 Model Context Protocol (MCP)

**Architecture**: Standardized protocol for tool integration.

**Capability Organization**:
- **Tools** are explicit, discoverable endpoints
- Tools have `name`, `description`, `inputSchema`
- No verb-based abstraction layer

**MCP Tool Structure**:
```json
{
  "name": "read_file",
  "description": "Read contents of a file",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {"type": "string"}
    }
  }
}
```

**Key Insight**: MCP—now adopted by OpenAI, Google, and the Linux Foundation—uses explicit tool names, not parameterized verbs. This is becoming the industry standard.

**Source**: [MCP Specification](https://modelcontextprotocol.io/specification/2025-11-25)

---

## 2. Cognitive Architecture Alternatives

### 2.1 BDI (Belief-Desire-Intention)

**Core Primitives**:
- **Beliefs**: Agent's knowledge about the world
- **Desires**: Goals the agent wants to achieve
- **Intentions**: Committed plans being executed
- **Plans**: Sequences of actions

**Operations**:
- Update beliefs
- Generate desires
- Filter desires → intentions
- Execute plans

**Mapping to Grounded Agency**:

| BDI Concept | Grounded Agency Equivalent |
|-------------|---------------------------|
| Belief base | `world-state`, `persist` |
| Belief update | `detect`, `identify`, `estimate` |
| Desire generation | (implicit in workflow goals) |
| Deliberation | `compare`, `plan` |
| Intention execution | `act-plan` |

**Assessment**: BDI is too abstract for practical capability definition. It describes *what agents are* (beliefs, desires, intentions), not *what agents do* (detect, act, verify).

**Source**: [BDI Wikipedia](https://en.wikipedia.org/wiki/Belief%E2%80%93desire%E2%80%93intention_software_model)

### 2.2 SOAR (State, Operator, And Result)

**Core Primitives**:
- **State**: Current problem-solving situation
- **Operator**: Transforms state
- **Impasse**: When knowledge is insufficient
- **Subgoal**: Created to resolve impasse

**Problem-Solving Functions**:
1. Elaborate state
2. Propose candidate operators
3. Compare candidates
4. Apply selected operator

**Mapping to Grounded Agency**:

| SOAR Concept | Grounded Agency Equivalent |
|--------------|---------------------------|
| State | `world-state` |
| Operator proposal | `discover`, `generate` |
| Operator comparison | `compare` |
| Operator application | `act`, `transform` |
| Impasse handling | `decompose` |

**Assessment**: SOAR provides a useful framing but is too abstract. The "operator" concept is closer to our "capability" but SOAR doesn't enumerate what operators exist—they're problem-specific.

**Source**: [SOAR Architecture](https://soar.eecs.umich.edu/soar_manual/02_TheSoarArchitecture/)

### 2.3 ReAct (Reasoning and Acting)

**Core Primitives** (only 3!):
- **Thought**: Reasoning trace
- **Action**: Tool invocation
- **Observation**: Result processing

**The Loop**:
```
Thought → Action → Observation → Thought → ...
```

**Assessment**: ReAct is the dominant practical pattern. It's simpler than BDI/SOAR and directly maps to how LLM agents work. However, it doesn't specify *what* actions are available—that's left to the tool inventory.

**Source**: [ReAct Paper](https://arxiv.org/abs/2210.03629), [IBM ReAct Guide](https://www.ibm.com/think/topics/react-agent)

---

## 3. The Core Question: Explicit vs Parameterized

### 3.1 Arguments for Explicit Capabilities

| Argument | Evidence |
|----------|----------|
| **Industry practice** | LangChain, AutoGPT, CrewAI, MCP all use explicit tools |
| **Discoverability** | Users can see available capabilities |
| **Type safety** | Each capability has specific I/O contracts |
| **Documentation** | Easier to document explicit capabilities |
| **Tooling** | IDEs can autocomplete explicit names |

**Example**: `search_web()` is clearer than `retrieve(domain: web, method: search)`

### 3.2 Arguments for Parameterized Verbs

| Argument | Evidence |
|----------|----------|
| **Smaller core** | 8 verbs vs 99 capabilities |
| **No capability explosion** | New domains add parameters, not capabilities |
| **Semantic clarity** | All "detect" operations share semantics |
| **Composability** | Parameters can be computed/dynamic |

**Example**: `detect(domain: entity)` makes clear it shares semantics with `detect(domain: person)`

### 3.3 What Agents Actually Do

Looking at how agents use capabilities in practice:

**ReAct Agent Typical Actions**:
```
1. search(query)       ← explicit
2. read_file(path)     ← explicit
3. write_file(path, content) ← explicit
4. run_code(code)      ← explicit
5. ask_user(question)  ← explicit
```

**Not**:
```
1. retrieve(domain: web, method: search)
2. retrieve(domain: file, method: read)
3. persist(domain: file)
4. act(domain: code, method: execute)
5. receive(domain: user, method: question)
```

**Observation**: Agents work with **concrete tools**, not **abstract verbs with parameters**.

### 3.4 The Hybrid Insight

The research suggests a **layered approach**:

```
LAYER 1: Primitives (small, abstract)
├── observe, transform, select, verify, store, send

LAYER 2: Capabilities (explicit, typed)
├── detect-anomaly, estimate-risk, plan, verify, checkpoint
├── These are COMMON patterns worth naming explicitly

LAYER 3: Tools (implementation-specific)
├── search_web, read_file, query_postgres
├── These map to actual integrations
```

**Key Insight**: Our 39 capabilities sit at Layer 2—they're common patterns that deserve names, but they compose from Layer 1 primitives and are implemented by Layer 3 tools.

---

## 4. Foundation Alternatives to DIS '23

### 4.1 About DIS '23

The current ontology cites "DIS '23" (Yildirim et al.) as the foundation for the 8 verbs. However, research shows this paper is actually from **CHI 2023** and focuses on **design ideation for AI-powered UX**, not agent capability taxonomies.

The 8 verbs (detect, identify, estimate, forecast, compare, discover, generate, act) appear to be a synthesis of AI model capabilities, not a formal agent architecture framework.

**Source**: [Yildirim et al. CHI 2023](https://dl.acm.org/doi/10.1145/3544548.3580652)

### 4.2 Alternative Foundation: Tool-Primitive Model

Instead of abstract verbs, define capabilities as **what agents concretely do**:

```
PERCEPTION (How agents acquire information)
├── retrieve      → Pull specific data
├── search        → Query by criteria
├── inspect       → Observe current state
├── receive       → Accept pushed data

ANALYSIS (How agents understand information)
├── detect        → Find patterns/occurrences
├── classify      → Categorize/label
├── measure       → Quantify values
├── predict       → Forecast future states
├── compare       → Evaluate alternatives
├── explain       → Generate reasoning

SYNTHESIS (How agents create new things)
├── plan          → Create action sequences
├── generate      → Produce content
├── transform     → Convert formats

EXECUTION (How agents change the world)
├── act           → Execute changes
├── send          → Transmit externally
├── persist       → Store durably

SAFETY (How agents ensure correctness)
├── verify        → Check conditions
├── checkpoint    → Save state
├── rollback      → Restore state
├── constrain     → Enforce limits
├── audit         → Record provenance

COORDINATION (How agents work together)
├── delegate      → Assign to another agent
├── synchronize   → Achieve agreement
├── invoke        → Execute workflow
```

This gives us **~25 core capabilities** that are:
- Concrete (what agents actually do)
- Composable (can build complex behaviors)
- Aligned with MCP/tool patterns

### 4.3 Alternative Foundation: ReAct-Aligned Model

Align capabilities with the dominant ReAct pattern:

```
REASONING CAPABILITIES (support Thought)
├── analyze       → Understand situation
├── plan          → Create action sequence
├── evaluate      → Assess options
├── explain       → Justify reasoning

ACTION CAPABILITIES (support Action)
├── retrieve      → Get information
├── search        → Find information
├── generate      → Create content
├── execute       → Run code/actions
├── send          → Transmit data
├── persist       → Store data

OBSERVATION CAPABILITIES (support Observation)
├── inspect       → Examine results
├── verify        → Check conditions
├── compare       → Evaluate against expectations
├── detect        → Find patterns in results

SAFETY CAPABILITIES (cross-cutting)
├── checkpoint, rollback, audit, constrain
```

### 4.4 Alternative Foundation: MCP-Native Model

Align with the emerging MCP standard:

```
MCP PRIMITIVES
├── tools/list    → Discover capabilities
├── tools/call    → Execute capability
├── resources/list → Discover data
├── resources/read → Access data
├── prompts/list  → Discover templates
├── prompts/get   → Get template

GROUNDED AGENCY MAPS TO:
├── PERCEPTION    → resources/* operations
├── ACTION        → tools/call operations
├── MEMORY        → persistence tools
├── COORDINATION  → agent handoff tools
```

---

## 5. Recommendation

### 5.1 Proposed Foundation: Pragmatic Tool-Primitive

Based on this research, we recommend:

**Foundation**: Neither pure DIS verbs nor pure MCP tools, but a **pragmatic middle ground**:

1. **Small Primitive Core** (~10): Abstract operations that everything else composes from
2. **Explicit Common Capabilities** (~25-30): Named patterns that agents frequently use
3. **Domain as Context, Not Parameter**: Domains are documentation/examples, not formal parameters

### 5.2 The Recommended 30 Capabilities

```
PERCEPTION (4)
├── retrieve    → Pull specific known data
├── search      → Query by criteria
├── inspect     → Observe current state
├── receive     → Accept pushed data

UNDERSTANDING (6)
├── detect      → Find patterns/occurrences
├── classify    → Categorize/label (was: identify)
├── measure     → Quantify values (was: estimate)
├── predict     → Forecast future (was: forecast)
├── compare     → Evaluate alternatives
├── discover    → Find unknown patterns

REASONING (4)
├── plan        → Create action sequence
├── decompose   → Break into subproblems
├── critique    → Identify weaknesses
├── explain     → Justify conclusions

WORLD MODELING (6)
├── world-state       → Create state snapshot
├── state-transition  → Define dynamics
├── causal-model      → Cause-effect relationships
├── ground            → Anchor to evidence (was: grounding)
├── resolve-identity  → Deduplicate entities
├── simulate          → Run what-if scenarios

SYNTHESIS (3)
├── generate    → Produce content
├── transform   → Convert formats
├── integrate   → Merge sources

EXECUTION (2)
├── act         → Execute changes
├── send        → Transmit externally

SAFETY (5)
├── verify      → Check conditions
├── checkpoint  → Save state
├── rollback    → Restore state
├── constrain   → Enforce limits
├── audit       → Record provenance

MEMORY (2)
├── persist     → Store durably
├── recall      → Retrieve stored

COORDINATION (3)
├── delegate    → Assign to agent
├── synchronize → Achieve agreement
├── invoke      → Execute workflow

TOTAL: 35 capabilities
```

### 5.3 Key Differences from Current Proposal

| Aspect | 39-Capability Proposal | 35-Capability Recommendation |
|--------|------------------------|------------------------------|
| Foundation | DIS '23 verbs | Tool-primitive alignment |
| `identify` | Keep (DIS verb) | Rename to `classify` (clearer) |
| `estimate` | Keep (DIS verb) | Rename to `measure` (clearer) |
| `forecast` | Keep (DIS verb) | Rename to `predict` (standard) |
| `grounding` | Keep | Rename to `ground` (verb form) |
| `identity-resolution` | Keep | Rename to `resolve-identity` (verb-first) |
| `model-schema` | Keep | Remove (tool-specific) |
| `detect-anomaly` | Keep (specialization) | Remove (use detect + context) |
| `estimate-risk` | Keep (specialization) | Remove (use measure + context) |
| `act-plan` | Keep (specialization) | Remove (use act with plan input) |

### 5.4 Why This Works Better

1. **Simpler names**: `classify` > `identify`, `measure` > `estimate`
2. **Verb-first**: `resolve-identity` > `identity-resolution`
3. **No special cases**: No `detect-anomaly`, `estimate-risk` exceptions
4. **Tool-aligned**: Names match how MCP/LangChain tools are named
5. **Still atomic**: Each capability does one thing

---

## 6. Validation Against Industry Patterns

### 6.1 LangChain Mapping

| Our Capability | LangChain Tool Equivalent |
|----------------|--------------------------|
| retrieve | `document_loader`, `retriever` |
| search | `search_tool`, `web_search` |
| generate | `llm_chain`, `text_generator` |
| execute (act) | `agent_executor` |
| persist | `vector_store.add` |
| recall | `vector_store.similarity_search` |

### 6.2 MCP Mapping

| Our Capability | MCP Pattern |
|----------------|-------------|
| retrieve | `resources/read` |
| search | `tools/call` with search tool |
| inspect | `resources/list` |
| all others | `tools/call` with appropriate tool |

### 6.3 ReAct Mapping

| ReAct Phase | Our Capabilities |
|-------------|------------------|
| Thought | compare, plan, critique, explain |
| Action | retrieve, search, generate, act, send |
| Observation | inspect, detect, verify, compare |

---

## 7. Conclusion

### Key Takeaways

1. **Industry uses explicit tools, not parameterized verbs**: LangChain, AutoGPT, CrewAI, MCP all expose concrete, named tools.

2. **Cognitive architectures are too abstract**: BDI and SOAR describe what agents *are*, not what they *do*. They don't provide capability inventories.

3. **ReAct is the dominant pattern**: Thought → Action → Observation is how LLM agents work. Capabilities should align with this.

4. **DIS '23 is not a standard**: The 8 verbs are a useful synthesis but not an industry standard. We can adapt them.

5. **The right count is ~30-35**: Not 99 (too many, redundant), not 8 (too abstract), not 39 (close but some naming issues).

### Recommendation

Adopt the **35-capability model** with:
- Tool-aligned naming (verbs first, clear meanings)
- No special-case specializations
- Domain as context/examples, not formal parameters
- Alignment with MCP and ReAct patterns

This creates an ontology that is:
- **Grounded** in how agents actually work
- **Practical** for implementation
- **Defensible** based on industry patterns
- **Extensible** through tool composition

---

## References

### Primary Sources

- [LangChain State of Agent Engineering](https://www.langchain.com/state-of-agent-engineering)
- [LangChain Agents Guide 2025](https://www.leanware.co/insights/langchain-agents-complete-guide-in-2025)
- [AutoGPT Platform Introduction](https://agpt.co/blog/introducing-the-autogpt-platform)
- [AutoGPT Architecture Breakdown](https://medium.com/@georgesung/ai-agents-autogpt-architecture-breakdown-ba37d60db944)
- [CrewAI Tools Documentation](https://docs.crewai.com/en/concepts/tools)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [MCP Specification](https://modelcontextprotocol.io/specification/2025-11-25)
- [MCP Tools Concept](https://modelcontextprotocol.info/docs/concepts/tools/)

### Cognitive Architecture Sources

- [BDI Architecture Wikipedia](https://en.wikipedia.org/wiki/Belief%E2%80%93desire%E2%80%93intention_software_model)
- [BDI Agents: Theory to Practice (Rao & Georgeff)](https://cdn.aaai.org/ICMAS/1995/ICMAS95-042.pdf)
- [SOAR Architecture Manual](https://soar.eecs.umich.edu/soar_manual/02_TheSoarArchitecture/)
- [SOAR Wikipedia](https://en.wikipedia.org/wiki/Soar_(cognitive_architecture))
- [ReAct Paper (Yao et al.)](https://arxiv.org/abs/2210.03629)
- [IBM ReAct Agent Guide](https://www.ibm.com/think/topics/react-agent)

### Agent Taxonomy Sources

- [AI Agents vs Agentic AI Taxonomy](https://arxiv.org/html/2505.10468v1)
- [Artificial Intelligence Ontology (AIO)](https://journals.sagepub.com/doi/10.1177/15705838241304103)
- [Yildirim et al. CHI 2023](https://dl.acm.org/doi/10.1145/3544548.3580652)

### Claude/Anthropic Sources

- [Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)
- [Agent-Native Architecture](https://claude-plugins.dev/skills/@EveryInc/compound-engineering-plugin/agent-native-architecture)
