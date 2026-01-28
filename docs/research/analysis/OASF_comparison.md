# OASF vs Grounded Agency Capability Ontology: Comprehensive Comparison

**Date:** 2026-01-28
**OASF Version:** 0.8.0
**Grounded Agency Version:** 2.0.0

## Executive Summary

This document provides a comprehensive comparison between the **Open Agentic Schema Framework (OASF)** by Cisco/Outshift and our **Grounded Agency Capability Ontology**. While both frameworks aim to standardize AI agent capabilities, they take fundamentally different approaches:

| Aspect | OASF | Grounded Agency |
|--------|------|-----------------|
| **Philosophy** | Task/skill taxonomy | Cognitive architecture |
| **Organization** | 15 skill categories | 9 cognitive layers |
| **Granularity** | ~100+ specific skills | 36 atomic capabilities |
| **Focus** | What agents can do | How agents reason safely |
| **Safety Model** | Category-level (Security & Privacy) | Built into every capability |
| **Composability** | Implicit | Explicit typed contracts |

---

## 1. Framework Overview

### 1.1 OASF (Open Agentic Schema Framework)

OASF provides a structured taxonomy of AI agent skills organized into **15 primary categories**:

1. Natural Language Processing
2. Images/Computer Vision
3. Audio
4. Tabular/Text
5. Analytical Skills
6. Retrieval Augmented Generation
7. Multi-modal
8. Security & Privacy
9. Data Engineering
10. Agent Orchestration
11. Evaluation & Monitoring
12. DevOps/MLOps
13. Governance & Compliance
14. Tool Interaction
15. Advanced Reasoning & Planning

Each category contains 2-11 subcategories with hierarchical numerical coding (e.g., 10101 for a specific skill under category 101).

### 1.2 Grounded Agency Capability Ontology

Our ontology defines **36 atomic capabilities** across **9 cognitive layers**, derived from first principles analysis of BDI cognitive architecture, ReAct agent patterns, Claude Skills, and MCP tool patterns:

| Layer | Purpose | Capabilities |
|-------|---------|--------------|
| PERCEIVE | Information acquisition | retrieve, search, observe, receive |
| UNDERSTAND | Making sense of information | detect, classify, measure, predict, compare, discover |
| REASON | Planning and analysis | plan, decompose, critique, explain |
| MODEL | World representation | state, transition, attribute, ground, simulate |
| SYNTHESIZE | Content creation | generate, transform, integrate |
| EXECUTE | Changing the world | execute, mutate, send |
| VERIFY | Correctness assurance | verify, checkpoint, rollback, constrain, audit |
| REMEMBER | State persistence | persist, recall |
| COORDINATE | Multi-agent interaction | delegate, synchronize, invoke, inquire |

---

## 2. Detailed Capability Mapping

### 2.1 OASF Skills That Map to Our Atomic Capabilities

The following OASF skills align with our atomic capabilities and could be represented using domain parameters:

