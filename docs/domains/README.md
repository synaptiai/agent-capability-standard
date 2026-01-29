# Domain Templates

This directory contains domain-specific workflow templates and configuration profiles for the Grounded Agency framework.

## What Are Domain Templates?

Domain templates provide ready-to-use starting points for specific industry verticals. Each domain includes:

- **Profile** — Trust weights, risk thresholds, and checkpoint policies calibrated for the domain
- **Workflows** — Pre-composed workflow patterns using the 36 atomic capabilities
- **Documentation** — Guidance on customization and integration

## Available Domains

| Domain | Profile | Workflows | Key Characteristics |
|--------|---------|-----------|-------------------|
| [Manufacturing](./manufacturing/README.md) | [manufacturing.yaml](../../schemas/profiles/manufacturing.yaml) | 4 workflows | Safety-critical, sensor-primary, regulatory |
| [Personal Assistant](./personal-assistant/README.md) | [personal_assistant.yaml](../../schemas/profiles/personal_assistant.yaml) | 4 workflows | User-centric, communication-safe, preference-learning |
| [Data Analysis](./data-analysis/README.md) | [data_analysis.yaml](../../schemas/profiles/data_analysis.yaml) | 4 workflows | Quality-focused, reproducible, statistical rigor |
| [Healthcare](./healthcare/README.md) | [healthcare.yaml](../../schemas/profiles/healthcare.yaml) | 4 workflows | Advisory-only, patient-safety, regulated |
| [Vision](./vision/README.md) | [vision.yaml](../../schemas/profiles/vision.yaml) | 4 workflows | Visual-evidence-primary, spatially-grounded, generation-gated |
| [Audio](./audio/README.md) | [audio.yaml](../../schemas/profiles/audio.yaml) | 4 workflows | Temporal-evidence-primary, signal-quality-aware, speaker-privacy-gated |
| [Multi-modal](./multimodal/README.md) | [multimodal.yaml](../../schemas/profiles/multimodal.yaml) | 4 workflows | Cross-modal-consistent, alignment-verified, modality-trust-ranked |

## Choosing a Domain

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

5. **Create workflow files** in `schemas/workflows/`

6. **Document** in `docs/domains/<your-domain>/README.md`

7. **Validate** workflows against the capability ontology:
   ```bash
   python tools/validate_workflows.py
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
