# Domain Templates

This directory contains domain-specific workflow templates and configuration profiles for the Grounded Agency framework.

## What Are Domain Templates?

Domain templates provide ready-to-use starting points for specific industry verticals. Each domain includes:

- **Profile** — Trust weights, risk thresholds, checkpoint rules and evidence requirements calibrated for the domain, which take effect where a host, a safety layer or the validator applies the profile (see [Status of Domain Profiles](#status-of-domain-profiles))
- **Workflows** — Pre-composed workflow patterns using the 36 atomic capabilities
- **Documentation** — Guidance on customization and integration

## Available Domains

| Domain | Profile | Workflows | Key Characteristics |
|--------|---------|-----------|-------------------|
| [Manufacturing](./manufacturing/README.md) | [manufacturing.yaml](../../schemas/profiles/manufacturing.yaml) | 4 workflows | Safety-critical, sensor-primary, regulatory |
| [Personal Assistant](./personal-assistant/README.md) | [personal_assistant.yaml](../../schemas/profiles/personal_assistant.yaml) | 4 workflows | User-centric, communication-safe, preference-learning |
| [Data Analysis](./data-analysis/README.md) | [data_analysis.yaml](../../schemas/profiles/data_analysis.yaml) | 4 workflows | Quality-focused, reproducible, statistical rigor |
| [Healthcare](./healthcare/README.md) | [healthcare.yaml](../../schemas/profiles/healthcare.yaml) | 4 workflows | Advisory-only, patient-safety, regulated |
| [Vision](./vision/README.md) | [vision.yaml](../../schemas/profiles/vision.yaml) | 4 proposed (not yet in a catalog) | Visual-evidence-primary, spatially-grounded, generation-gated |
| [Audio](./audio/README.md) | [audio.yaml](../../schemas/profiles/audio.yaml) | 4 proposed (not yet in a catalog) | Temporal-evidence-primary, signal-quality-aware, speaker-privacy-gated |
| [Multi-modal](./multimodal/README.md) | [multimodal.yaml](../../schemas/profiles/multimodal.yaml) | 4 proposed (not yet in a catalog) | Cross-modal-consistent, alignment-verified, modality-trust-ranked |

## Choosing a Domain

The key settings listed for each domain are what its profile declares. [Status of Domain Profiles](#status-of-domain-profiles) says what enforces a rule today.

### Manufacturing

Choose this if you're building agents for:
- Production line monitoring
- Quality control and inspection
- Predictive maintenance
- Supply chain management

**Key profile settings:**
- High trust for sensors (0.92-0.95)
- Checkpoints before all actuator commands
- Human required for all mutations

### Personal Assistant

Choose this if you're building agents for:
- Schedule management
- Information research
- Task delegation
- Communication drafting

**Key profile settings:**
- Highest trust for explicit user input (0.98)
- Checkpoints before all communications
- Never auto-send messages

### Data Analysis

Choose this if you're building agents for:
- Data pipeline validation
- Anomaly investigation
- Report generation
- ML model monitoring

**Key profile settings:**
- High trust for certified data (0.95)
- Required data lineage grounding
- Statistical uncertainty in all measurements

### Healthcare

Choose this if you're building clinical decision support for:
- Patient monitoring
- Clinical alert triage
- Care plan review
- Care handoffs

**Key profile settings:**
- NO autonomous clinical actions
- 7-year audit retention
- All outputs include clinical disclaimers

### Vision

Choose this if you're building agents for:
- Image classification and object detection
- Visual quality inspection
- Image generation with review pipelines
- Computer vision pipelines

**Key profile settings:**
- High trust for calibrated cameras (0.93-0.95)
- Checkpoints before all image modifications and generation
- Evidence requires image references and bounding boxes

### Audio

Choose this if you're building agents for:
- Speech recognition and transcription
- Audio classification and event detection
- Speaker verification
- Audio quality assessment

**Key profile settings:**
- High trust for studio recordings (0.93-0.95)
- Checkpoints before speaker identification
- Evidence requires time segments and signal quality metrics

### Multi-modal

Choose this if you're building agents for:
- Image captioning and visual question answering
- Text-to-image or text-to-video generation
- Cross-modal search and retrieval
- Document understanding (OCR + layout)

**Key profile settings:**
- Trust decreases with each generation step
- Checkpoints before all modality conversions
- Evidence requires source/target modality identification and alignment scores

## Profile Schema

All domain profiles follow the schema defined in [profile_schema.yaml](../../schemas/profiles/profile_schema.yaml).

Key sections:

```yaml
standard: "1.2.0"   # The Standard and ontology the profile is written for
ontology: "2.2.0"
trust_weights:      # Source and trust-class weights (0.0 to 1.0)
risk_thresholds:    # Which steps need approval, and which a person's
checkpoint_policy:  # Capability ids or "*" that need a checkpoint
evidence_policy:    # Grounding, anchor kinds and a minimum confidence
allowed_destinations: # Where a send may go
domain_sources:     # Expected data sources (informative)
workflows:          # Recommended workflows (informative)
```

## Creating a Custom Domain

1. **Copy an existing profile** as a starting point:
   ```bash
   cp schemas/profiles/manufacturing.yaml schemas/profiles/my_domain.yaml
   ```

2. **Adjust trust weights** for your data sources

3. **Set risk thresholds** appropriate for your domain

4. **Define checkpoint policy**: capability ids, or `"*"` (quoted) for every one but `checkpoint`, mapped to `always`, `high_risk`, `medium_risk` or `never`. Check the profile with `python tools/validate_profiles.py`: an unknown id or member is an error ([§5.21.2](../../spec/STANDARD-v1.2.0.md#5212-loading-a-profile))

5. **Create workflow files** in `schemas/workflows/`. A workflow does not select its profile, so one that needs a checkpoint or an approval wherever it runs declares it: a `checkpoint` step, `requires_approval: true`

6. **Document** in `docs/domains/<your-domain>/README.md`

7. **Validate** workflows against the capability ontology (without `--catalog` the validator checks only `schemas/workflow_catalog.yaml`). CI runs this in strict mode for every file in `schemas/workflows/`, so warnings fail too:
   ```bash
   python tools/validate_workflows.py --catalog schemas/workflows/<your-domain>_workflows.yaml --strict
   python tools/validate_workflows.py --catalog schemas/workflows/<your-domain>_workflows.yaml --strict \
     --profile schemas/profiles/<your_domain>.yaml   # as a run under the profile would be checked
   ```

## How Domains Demonstrate Domain-Agnostic Capabilities

The 36 atomic capabilities are intentionally domain-agnostic. The same `detect` capability works for:
- **Manufacturing:** Detecting sensor anomalies
- **Personal Assistant:** Detecting scheduling conflicts
- **Data Analysis:** Detecting data drift
- **Healthcare:** Detecting clinical patterns

What changes is the **domain parameter**:

```yaml
# Manufacturing
detect:
  domain: anomaly
  pattern: statistical_deviation

# Healthcare
detect:
  domain: clinical_pattern
  pattern: early_warning_score
```

This proves the atomic capability set is complete — different domains compose the same building blocks with domain-specific parameterization.

## Status of Domain Profiles

A domain profile takes effect where it is **applied** (Standard 1.2.0
[§5.21](../../spec/STANDARD-v1.2.0.md#521-domain-profiles)): by the reference
executor (`Run.start(profiles=…)`, `WorkflowRunner(profiles=…)`), the
validator (`tools/validate_workflows.py --profile`), the Python adapter
(`GroundedAgentConfig(profiles=…)`), the Standard Agents binding and
TypeScript hosts through the WebAssembly core; never by a workflow's
`profile` field or the plugin hooks. Applied, a profile only tightens: its
thresholds and `checkpoint_policy` raise the flags of steps and calls (under
`require_human` and `block_autonomous` a person approves each one, which no
standing mandate covers), and an output fails that its grounding policy
(`require_grounding`, §5.20) finds ungrounded (F505) or that is below
`minimum_confidence` (F504). Its `trust_weights` replace weights where a
host computes trust scores (`grounded_agency.trust`). A profile with an
error is refused; a misspelled top-level member is a logged warning (W604).

A profile's destination policy (`allowed_destinations`, §4.4.2) is in force
beside the host's own: the executor fails a `send` step it does not allow,
and the Python adapter and the Standard Agents binding refuse such a `send`
call, with F504 and before approval; an empty list allows no send. No
shipped profile (`schemas/profiles/`, examples, version 2.0.0) sets one.

Without a profile, what is enforced rests on the ontology's safety flags:

| What is enforced | By what |
|------------------|---------|
| No `mutate`, `send` or `rollback` step without a `checkpoint` step before it (V102); a step's flags are never weaker than the ontology's (W602) | The validator in `core/` ([§5.2.1](../../spec/STANDARD-v1.2.0.md#521-safety-flags)) |
| A step runs only on a valid checkpoint and a decision on what the approver was shown, where its flags require them | The reference executor ([Running workflows](../guides/RUNNING_WORKFLOWS.md#what-the-executor-enforces)) |
| A tool call needs a checkpoint (F501, strict mode) and is put to the host for approval (F502), where its capability requires them | The Python adapter ([Claude Agent SDK integration](../integrations/claude_agent_sdk.md)) |
| A Write, Edit, MultiEdit, NotebookEdit or Bash call needs a valid checkpoint marker (F501) | The plugin hook ([Safety hooks](../../hooks/README.md)) |
| A profile's `evidence_policy`, when a host applies it, is a grounding policy: outputs are grounded or marked inferred (F505, [§5.20](../../spec/STANDARD-v1.2.0.md#520-grounding)) | The executor, the Python adapter and the binding |

## Related Documentation

- [Capability Ontology](../../schemas/capability_ontology.yaml) — The 36 atomic capabilities
- [Workflow Catalog](../../schemas/workflow_catalog.yaml) — Core workflow patterns
- [Getting Started](../QUICKSTART.md) — Quick start guide