| OASF Skill | OASF Category | Grounded Agency Equivalent | Notes |
|------------|---------------|---------------------------|-------|
| Information Retrieval | RAG [6] | `retrieve` | Direct mapping |
| Document Search | RAG [6] | `search` | Direct mapping |
| Named Entity Recognition | NLP [111] | `detect` with `domain: entity` | Domain parameterization |
| Topic Classification | NLP [109] | `classify` | Direct mapping |
| Sentiment Analysis | NLP [109] | `classify` with `domain: sentiment` | Domain parameterization |
| Quality Assessment | Data Eng [9] | `measure` with `domain: quality` | Domain parameterization |
| Risk Classification | Governance [13] | `measure` with `domain: risk` | Domain parameterization |
| Anomaly Detection | Evaluation [11] | `detect` with `domain: anomaly` | Domain parameterization |
| Threat Detection | Security [8] | `detect` with `domain: threat` | Domain parameterization |
| Text Summarization | NLP [102] | `explain` or `transform` | Context-dependent |
| Text Generation | NLP [102] | `generate` | Direct mapping |
| Translation | NLP [105] | `transform` with `domain: language` | Domain parameterization |
| Code Generation | Analytical [5] | `generate` with `domain: code` | Domain parameterization |
| Task Decomposition | Orchestration [10] | `decompose` | Direct mapping |
| Multi-agent Planning | Orchestration [10] | `plan` + `delegate` | Composition |
| Policy Mapping | Governance [13] | `constrain` | Direct mapping |
| Compliance Assessment | Governance [13] | `verify` with `domain: compliance` | Domain parameterization |
| Audit Summarization | Governance [13] | `audit` + `explain` | Composition |
| Performance Monitoring | Evaluation [11] | `observe` + `measure` | Composition |
| Benchmark Execution | Evaluation [11] | `execute` + `verify` | Composition |
| Schema Inference | Data Eng [9] | `discover` with `domain: schema` | Domain parameterization |
| Data Transformation | Data Eng [9] | `transform` | Direct mapping |
| Feature Engineering | Data Eng [9] | `transform` + `generate` | Composition |
| Workflow Automation | Tool [14] | `invoke` | Maps to workflow invocation |
| API Schema Understanding | Tool [14] | `detect` + `classify` | Pattern detection + categorization |

### 2.2 OASF Skills That Would Be Workflow Patterns

These OASF skills are inherently multi-step processes best represented as composed workflows:

| OASF Skill | Proposed Workflow Pattern | Required Capabilities |
|------------|--------------------------|----------------------|
| **Question Answering** | `question_answer` | search → retrieve → ground → generate → explain |
| **Document QA** | `document_qa` | retrieve → detect → classify → ground → generate |
| **Fact Verification** | `fact_verification` | retrieve → ground → verify → explain |
| **Problem Solving** | `problem_solve` | decompose → plan → execute → verify |
| **Hypothesis Generation** | `hypothesis_generation` | observe → discover → predict → critique |
| **Chain-of-Thought Reasoning** | `chain_of_thought` | decompose → explain → verify (iterative) |
| **Long-horizon Planning** | `strategic_planning` | state → predict → plan → simulate → critique |
| **Negotiation/Conflict Resolution** | `negotiation` | inquire → compare → plan → delegate → synchronize |
| **CI/CD Pipeline** | `cicd_workflow` | observe → verify → checkpoint → execute → verify → audit |
| **Model Versioning** | `model_versioning` | checkpoint → mutate → verify → persist → audit |
| **Infrastructure Provisioning** | `infrastructure_provision` | plan → constrain → checkpoint → execute → verify |
| **Vulnerability Assessment** | `vulnerability_assessment` | search → detect → measure → critique → explain |
| **Data Quality Pipeline** | `data_quality` | observe → detect → measure → transform → verify |
| **Test Case Generation** | `test_generation` | observe → critique → generate → verify |

### 2.3 OASF Categories Without Direct Grounded Agency Equivalent

These OASF categories represent **modality-specific capabilities** that our ontology intentionally abstracts away:

| OASF Category | Why No Direct Equivalent | How to Handle |
|---------------|-------------------------|---------------|
| **Computer Vision [2]** | Modality-specific (image segmentation, object detection) | Domain parameter on `detect`, `classify`, `generate`, `transform` |
| **Audio [3]** | Modality-specific (audio classification, speech synthesis) | Domain parameter on `detect`, `classify`, `generate`, `transform` |
| **Multi-modal [7]** | Cross-modality transformations | `transform` with source/target modality parameters |
| **DevOps/MLOps [12]** | Infrastructure-specific operations | Workflow patterns using `execute`, `verify`, `checkpoint` |

**Key Insight:** Our ontology treats modality (text, image, audio, code) as a **domain parameter**, not a separate capability. This reduces the ontology size while maintaining expressiveness.

---

## 3. Comparative Analysis

### 3.1 Philosophical Differences

