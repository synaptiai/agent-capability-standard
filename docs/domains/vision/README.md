# Vision Domain

This document describes how to use the Grounded Agency framework for computer vision and image processing environments.

## Overview

The vision domain profile is calibrated for environments where:
- **Visual evidence is primary** -- Detections and classifications are anchored to image regions
- **Spatial grounding matters** -- Bounding boxes and pixel evidence provide accountability
- **Source quality varies widely** -- Calibrated cameras vs. generated imagery have very different trust levels
- **Generation requires oversight** -- AI-generated images need checkpoint-before-create policies

This profile maps to [OASF Category 2 (Computer Vision)](https://schema.oasf.outshift.com/skill_categories), covering image segmentation, object detection, image generation, and visual transformations.

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
