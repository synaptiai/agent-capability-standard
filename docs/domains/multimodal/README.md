# Multi-modal Domain

This document describes how to use the Grounded Agency framework for multi-modal AI environments combining text, image, audio, and video.

## Overview

The multi-modal domain profile is calibrated for environments where:
- **Cross-modal consistency is critical** -- Claims must be grounded across modalities
- **Alignment verification is required** -- Text-image or audio-visual pairs must be validated
- **Generation trust varies by modality** -- Generated video is less trusted than generated text
- **Transformation pipelines span modalities** -- Image-to-text, text-to-image, speech-to-text

This profile maps to [OASF Category 7 (Multi-modal)](https://schema.oasf.outshift.com/skill_categories) (see also `schemas/interop/oasf_mapping.yaml` for the local mapping), covering image-to-text, text-to-video, speech recognition, visual question answering, and cross-modal transformations.

## Domain Profile

**Profile location:** `schemas/profiles/multimodal.yaml`

### Trust Weights

Multi-modal environments trust aligned and verified sources over generated cross-modal outputs:

| Source | Trust Weight | Rationale |
|--------|-------------|-----------|
| Aligned Dataset | 0.93 | Pre-aligned multi-modal pairs (e.g., image-caption) |
| Synchronized Capture | 0.92 | Simultaneously captured multi-modal data |
| Human Alignment Label | 0.92 | Human-verified cross-modal alignment |
| Expert Assessment | 0.90 | Domain expert cross-modal evaluation |
| Text Input | 0.90 | Verified text content |
| Image Input | 0.88 | Verified image content |
| Video Input | 0.87 | Verified video content |
| Audio Input | 0.85 | Verified audio content |
| Cross-modal Embedding | 0.75 | Shared embedding representations |
| Generated Text | 0.72 | AI-generated text from other modalities |
| Model Prediction | 0.65 | Cross-modal model predictions |
| Generated Image | 0.60 | AI-generated images |
| Generated Audio | 0.58 | AI-synthesized audio |
| Generated Video | 0.55 | AI-generated video (lowest confidence) |

*Sorted by source category; see profile YAML for exact grouping.*

### Risk Thresholds

```yaml
auto_approve: low       # Only low-risk analyses auto-approved
require_review: medium  # Medium+ requires human review
require_human: high     # High-risk cross-modal decisions require human
block_autonomous:
  - mutate              # Never autonomously modify source content
  - send                # Never autonomously distribute generated content
  - generate            # Never autonomously generate without review
```

### Checkpoint Policy

Multi-modal workflows require checkpoints before any action that:
- Converts content between modalities
- Generates new content in any modality
- Makes cross-modal alignment decisions
- Processes large batch transformations

## Capability Usage

The 36 atomic capabilities apply to multi-modal work through domain parameterization:

### Detection (Cross-modal)

```yaml
detect:
  domain: cross_modal_alignment
  input:
    image_ref: "s3://dataset/scene_042.jpg"
    text: "A red car parked on a street"
    model: "clip-alignment-v2"
  output:
    alignment_score: 0.87
    misaligned_elements: []
    evidence_anchors:
      - type: source_modality
        ref: "image: s3://dataset/scene_042.jpg"
      - type: target_modality
        ref: "text: A red car parked..."
      - type: alignment_score
        value: 0.87
```

### Transformation (Image-to-Text)

```yaml
transform:
  domain: captioning
  input:
    source: "camera://scene/frame-1042.jpg"
    source_format: image
    target_format: text
    detail_level: "detailed"
  output:
    caption: "A manufacturing floor with three conveyor belts..."
    evidence_anchors:
      - type: source_modality
        ref: "image: camera://scene/frame-1042.jpg"
      - type: target_modality
        ref: "text caption"
      - type: confidence_score
        value: 0.84
      - type: modality_hash
        source: "sha256:abc..."
```

### Transformation (Text-to-Image)

```yaml
transform:
  domain: image_generation
  input:
    source: "Generate a technical diagram of the assembly process"
    source_format: text
    target_format: image
    constraints:
      style: "technical"
      resolution: "1024x1024"
  output:
    image_ref: "generated://diagram-uuid-789.png"
    evidence_anchors:
      - type: source_modality
        ref: "text prompt"
      - type: target_modality
        ref: "generated image"
      - type: modality_hash
        value: "sha256:def..."
```

### Classification (Visual Question Answering)

```yaml
classify:
  domain: visual_qa
  input:
    image_ref: "s3://dataset/chart_017.png"
    question: "What is the trend shown in this chart?"
    taxonomy: ["increasing", "decreasing", "stable", "fluctuating"]
  output:
    label: "increasing"
    explanation: "The line chart shows consistent upward movement..."
    confidence: 0.91
    evidence_anchors:
      - type: source_modality
        ref: "image: s3://dataset/chart_017.png"
      - type: source_modality
        ref: "text question"
      - type: confidence_score
        value: 0.91
```

## Available Workflows

> **Note:** These workflows are proposed and pending inclusion in the workflow catalog. See the [workflow catalog](../../../schemas/workflow_catalog.yaml) for currently available patterns.

### 1. Image Captioning Pipeline

**Goal:** Generate natural language captions for images with cross-modal evidence grounding.

**Capabilities used:**
- `retrieve` -- Load image and captioning model configuration
- `observe` -- Inspect image features and content
- `detect` -- Detect objects and scene elements
- `classify` -- Classify scene type and attributes
- `transform` -- Convert visual features to text caption
- `ground` -- Anchor caption to source image regions
- `verify` -- Validate caption accuracy against image content
- `checkpoint` -- Checkpoint before final output
- `audit` -- Record captioning decision and provenance

**Trigger:** Image submission

**Output:** Caption with alignment score, confidence, and modality provenance

### 2. Visual Question Answering

**Goal:** Answer natural language questions about images with grounded evidence.

**Capabilities used:**
- `retrieve` -- Load image and question context
- `observe` -- Inspect relevant image regions
- `detect` -- Detect entities referenced in the question
- `classify` -- Classify answer from visual evidence
- `ground` -- Anchor answer to specific image regions and question
- `explain` -- Generate answer explanation with cross-modal evidence
- `verify` -- Validate answer against visual evidence
- `audit` -- Record QA decision and provenance

**Trigger:** Question-image pair submission

**Output:** Answer with cross-modal evidence anchors and confidence

### 3. Text-to-Image Generation

**Goal:** Generate images from text prompts with review and provenance tracking.

**Capabilities used:**
- `retrieve` -- Load generation constraints and style guides
- `observe` -- Analyze text prompt for intent and constraints
- `generate` -- Create image from text prompt
- `detect` -- Detect alignment between prompt and generated image
- `verify` -- Validate generated image against prompt requirements
- `ground` -- Anchor generated image to source prompt
- `checkpoint` -- Checkpoint before release
- `explain` -- Document generation provenance
- `audit` -- Record generation and review decision

**Trigger:** Text-to-image generation request

**Output:** Generated image with prompt alignment score and provenance trail

### 4. Cross-modal Search

**Goal:** Search across modalities to find content matching a query in any modality.

**Capabilities used:**
- `retrieve` -- Load query (text, image, or audio)
- `transform` -- Convert query to cross-modal embedding
- `search` -- Search across modality indices
- `compare` -- Rank results by cross-modal similarity
- `detect` -- Detect alignment quality of top results
- `ground` -- Anchor results to source query and modality evidence
- `explain` -- Generate search result summary with cross-modal context
- `audit` -- Record search session and results

**Trigger:** Cross-modal search request

**Output:** Ranked results across modalities with alignment scores

## Evidence Grounding for Multi-modal

Cross-modal evidence anchors must include:

1. **Source modality** -- Identification of each input modality with references
2. **Target modality** -- Identification of the output modality
3. **Alignment score** -- Cross-modal similarity or alignment metric
4. **Confidence score** -- Model confidence for the transformation
5. **Modality hash** -- Content hash for each modality artifact (provenance tracking)

## Cross-modal Trust Hierarchy

When modalities conflict, trust follows this hierarchy:

1. **Verified human input** (any modality) -- Highest trust
2. **Calibrated sensor data** (image, audio) -- High trust
3. **Aligned datasets** -- High trust for trained patterns
4. **Single-modality AI output** -- Moderate trust
5. **Cross-modal AI output** -- Lower trust (compounding uncertainty)
6. **AI-generated content** -- Lowest trust (especially video)

## Customization Guide

### Adjusting for Document Understanding

```yaml
trust_weights:
  scanned_document: 0.90       # OCR source documents
  text_input: 0.92             # Extracted text
  layout_analysis: 0.85        # Document layout models
evidence_policy:
  required_anchor_types:
    - source_modality
    - target_modality
    - page_reference            # Page and region in document
    - confidence_score
```

### Adjusting for Video Understanding

```yaml
trust_weights:
  video_input: 0.90            # Source video
  frame_extraction: 0.88       # Individual frames
  audio_track: 0.85            # Extracted audio
  subtitle_track: 0.80         # Subtitle/caption data
evidence_policy:
  required_anchor_types:
    - source_modality
    - time_segment              # Video timestamp range
    - frame_reference           # Specific frame
    - confidence_score
```

## Safety Considerations

1. **Verify cross-modal consistency** -- Claims grounded in multiple modalities are stronger
2. **Trust decreases with generation** -- Generated content is less trusted than captured content
3. **Checkpoint all modality conversions** -- Transformation introduces uncertainty
4. **Track modality provenance** -- Every output must trace back to source modalities
5. **Flag alignment failures** -- Misaligned cross-modal data should trigger review

## Related Documentation

- [Profile Schema](../../../schemas/profiles/profile_schema.yaml)
- [Vision Domain](../vision/README.md)
- [Audio Domain](../audio/README.md)
- [Capability Ontology](../../../schemas/capability_ontology.yaml)
- [OASF Comparison](../../research/analysis/OASF_comparison.md)