| Dimension | OASF | Grounded Agency |
|-----------|------|-----------------|
| **Organizing Principle** | What can agents do? (Skills) | How do agents think? (Cognition) |
| **Taxonomy Basis** | Industry domains and use cases | Cognitive science (BDI architecture) |
| **Granularity Control** | Fine-grained skill listing | Atomic + composable patterns |
| **Safety Integration** | Separate category (Security & Privacy) | Embedded in every capability |

### 3.2 Safety Model Comparison

**OASF Safety Approach:**
- Security & Privacy as a separate skill category [8]
- Threat detection, vulnerability analysis, privacy assessment as distinct skills
- Safety is an optional "add-on" capability

**Grounded Agency Safety Approach:**
- Every capability has `risk`, `mutation`, `requires_checkpoint`, `requires_approval` attributes
- High-risk capabilities (`mutate`, `send`) structurally require checkpoints
- Evidence anchors and confidence required in all output schemas
- `constrain` capability enforces policies pre-execution
- `verify` capability validates post-execution
- Safety is **not optional**—it's built into the capability contracts

### 3.3 Composability Comparison

**OASF Composability:**
- Skills are listed as standalone capabilities
- Composition is implicit (combine skills as needed)
- No formal workflow definition mechanism
- No typed contracts between skills

**Grounded Agency Composability:**
- Explicit edge types define capability relationships:
  - `requires`: Hard dependency
  - `enables`: Unlocks other capabilities
  - `precedes`: Temporal ordering
  - `conflicts_with`: Mutual exclusivity
  - `alternative_to`: Substitutability
  - `specializes`: Inheritance
- Workflow catalog provides reference patterns
- Typed input/output schemas enable formal composition

### 3.4 Evidence and Grounding

**OASF:**
- No explicit grounding mechanism
- No evidence anchor requirements
- No confidence/uncertainty modeling

**Grounded Agency:**
- Every capability output includes `evidence_anchors` and `confidence`
- Dedicated `ground` capability anchors claims to evidence
- `audit` capability provides provenance tracking
- Uncertainty explicitly modeled in `measure` outputs

---

## 4. Gap Analysis

### 4.1 OASF Capabilities Missing from Grounded Agency

| OASF Skill | Analysis | Recommendation |
|------------|----------|----------------|
| **Image Generation** | Modality-specific | Use `generate` with `domain: image` |
| **Video Generation** | Modality-specific | Use `generate` with `domain: video` |
| **Speech Recognition** | Modality-specific | Use `detect` + `transform` with audio domain |
| **Speech Synthesis** | Modality-specific | Use `generate` with `domain: audio` |
| **Depth Estimation** | Vision-specific measurement | Use `measure` with `domain: depth` |
| **Image-to-3D** | Complex transformation | Workflow: `detect` → `transform` → `generate` |
| **Personalization** | User adaptation | Use `state` (user model) + `transform` |
| **Bias Mitigation** | Ethical constraint | Use `constrain` with bias detection rules |
| **Content Moderation** | Safety filtering | Use `classify` + `constrain` |

**Conclusion:** No new atomic capabilities needed. All OASF skills can be expressed through domain parameterization or workflow composition.

### 4.2 Grounded Agency Capabilities Missing from OASF

| Capability | Gap in OASF | Significance |
|------------|-------------|--------------|
| `ground` | No explicit evidence anchoring | **Critical for safety** |
| `checkpoint` | No state preservation before mutations | **Critical for rollback** |
| `rollback` | No recovery mechanism | **Critical for safety** |
| `inquire` | No structured clarification capability | **Important for human-in-loop** |
| `attribute` | No causal reasoning primitive | **Important for explanation** |
| `simulate` | Implicit in planning, not explicit | **Important for what-if analysis** |
| `synchronize` | Multi-agent state agreement missing | **Important for coordination** |

**Conclusion:** OASF lacks explicit safety primitives that are foundational to Grounded Agency.

---

## 5. OASF Skills as Workflow Patterns

