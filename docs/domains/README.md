# Domain Templates

This directory contains domain-specific workflow templates and configuration profiles for the Grounded Agency framework.

## What Are Domain Templates?

Domain templates provide ready-to-use starting points for specific industry verticals. Each domain includes:

- **Profile** — Trust weights, risk thresholds, and checkpoint policies calibrated for the domain, as informative data (see [Status of Domain Profiles](#status-of-domain-profiles))
- **Workflows** — Pre-composed workflow patterns using the 36 atomic capabilities
- **Documentation** — Guidance on customization and integration

## Status of Domain Profiles

A domain profile is informative data for hosts and workflow authors. It records what the authors of a domain consider appropriate: how far to trust each source, which risk levels and capabilities call for a person, when to take a checkpoint and what evidence to expect. It changes nothing about how a workflow is validated or run, or about what a tool call is allowed to do.

- **The Standard does not say how a profile is applied.** Standard 1.1.0 mentions profiles twice: `profile` is a recognised descriptive workflow field ([§5.1](../../spec/STANDARD-v1.1.0.md#51-catalog-and-workflow-definition)), and a `trust_weights` key of the form `trust_class:<class>` overrides the weight of a trust class ([§8.3](../../spec/STANDARD-v1.1.0.md#83-trust-classes)). It does not say how a run selects a profile, or what any other setting changes.
- **No shipped component loads or selects a profile.** The validator and the executor (`core/`), the Python package (`grounded_agency/`) and the plugin hooks (`hooks/`) do not load `schemas/profiles/*.yaml`. One setting has reference code: the trust arithmetic of `grounded_agency/trust.py` applies a profile's `trust_weights` to a static weight when its caller passes them (a `trust_class:<class>` key as the class weight of §8.3, any other key as a source weight), and reads no file. Nothing applies any other setting. `tools/validate_profiles.py` checks the shape of a profile: required fields, types, value ranges and enumerations. It does not check that the entries of `block_autonomous` and `require_grounding` are capability ids, or that a listed workflow exists.
- **The settings are not tied to the Standard's vocabulary.** `require_human` admits `critical`, which is not one of the risk levels of [§4.1](../../spec/STANDARD-v1.1.0.md#41-capability-definition) (`low`, `medium`, `high`). The keys of `checkpoint_policy` are free-form labels. None of the `required_anchor_types` in the shipped profiles is an `Anchor.kind` of `schemas/event_schema.yaml`, and none of their `trust_weights` keys has the `trust_class:<class>` form of §8.3.

A setting such as `block_autonomous`, `require_human`, `checkpoint_policy` or `minimum_confidence` therefore takes effect only where a host implements it, or where a workflow author writes it into the workflow, for example by raising a step's `requires_approval` ([§5.2.1](../../spec/STANDARD-v1.1.0.md#521-safety-flags)). Where this documentation says that a profile requires, blocks or never allows something, that is what the profile declares, not something a shipped component enforces.

What is enforced today rests on the ontology's safety flags and on workflows, not on profiles:

| What is enforced | By what |
|------------------|---------|
| A workflow in which `mutate`, `send` or `rollback` has no `checkpoint` step running before it does not validate (V102). A step's safety flags are the stricter of its own declaration and the ontology's; a weaker declaration has no effect and is reported (W602) | The validator in `core/`, run by `tools/validate_workflows.py` ([§4.3](../../spec/STANDARD-v1.1.0.md#43-edge-types-and-dependency-semantics), [§5.2.1](../../spec/STANDARD-v1.1.0.md#521-safety-flags)) |
| A step whose effective `requires_checkpoint` is true runs only on a valid checkpoint, and a step whose effective `requires_approval` is true runs only on a decision bound to what the approver was shown. In the ontology `mutate` and `send` carry both flags and `execute` carries `requires_approval` | The reference executor in `core/` ([Running workflows](../guides/RUNNING_WORKFLOWS.md#what-the-executor-enforces), [§5.14](../../spec/STANDARD-v1.1.0.md#514-approval)) |
| A tool call is classified by a capability. In strict mode a call whose capability requires a checkpoint is denied when no valid checkpoint exists (F501). A call whose capability requires approval is put to the host's permission flow (F502), unless the adapter is configured with `approval="off"`. Calls are rate-limited by risk level | The Python adapter, `grounded_agency/adapter.py` ([Claude Agent SDK integration](../integrations/claude_agent_sdk.md)) |
| A Write, Edit, MultiEdit, NotebookEdit or Bash call is blocked unless a valid, unexpired checkpoint marker exists (F501). The hook asks for no approval | The Claude Code plugin hook, `hooks/pretooluse_require_checkpoint.sh` ([Safety hooks](../../hooks/README.md)) |

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
trust_weights:      # Source-specific trust (0.0 to 1.0)
risk_thresholds:    # What risk levels require human involvement
checkpoint_policy:  # When to create checkpoints
evidence_policy:    # Evidence requirements for claims
domain_sources:     # Expected data sources
workflows:          # Recommended workflows
```

## Creating a Custom Domain

1. **Copy an existing profile** as a starting point:
   ```bash
   cp schemas/profiles/manufacturing.yaml schemas/profiles/my_domain.yaml
   ```

2. **Adjust trust weights** for your data sources

3. **Set risk thresholds** appropriate for your domain

4. **Define checkpoint policy** based on what actions are critical

5. **Create workflow files** in `schemas/workflows/`. Nothing applies a profile to a workflow ([Status of Domain Profiles](#status-of-domain-profiles)), so write the checkpoints and approvals the domain needs into the workflows themselves: a `checkpoint` step before a step that changes state, and `requires_approval: true` or `requires_checkpoint: true` on a step whose ontology flags are weaker than the profile asks for

6. **Document** in `docs/domains/<your-domain>/README.md`

7. **Validate** workflows against the capability ontology (without `--catalog` the validator checks only `schemas/workflow_catalog.yaml`). CI runs this in strict mode for every file in `schemas/workflows/`, so warnings fail too:
   ```bash
   python tools/validate_workflows.py --catalog schemas/workflows/<your-domain>_workflows.yaml --strict
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

## Related Documentation

- [Capability Ontology](../../schemas/capability_ontology.yaml) — The 36 atomic capabilities
- [Workflow Catalog](../../schemas/workflow_catalog.yaml) — Core workflow patterns
- [Getting Started](../QUICKSTART.md) — Quick start guide
