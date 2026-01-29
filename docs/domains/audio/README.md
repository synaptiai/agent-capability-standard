# Audio Domain

This document describes how to use the Grounded Agency framework for audio processing and acoustic analysis environments.

## Overview

The audio domain profile is calibrated for environments where:
- **Temporal evidence is primary** -- Detections and classifications are anchored to time segments
- **Signal quality varies** -- Studio recordings vs. phone audio have very different trust levels
- **Speaker privacy matters** -- Speaker identification requires strict checkpoint policies
- **Synthesis requires oversight** -- AI-generated audio needs review before distribution

This profile maps to [OASF Category 3 (Audio)](https://schema.oasf.outshift.com/skill_categories), covering audio classification, speech recognition, speaker identification, and audio synthesis.

## Domain Profile

**Profile location:** `schemas/profiles/audio.yaml`

### Trust Weights

Audio environments trust calibrated and professional sources over processed or synthesized content:

| Source | Trust Weight | Rationale |
|--------|-------------|-----------|
| Studio Recording | 0.95 | Professional studio, controlled conditions |
| Reference Audio | 0.94 | Verified reference samples |
| Calibrated Microphone | 0.93 | Measurement-grade microphones |
| Digital Recording | 0.88 | Standard digital audio |
| Enhanced Audio | 0.82 | Noise-reduced or enhanced |
| Conference Audio | 0.80 | Meeting/conference recordings |
| Transcription | 0.78 | ASR-generated transcripts |
| Ambient Microphone | 0.78 | Environmental microphones |
| Phone Audio | 0.75 | Telephone/VoIP (lossy) |
| Crowd Annotation | 0.70 | Crowdsourced audio labels |
| Model Prediction | 0.62 | Other audio model predictions |
| Synthesized Audio | 0.55 | AI-generated or TTS audio |
| Ground Truth Transcript | 0.95 | Verified human transcripts |
| Expert Annotation | 0.90 | Linguist/domain expert annotations |

### Risk Thresholds

```yaml
auto_approve: low       # Only low-risk audio analysis auto-approved
require_review: medium  # Medium+ requires human review
require_human: high     # High-risk audio decisions require human
block_autonomous:
  - mutate              # Never autonomously modify source audio
  - send                # Never autonomously distribute audio content
```

### Checkpoint Policy

Audio workflows require checkpoints before any action that:
- Modifies source audio
- Produces a final transcription
- Generates or synthesizes audio
- Identifies speakers

## Capability Usage

The 36 atomic capabilities apply to audio through domain parameterization:

### Detection

```yaml
detect:
  domain: sound_event
  input:
    audio_ref: "mic://room-3/stream-2024-01-15T10:32:00Z"
    model: "audio-event-detector-v2"
  output:
    detections:
      - label: "glass_breaking"
        time_segment: [12.4, 13.1]
        confidence: 0.88
    evidence_anchors:
      - type: audio_reference
        ref: "mic://room-3/stream-2024-01-15T10:32:00Z"
      - type: time_segment
        start: 12.4
        end: 13.1
```

### Classification

```yaml
classify:
  domain: audio_genre
  input:
    audio_ref: "s3://corpus/sample_042.wav"
    taxonomy: ["speech", "music", "noise", "silence"]
  output:
    label: "speech"
    confidence: 0.94
    evidence_anchors:
      - type: audio_reference
        ref: "s3://corpus/sample_042.wav"
      - type: signal_quality
        snr_db: 32.5
```

### Transformation (Speech-to-Text)

```yaml
transform:
  domain: transcription
  input:
    source: "recording://meeting-2024-01-15.wav"
    source_format: audio
    target_format: text
    language: "en-US"
  output:
    transcript: "The quarterly results show..."
    word_timestamps: [...]
    evidence_anchors:
      - type: audio_reference
        ref: "recording://meeting-2024-01-15.wav"
      - type: signal_quality
        snr_db: 28.0
      - type: confidence_score
        value: 0.91
```

### Generation (Text-to-Speech)

```yaml
generate:
  domain: audio
  input:
    text: "The system is operating normally."
    voice: "neutral-professional"
    format: "wav"
  output:
    audio_ref: "generated://tts-uuid-def456.wav"
    evidence_anchors:
      - type: source_modality
        ref: "text input"
      - type: modality_hash
        value: "sha256:..."
```

## Available Workflows

> **Note:** These workflows are proposed and pending inclusion in the workflow catalog. See the [workflow catalog](../../../schemas/workflow_catalog.yaml) for currently available patterns.

### 1. Speech Recognition Pipeline

**Goal:** Transcribe audio to text with temporal evidence grounding.

**Capabilities used:**
- `retrieve` -- Load audio and language model configuration
- `observe` -- Assess audio signal quality
- `transform` -- Convert audio to text transcription
- `detect` -- Detect speaker changes and non-speech events
- `measure` -- Quantify transcription confidence and signal quality
- `ground` -- Anchor transcript segments to audio time ranges
- `verify` -- Validate transcription against quality thresholds
- `checkpoint` -- Checkpoint before final output
- `audit` -- Record transcription decision

**Trigger:** Audio submission or stream start

**Output:** Timestamped transcript with confidence scores and signal quality metrics

### 2. Audio Classification Pipeline

**Goal:** Classify audio segments into predefined categories (speech, music, noise, events).

**Capabilities used:**
- `retrieve` -- Load audio and classification taxonomy
- `observe` -- Inspect audio signal characteristics
- `detect` -- Detect sound events and segment boundaries
- `classify` -- Assign category labels with confidence
- `ground` -- Anchor classifications to time segments
- `explain` -- Generate classification report
- `audit` -- Record classification results

**Trigger:** Audio submission or continuous monitoring

**Output:** Classification labels with time segments and confidence scores

### 3. Speaker Verification

**Goal:** Verify speaker identity with privacy-aware checkpoints.

**Capabilities used:**
- `retrieve` -- Load reference voiceprints
- `observe` -- Capture audio features
- `detect` -- Detect speech segments
- `compare` -- Compare against reference voiceprints
- `classify` -- Determine speaker identity match
- `ground` -- Anchor verification to acoustic evidence
- `checkpoint` -- Checkpoint before identity disclosure
- `verify` -- Validate confidence against threshold
- `audit` -- Record verification decision

**Trigger:** Authentication request

**Output:** Verification result with confidence and privacy audit trail

### 4. Audio Quality Assessment

**Goal:** Assess audio quality and recommend processing actions.

**Capabilities used:**
- `retrieve` -- Load quality standards and reference signals
- `observe` -- Capture audio signal properties
- `measure` -- Quantify signal-to-noise ratio and quality metrics
- `detect` -- Identify noise, clipping, and artifacts
- `compare` -- Compare against quality thresholds
- `classify` -- Recommend quality disposition
- `explain` -- Generate quality assessment report
- `audit` -- Record assessment results

**Trigger:** Audio ingestion or quality check request

**Output:** Quality assessment with metrics and processing recommendations

## Evidence Grounding for Audio

Audio evidence anchors must include:

1. **Audio reference** -- URI or hash of the source audio
2. **Time segment** -- Start/end timestamps for segment-specific claims
3. **Confidence score** -- Model confidence for each detection/classification
4. **Signal quality** -- SNR or quality metric for the source audio

## Customization Guide

### Adjusting for Call Center Analysis

```yaml
trust_weights:
  phone_audio: 0.82           # Primary input for call centers
  transcription: 0.80         # ASR critical for this domain
  agent_annotation: 0.85      # Call center agent notes
evidence_policy:
  minimum_confidence: 0.75    # Lower threshold for noisy phone audio
```

### Adjusting for Music Analysis

```yaml
trust_weights:
  studio_recording: 0.96      # Primary source
  reference_audio: 0.95       # Reference tracks
  expert_annotation: 0.92     # Musicologist annotations
evidence_policy:
  required_anchor_types:
    - audio_reference
    - time_segment
    - frequency_analysis       # Spectral evidence
    - confidence_score
```

## Safety Considerations

1. **Always ground** detections to specific time segments
2. **Never trust synthesized audio** at the same level as recordings
3. **Checkpoint before speaker identification** -- Privacy implications
4. **Maintain provenance** -- Track from capture through all processing stages
5. **Assess signal quality** -- Low SNR audio requires lower confidence thresholds

## Related Documentation

- [Profile Schema](../../../schemas/profiles/profile_schema.yaml)
- [Capability Ontology](../../../schemas/capability_ontology.yaml)
- [OASF Comparison](../../research/analysis/OASF_comparison.md)