The following OASF capabilities would be better expressed as composed workflows using our atomic capabilities:

### 5.1 RAG Pipeline (OASF Category 6)

```yaml
rag_pipeline:
  goal: Retrieve relevant information and generate grounded response
  steps:
  - capability: search
    purpose: Find relevant documents
  - capability: retrieve
    purpose: Fetch document content
  - capability: detect
    purpose: Extract relevant passages
    domain: relevance
  - capability: ground
    purpose: Anchor response to retrieved evidence
  - capability: generate
    purpose: Produce response
  - capability: explain
    purpose: Cite sources
```

### 5.2 Security Assessment (OASF Category 8)

```yaml
security_assessment:
  goal: Identify and assess security vulnerabilities
  steps:
  - capability: search
    purpose: Scan for known vulnerability patterns
  - capability: detect
    domain: vulnerability
    purpose: Find potential security issues
  - capability: measure
    domain: severity
    purpose: Assess risk level
  - capability: attribute
    purpose: Identify root causes
  - capability: critique
    purpose: Evaluate mitigation options
  - capability: generate
    domain: report
    purpose: Produce security report
  - capability: audit
    purpose: Record assessment findings
```

### 5.3 Multi-Agent Orchestration (OASF Category 10)

```yaml
multi_agent_orchestration:
  goal: Coordinate multiple agents on complex task
  steps:
  - capability: decompose
    purpose: Break task into subtasks
  - capability: plan
    purpose: Create execution plan with dependencies
  - capability: delegate
    purpose: Assign subtasks to appropriate agents
  - capability: synchronize
    purpose: Coordinate shared state
  - capability: verify
    purpose: Validate subtask results
  - capability: integrate
    purpose: Merge results from multiple agents
  - capability: audit
    purpose: Record orchestration decisions
```

### 5.4 Data Quality Pipeline (OASF Category 9)

```yaml
data_quality_pipeline:
  goal: Clean and validate data
  steps:
  - capability: observe
    purpose: Examine raw data
  - capability: detect
    domain: data_issue
    purpose: Find quality problems
  - capability: classify
    purpose: Categorize issue types
  - capability: measure
    domain: quality
    purpose: Compute quality metrics
  - capability: transform
    purpose: Apply cleaning operations
  - capability: verify
    purpose: Validate cleaned data
  - capability: audit
    purpose: Record transformations applied
```

### 5.5 MLOps Model Deployment (OASF Category 12)

```yaml
model_deployment:
  goal: Safely deploy ML model to production
  risk: high
  steps:
  - capability: verify
    purpose: Validate model artifacts
  - capability: constrain
    purpose: Check deployment policies
  - capability: checkpoint
    purpose: Save rollback point
  - capability: execute
    purpose: Run deployment scripts
  - capability: verify
    purpose: Validate deployment success
  - capability: measure
    domain: performance
    purpose: Check model performance
  - capability: audit
    purpose: Record deployment event
  gates:
  - when: ${verify_out.passed} == false
    action: rollback
```

---

## 6. Recommendations

### 6.1 For Grounded Agency Enhancement

1. **Add domain profiles for OASF categories** - Create profiles for Vision, Audio, and Multi-modal domains that specialize our capabilities for those modalities.

2. **Create workflow patterns for common OASF skills** - Add the workflow patterns defined in Section 5 to the workflow catalog.

3. **Document modality handling** - Clarify how image, audio, video, and multi-modal inputs should be handled via domain parameters.

### 6.2 For Interoperability

1. **Create OASF-to-Grounded-Agency mapping file** - A machine-readable mapping that translates OASF skill codes to our capabilities.

2. **Define capability adapters** - For systems using OASF, provide adapters that wrap our capabilities with OASF-compatible interfaces.

3. **Propose safety extensions to OASF** - The OASF community could benefit from Grounded Agency's safety primitives (`ground`, `checkpoint`, `rollback`, `constrain`).

