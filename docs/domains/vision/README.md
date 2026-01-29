# Vision Domain

This document describes how to use the Grounded Agency framework for computer vision and image processing environments.

## Overview

The vision domain profile is calibrated for environments where:
- **Visual evidence is primary** -- Detections and classifications are anchored to image regions
- **Spatial grounding matters** -- Bounding boxes and pixel evidence provide accountability
- **Source quality varies widely** -- Calibrated cameras vs. generated imagery have very different trust levels
- **Generation requires oversight** -- AI-generated images need checkpoint-before-create policies

This profile maps to [OASF Category 2 (Computer Vision)](https://schema.oasf.outshift.com/skill_categories) (see also `schemas/interop/oasf_mapping.yaml` for the local mapping), covering image segmentation, object detection, image generation, and visual transformations.

## Domain Profile

**Profile location:** `schemas/profiles/vision.yaml`

### Trust Weights

Vision environments trust calibrated capture systems over processed or synthetic sources:

| Source | Trust Weight | Rationale |
|--------|-------------|-----------|
| Calibrated Camera | 0.95 | Fixed, calibrated industrial/scientific cameras |
| LiDAR Scan | 0.94 | High geometric accuracy point clouds |
| Stereo Camera | 0.93 | Depth-enabled stereo vision |
| Satellite Imagery | 0.92 | Verified satellite/aerial providers |
| Screen Capture | 0.90 | Screenshots with known provenance |
| Digital Camera | 0.88 | Standard digital photography |
| Annotated Image | 0.85 | Human-annotated image data |
| Smartphone Camera | 0.82 | Mobile device cameras |
| Crowd Annotation | 0.72 | Crowdsourced annotations |
| Augmented Image | 0.70 | Augmented/transformed training data |
| Model Prediction | 0.65 | Predictions from other ML models |
| Synthetic Image | 0.60 | AI-generated or synthetic imagery |
| Ground Truth Label | 0.95 | Verified ground truth annotations |
| Expert Annotation | 0.90 | Domain expert visual annotations |

*Sorted by source category; see profile YAML for exact grouping.*

### Risk Thresholds

```yaml
auto_approve: low       # Only low-risk visual analysis auto-approved
require_review: medium  # Medium+ requires human review
require_human: high     # High-risk visual decisions require human
block_autonomous:
  - mutate              # Never autonomously modify source imagery
  - send                # Never autonomously distribute visual content
```

### Checkpoint Policy

Vision workflows require checkpoints before any action that:
- Modifies source imagery
- Produces a final classification output
- Generates new images
- Processes large batches

## Capability Usage

The 36 atomic capabilities apply to vision through domain parameterization:

### Detection

```yaml
detect:
  domain: object
  input:
    image_ref: "camera://line-4/frame-12847"
    model: "yolov8-custom"
  output:
    detections:
      - label: "defect_crack"
        bounding_box: [120, 45, 180, 90]
        confidence: 0.92
    evidence_anchors:
      - type: image_reference
        ref: "camera://line-4/frame-12847"
      - type: bounding_box
        coordinates: [120, 45, 180, 90]
```

### Classification

```yaml
classify:
  domain: scene
  input:
    image_ref: "s3://dataset/img_0042.jpg"
    taxonomy: ["indoor", "outdoor", "aerial"]
  output:
    label: "outdoor"
    confidence: 0.89
    evidence_anchors:
      - type: image_reference
        ref: "s3://dataset/img_0042.jpg"
      - type: confidence_score
        value: 0.89
```

### Generation

```yaml
generate:
  domain: image
  input:
    prompt: "Industrial component schematic, technical drawing style"
    constraints:
      resolution: "1024x1024"
      style: "technical"
  output:
    image_ref: "generated://uuid-abc123"
    evidence_anchors:
      - type: source_modality
        ref: "text prompt"
      - type: modality_hash
        value: "sha256:..."
```

### Transformation

```yaml
transform:
  domain: image
  input:
    source: "camera://raw/frame-001.raw"
    operations: ["denoise", "normalize", "resize"]
  output:
    image_ref: "processed://frame-001.png"
    evidence_anchors:
      - type: image_reference
        ref: "camera://raw/frame-001.raw"
      - type: pixel_evidence
        operations_applied: ["denoise", "normalize", "resize"]
```

## Available Workflows

> **Note:** These workflows are proposed and pending inclusion in the workflow catalog. See the [workflow catalog](../../../schemas/workflow_catalog.yaml) for currently available patterns.

### 1. Image Classification Pipeline

**Goal:** Classify images into predefined categories with evidence grounding.

**Capabilities used:**
- `retrieve` -- Load image and reference taxonomy
- `observe` -- Inspect image features
- `detect` -- Detect objects and regions of interest
- `classify` -- Assign category labels with confidence
- `ground` -- Anchor classification to visual evidence
- `explain` -- Generate classification report
- `checkpoint` -- Checkpoint before final output
- `audit` -- Record classification decision

**Trigger:** Image submission or batch schedule

**Output:** Classification label with confidence and visual evidence anchors

### 2. Object Detection Pipeline

**Goal:** Detect and localize objects within images with bounding box evidence.

**Capabilities used:**
- `retrieve` -- Load image and detection model
- `detect` -- Detect objects with bounding boxes
- `classify` -- Classify each detected object
- `measure` -- Quantify detection confidence
- `ground` -- Anchor detections to image regions
- `verify` -- Validate detections against thresholds
- `explain` -- Generate detection report
- `audit` -- Record detection results

**Trigger:** Image or video frame submission

**Output:** Detected objects with bounding boxes, labels, and confidence scores

### 3. Visual Quality Inspection

**Goal:** Inspect visual inputs for defects or quality deviations.

**Capabilities used:**
- `retrieve` -- Load reference specifications
- `observe` -- Capture inspection image
- `detect` -- Identify visual defects
- `compare` -- Compare against quality standards
- `classify` -- Recommend disposition (pass/fail/review)
- `ground` -- Anchor findings to image regions
- `checkpoint` -- Checkpoint before disposition
- `explain` -- Generate inspection report
- `audit` -- Record inspection cycle

**Trigger:** Batch completion or continuous inspection

**Output:** Disposition recommendation with defect evidence

### 4. Image Generation Review

**Goal:** Generate images from prompts with human review checkpoints.

**Capabilities used:**
- `retrieve` -- Load generation constraints and style guides
- `generate` -- Create image from prompt
- `verify` -- Check generated image against constraints
- `ground` -- Anchor generated image to source prompt
- `checkpoint` -- Checkpoint before release
- `explain` -- Document generation provenance
- `audit` -- Record generation and review decision

**Trigger:** Generation request

**Output:** Generated image with provenance trail and review status

## Evidence Grounding for Vision

Visual evidence anchors must include:

1. **Image reference** -- URI or hash of the source image
2. **Bounding box** -- Spatial coordinates for region-specific claims
3. **Confidence score** -- Model confidence for each detection/classification
4. **Pixel evidence** -- Segmentation masks or attention maps when applicable

## Customization Guide

### Adjusting for Medical Imaging

```yaml
trust_weights:
  dicom_source: 0.96        # DICOM-compliant medical imaging
  calibrated_camera: 0.95
  expert_annotation: 0.94   # Radiologist annotations
```

### Adjusting for Autonomous Vehicles

```yaml
trust_weights:
  lidar_scan: 0.96          # Primary sensor for self-driving
  calibrated_camera: 0.94
  radar_return: 0.92
checkpoint_policy:
  before_classification_output: always  # Safety-critical
  before_image_modification: always
```

## Safety Considerations

1. **Always ground** detections to specific image regions with bounding boxes
2. **Never trust synthetic images** at the same level as captured images
3. **Checkpoint before generation** -- AI-generated images should be reviewed
4. **Maintain provenance** -- Track the full pipeline from capture to classification
5. **Flag low confidence** -- Detections below `minimum_confidence` (0.80) require review

## Related Documentation

- [Profile Schema](../../../schemas/profiles/profile_schema.yaml)
- [Capability Ontology](../../../schemas/capability_ontology.yaml)
- [OASF Comparison](../../research/analysis/OASF_comparison.md)
