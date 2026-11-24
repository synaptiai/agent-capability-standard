# Audio Domain

This document describes how to use the Grounded Agency framework for audio processing and acoustic analysis environments.

## Overview

The audio domain profile is calibrated for environments where:
- **Temporal evidence is primary** -- Detections and classifications are anchored to time segments
- **Signal quality varies** -- Studio recordings vs. phone audio have very different trust levels
- **Speaker privacy matters** -- Speaker identification requires strict checkpoint policies
- **Synthesis requires oversight** -- AI-generated audio needs review before distribution

This profile maps to [OASF Category 3 (Audio)](https://schema.oasf.outshift.com/skill_categories) (see also `schemas/interop/oasf_mapping.yaml` for the local mapping), covering audio classification, speech recognition, speaker identification, and audio synthesis.

The profile takes effect where a host, a safety layer or the validator applies it (Standard 1.2.0 [§5.21](../../../spec/STANDARD-v1.2.0.md#521-domain-profiles)): applied, its rules raise the flags of the steps and calls they name, and only tighten. A workflow's `profile` field applies nothing. See [Status of Domain Profiles](../README.md#status-of-domain-profiles) for which components apply it, its grounding policy (`require_grounding`) and minimum confidence included.

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

*Sorted by source category; see profile YAML for exact grouping.*

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

The profile requires a checkpoint before each step or call that:
- Modifies source audio (`mutate`)
- Writes a final transcription or synthesized audio out (`persist`)
- Carries high risk, such as a large batch

Identifying a speaker (`classify`) changes no state, so the profile sets no
checkpoint for it; a deployment that wants one adds `classify: always`. The
profile states it as checkpoint rules on capabilities ([§5.21.3](../../../spec/STANDARD-v1.2.0.md#5213-effect-on-steps-and-calls); a `checkpoint` step is exempt):

```yaml
checkpoint_policy:
  # Standard v1.2 §5.21: capability ids or "*". From 1.0.0's labels:
  # before_audio_modification -> mutate; before_transcription_output and
  # before_synthesis -> persist; before_speaker_identification -> none
  # (classifying changes no state); before_batch_processing (high_risk) -> "*".
  mutate: always
  persist: always
  "*": high_risk
```

## Capability Usage

The 36 atomic capabilities apply to audio through domain parameterization.
Each output's `evidence_anchors` are evidence anchors (Standard 1.2.0 §6.5):
a `kind`, which the profile's `required_anchor_types` count, and a `ref` in
the forms of the [modality guide](../../guides/MODALITY_HANDLING.md#41-evidence-anchor-types-by-modality);
an `acs:` ref names a value the step was given, such as the text to speak
(§5.20). Other data, such as signal quality, stay out of the anchors.

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
      - kind: sensor
        ref: "audio:mic://room-3/stream-2024-01-15T10:32:00Z:segment:12400-13100"
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
    signal_quality:
      snr_db: 32.5
    evidence_anchors:
      - kind: file
        ref: "s3://corpus/sample_042.wav"
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
    confidence: 0.91
    signal_quality:
      snr_db: 28.0
    evidence_anchors:
      - kind: file
        ref: "recording://meeting-2024-01-15.wav"
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
      - kind: record
        ref: "acs:text"
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
  required_anchor_types:       # Anchor kinds (Standard 1.2.0 §6.5)
    - file                     # The source audio
    - x-spectral_analysis      # A vendor kind: spectral evidence
  require_grounding: [detect, classify]
```

## Safety Considerations

1. **Always ground** detections to specific time segments
2. **Never trust synthesized audio** at the same level as recordings
3. **Gate speaker identification** -- Privacy implications: the profile sets no checkpoint for it, so add `classify: always`, or list `classify` in `block_autonomous` to have a person approve it, where identifying a speaker needs either
4. **Maintain provenance** -- Track from capture through all processing stages
5. **Assess signal quality** -- Low SNR audio requires lower confidence thresholds

## Related Documentation

- [Profile Schema](../../../schemas/profiles/profile_schema.yaml)
- [Capability Ontology](../../../schemas/capability_ontology.yaml)
- [OASF Comparison](../../research/analysis/OASF_comparison.md)