### 6.3 Key Differentiators to Preserve

Our ontology's strengths that should not be compromised:

1. **Evidence anchors in all outputs** - Never optional
2. **Checkpoint-before-mutate requirement** - Structural safety
3. **Typed capability contracts** - Enable formal verification
4. **Cognitive layer organization** - Supports reasoning about agent behavior
5. **Explicit edge semantics** - Enables workflow validation

---

## 7. Conclusion

OASF and Grounded Agency represent complementary approaches to agent capability standardization:

- **OASF** provides a comprehensive **skill taxonomy** useful for categorizing what agents can do
- **Grounded Agency** provides a **cognitive architecture** focused on how agents should reason safely

The frameworks are not mutually exclusive. OASF skills can be implemented using Grounded Agency capabilities, benefiting from our safety guarantees and composability model. Conversely, OASF's extensive skill taxonomy identifies specific domain applications that could inform new workflow patterns.

**Bottom Line:** Every OASF skill can be expressed through our 36 atomic capabilities via domain parameterization or workflow composition, while gaining safety properties (evidence anchors, checkpoints, verification) that OASF lacks.

---

## Appendix A: Complete OASF Skill Category Mapping

| OASF ID | OASF Skill | Grounded Agency Mapping |
|---------|------------|------------------------|
| 101 | NLU | `detect` + `classify` |
| 102 | NLG | `generate` |
| 103 | Information Retrieval | `search` + `retrieve` + `ground` |
| 104 | Creative Content | `generate` with creative domain |
| 105 | Translation | `transform` with language domain |
| 106 | Personalization | `state` (user) + `transform` |
| 107 | Analytical Reasoning | `decompose` + `plan` + `explain` |
| 108 | Ethics/Safety | `constrain` + `classify` |
| 109 | Text Classification | `classify` |
| 110 | Module Extraction | `detect` + `transform` |
| 111 | Token Classification | `detect` with token domain |
| 2 | Computer Vision | `detect` + `classify` + `generate` + `transform` (image domain) |
| 3 | Audio | `detect` + `classify` + `generate` + `transform` (audio domain) |
| 4 | Tabular | `classify` + `predict` (tabular domain) |
| 5 | Analytical | `measure` + `generate` (code/math domain) |
| 6 | RAG | Workflow: `search` → `retrieve` → `ground` → `generate` |
| 7 | Multi-modal | `transform` with modality parameters |
| 8 | Security | `detect` + `measure` + `constrain` (security domain) |
| 9 | Data Engineering | `transform` + `verify` + `measure` |
| 10 | Orchestration | `decompose` + `delegate` + `synchronize` |
| 11 | Evaluation | `verify` + `measure` + `audit` |
| 12 | DevOps/MLOps | Workflow patterns with `execute` + `verify` + `checkpoint` |
| 13 | Governance | `constrain` + `audit` + `verify` |
| 14 | Tool Interaction | `invoke` + `execute` |
| 15 | Advanced Reasoning | `plan` + `decompose` + `simulate` + `predict` |

## Appendix B: Grounded Agency Capabilities Without OASF Equivalent

| Capability | Layer | Why OASF Lacks It |
|------------|-------|-------------------|
| `ground` | MODEL | OASF has no explicit evidence anchoring requirement |
| `checkpoint` | VERIFY | OASF has no state preservation primitive |
| `rollback` | VERIFY | OASF has no recovery mechanism |
| `attribute` | MODEL | OASF lacks explicit causal reasoning |
| `simulate` | MODEL | OASF planning is implicit, not counterfactual |
| `inquire` | COORDINATE | OASF lacks structured clarification |
| `synchronize` | COORDINATE | OASF orchestration lacks state agreement |
| `transition` | MODEL | OASF has no explicit dynamics modeling |
| `state` | MODEL | OASF lacks explicit world state representation |

---

*This comparison was generated on 2026-01-28 and reflects OASF version 0.8.0 and Grounded Agency version 2.0.0.*
