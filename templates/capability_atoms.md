# Capability Atoms

This library merges:
- DIS feature atoms (Detect/Identify/Estimate/Forecast/Compare/Discover/Generate/Act)
- Agentic + world-modeling atoms (retrieve/search/inspect, schema/graphs, planning, verification, governance, world modeling)

You can treat each capability as an "atomic unit" and compose them into higher-level workflows.

## Reference List (99 Capabilities)

> **Source of truth**: `schemas/capability_ontology.json`

### PERCEPTION (4)

Input and sensing capabilities for data acquisition.

| Capability | Description |
|------------|-------------|
| `inspect` | Examine data structure and content |
| `receive` | Accept incoming data or events |
| `retrieve` | Fetch specific data by reference |
| `search` | Find data matching criteria |

### MODELING (45)

World understanding and representation capabilities.

| Capability | Description |
|------------|-------------|
| `causal-model` | Build cause-effect relationship models |
| `detect` | Determine if pattern/entity/condition exists |
| `detect-activity` | Detect specific activities or behaviors |
| `detect-anomaly` | Detect deviations from expected patterns |
| `detect-attribute` | Detect specific attributes or properties |
| `detect-entity` | Detect entities in data |
| `detect-person` | Detect person-related patterns |
| `detect-world` | Detect world state changes |
| `diff-world-state` | Compare world states to identify changes |
| `digital-twin` | Create/maintain digital twin representations |
| `estimate` | Approximate values with uncertainty |
| `estimate-activity` | Estimate activity metrics |
| `estimate-attribute` | Estimate attribute values |
| `estimate-impact` | Estimate impact of changes |
| `estimate-outcome` | Estimate probable outcomes |
| `estimate-relationship` | Estimate relationship strength |
| `estimate-risk` | Estimate risk levels |
| `estimate-world` | Estimate world state parameters |
| `forecast` | Predict future states |
| `forecast-attribute` | Forecast attribute changes |
| `forecast-impact` | Forecast impact over time |
| `forecast-outcome` | Forecast probable outcomes |
| `forecast-risk` | Forecast risk evolution |
| `forecast-time` | Forecast temporal aspects |
| `forecast-world` | Forecast world state evolution |
| `grounding` | Anchor outputs to evidence |
| `identify` | Determine specific identity of entity |
| `identify-activity` | Identify specific activities |
| `identify-anomaly` | Identify specific anomalies |
| `identify-attribute` | Identify specific attributes |
| `identify-entity` | Identify specific entities |
| `identify-human-attribute` | Identify human-specific attributes |
| `identify-person` | Identify specific persons |
| `identify-world` | Identify world state components |
| `identity-resolution` | Resolve entity identity across sources |
| `integrate` | Combine data from multiple sources |
| `map-relationships` | Map dependencies and connections |
| `model-schema` | Create/validate data schemas |
| `provenance` | Track data origin and lineage |
| `simulation` | Run predictive simulations |
| `spatial-reasoning` | Reason about spatial relationships |
| `state-transition` | Model state changes |
| `temporal-reasoning` | Reason about temporal relationships |
| `uncertainty-model` | Quantify and propagate uncertainty |
| `world-state` | Represent current world state |

### REASONING (20)

Analysis, planning, and decision-making capabilities.

| Capability | Description |
|------------|-------------|
| `compare` | Compare entities or values |
| `compare-attributes` | Compare specific attributes |
| `compare-documents` | Compare document contents |
| `compare-entities` | Compare entity properties |
| `compare-impact` | Compare impact assessments |
| `compare-people` | Compare person attributes |
| `compare-plans` | Compare alternative plans |
| `critique` | Critically analyze proposals |
| `decide` | Make decisions from options |
| `decompose` | Break down complex problems |
| `evaluate` | Assess quality or fitness |
| `explain` | Generate explanations |
| `generalize` | Extract general patterns |
| `optimize` | Find optimal solutions |
| `plan` | Create action sequences |
| `prioritize` | Rank by importance |
| `schedule` | Arrange in time sequence |
| `summarize` | Condense information |
| `translate` | Convert between representations |
| `validate` | Check correctness |

### ACTION (12)

Execution and generation capabilities that produce outputs or side effects.

| Capability | Description |
|------------|-------------|
| `act` | Execute mutations with verification |
| `act-plan` | Execute a planned sequence |
| `generate` | Produce new content |
| `generate-attribute` | Generate specific attributes |
| `generate-audio` | Generate audio content |
| `generate-image` | Generate image content |
| `generate-numeric-data` | Generate numerical data |
| `generate-plan` | Generate action plans |
| `generate-text` | Generate text content |
| `generate-world` | Generate world representations |
| `send` | Transmit data externally |
| `transform` | Convert data formats |

### SAFETY (7)

Guardrail and verification capabilities for safe operation.

| Capability | Description |
|------------|-------------|
| `audit` | Record actions for accountability |
| `checkpoint` | Create restore points |
| `constrain` | Apply operational limits |
| `improve` | Enhance based on feedback |
| `mitigate` | Reduce identified risks |
| `rollback` | Restore previous state |
| `verify` | Confirm correctness |

### META (6)

Discovery and self-reflection capabilities.

| Capability | Description |
|------------|-------------|
| `discover` | Find new patterns or entities |
| `discover-activity` | Discover activities |
| `discover-anomaly` | Discover anomalies |
| `discover-human-attribute` | Discover human attributes |
| `discover-outcome` | Discover outcomes |
| `discover-relationship` | Discover relationships |

### MEMORY (2)

Persistence capabilities for state management.

| Capability | Description |
|------------|-------------|
| `persist` | Save state durably |
| `recall` | Retrieve persisted state |

### COORDINATION (3)

Multi-agent and workflow coordination capabilities.

| Capability | Description |
|------------|-------------|
| `delegate` | Assign tasks to other agents |
| `invoke-workflow` | Execute composed workflows |
| `synchronize` | Coordinate state across agents |

---

## Layer Summary

| Layer | Count | Purpose |
|-------|-------|---------|
| PERCEPTION | 4 | Input/sensing |
| MODELING | 45 | World understanding |
| REASONING | 20 | Analysis/planning |
| ACTION | 12 | Execution/generation |
| SAFETY | 7 | Guardrails |
| META | 6 | Discovery |
| MEMORY | 2 | Persistence |
| COORDINATION | 3 | Multi-agent |
| **Total** | **99** | |

## Usage

To get the latest capability list programmatically:

```bash
cat schemas/capability_ontology.json | jq -r '.nodes[] | "\(.layer): \(.id)"' | sort
```
