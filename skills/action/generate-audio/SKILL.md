---
name: generate-audio
description: Generate audio specifications, scripts, or plans for audio content under constraints. Use when creating podcast scripts, voiceover specifications, sound design briefs, or audio content plans.
argument-hint: "[content_type] [purpose] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Create audio content specifications, scripts, or production plans that meet specified requirements for voice, music, sound design, or other audio assets.

**Success criteria:**
- Audio specification is complete and actionable
- Tone and style appropriate for purpose
- Technical requirements specified
- Production guidance clear and practical

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `content_type` | Yes | string | Type: voiceover, podcast, music, sound_effect, notification |
| `purpose` | Yes | string | How the audio will be used |
| `constraints` | No | object | Duration, tone, format, technical specs |
| `voice_requirements` | No | object | Voice characteristics if applicable |
| `context` | No | string\|object | Background for content creation |
| `script_content` | No | string | Text to be spoken if voiceover |

## Procedure

1) **Clarify audio requirements**: Understand the need
   - Content type and format
   - Target audience and context
   - Technical specifications (format, bitrate, duration)
   - Emotional tone and energy level

2) **Develop content specification**: Based on content type
   - Voiceover: Script with direction notes
   - Podcast: Outline, segments, transitions
   - Music: Mood, tempo, instrumentation
   - Sound effects: Description, trigger, duration

3) **Add production notes**: Technical and creative guidance
   - Recording environment recommendations
   - Post-production needs (EQ, compression, effects)
   - File format and delivery specifications

4) **Include timing guidance**: Pacing and duration
   - Target duration for each section
   - Pacing notes (fast, measured, dramatic pauses)
   - Sync points if accompanying video

5) **Document accessibility**: Audio accessibility considerations
   - Transcript requirements
   - Captioning sync points
   - Audio description needs if accompanying visual

## Output Contract

Return a structured object:

```yaml
artifact:
  type: audio_specification | script | music_brief | sound_design
  content: string  # The specification or script
  format: string  # markdown, plain, etc.
  metadata:
    content_type: string
    duration:
      target: string
      minimum: string
      maximum: string
    format_specs:
      file_format: string
      sample_rate: string
      bit_depth: string
      channels: string
voice_specification:  # If applicable
  gender: string | null
  age_range: string
  accent: string
  tone: string
  pacing: string
  energy: string
production_notes:
  - category: recording | post_production | delivery
    note: string
constraints_used:
  - constraint: string
    satisfied: boolean
    notes: string | null
rationale: string
quality_signals:
  - metric: string
    value: string
accessibility_notes:
  transcript_required: boolean
  caption_sync_points: array[string] | null
  audio_description: string | null
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
safety_notes: array[string]
next_actions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `artifact` | object | Generated audio specification |
| `voice_specification` | object | Voice talent requirements |
| `production_notes` | array | Recording and production guidance |
| `constraints_used` | array | How constraints were addressed |
| `accessibility_notes` | object | Accessibility requirements |
| `confidence` | number | 0.0-1.0 confidence in specification quality |
| `evidence_anchors` | array[string] | References used |
| `assumptions` | array[string] | Explicitly stated assumptions |
| `safety_notes` | array[string] | Content safety considerations |
| `next_actions` | array[string] | Production next steps |

## Examples

### Example 1: Generating Voiceover Script Specification

**Input:**
```yaml
content_type: "voiceover"
purpose: "Product tutorial video introduction"
constraints:
  duration: "30-45 seconds"
  tone: "friendly, professional, encouraging"
  format: "WAV, 48kHz, 24-bit"
voice_requirements:
  energy: "medium-high"
  style: "conversational but clear"
script_content: "Welcome to our quick start guide. In the next few minutes, you'll learn everything you need to get started with our platform."
context:
  product: "SaaS project management tool"
  audience: "New users, business professionals"
  video_style: "Screen recording with animated highlights"
```

**Output:**
```yaml
artifact:
  type: script
  content: |
    # Tutorial Introduction Voiceover Script

    ## Context
    - Video Type: Product tutorial introduction
    - Placement: Opening 30-45 seconds of tutorial video
    - Visual: Animated logo intro, then screen recording begins

    ---

    ## Script

    [WARM, WELCOMING TONE - smile in voice]

    "Welcome to your quick start guide!"

    [BRIEF PAUSE - 0.5 sec]

    [ENCOURAGING, SLIGHTLY UPBEAT]

    "In just the next few minutes, you'll learn everything you need to get started
    with [Product Name] — and discover how easy it is to organize your projects
    and keep your team on track."

    [CONFIDENT, REASSURING]

    "Let's dive in."

    [PAUSE - 1 sec before video content begins]

    ---

    ## Director Notes

    **Pacing:** Measured but energetic. Not rushed, but maintains momentum.
    Average 3 words per second for clarity.

    **Emphasis words:** "quick" "everything" "easy" "dive in"

    **Energy arc:** Start warm -> build slight enthusiasm -> land with confidence

    **Avoid:** Sounding robotic, condescending, or overly salesy

    **Sync point:** "Let's dive in" should complete ~1 second before
    screen recording begins
  format: markdown
  metadata:
    content_type: voiceover
    duration:
      target: "35 seconds"
      minimum: "30 seconds"
      maximum: "45 seconds"
    format_specs:
      file_format: "WAV"
      sample_rate: "48kHz"
      bit_depth: "24-bit"
      channels: "mono"
voice_specification:
  gender: "neutral preference"
  age_range: "28-45"
  accent: "neutral North American or British"
  tone: "friendly, professional, encouraging"
  pacing: "measured, approximately 150 WPM"
  energy: "medium-high, conversational"
production_notes:
  - category: recording
    note: "Record in treated space - minimal room reverb"
  - category: recording
    note: "Record 3 takes minimum with varying energy levels"
  - category: recording
    note: "Capture room tone for 10 seconds for editing"
  - category: post_production
    note: "Light compression (2:1 ratio) for consistency"
  - category: post_production
    note: "De-ess if necessary, preserve natural sibilance"
  - category: post_production
    note: "Normalize to -3dB peak, -16 LUFS integrated"
  - category: delivery
    note: "Deliver as single WAV file plus project file if editing needed"
  - category: delivery
    note: "Include alternate takes as separate files"
constraints_used:
  - constraint: "duration: 30-45 seconds"
    satisfied: true
    notes: "Script times to approximately 35 seconds at natural pace"
  - constraint: "tone: friendly, professional, encouraging"
    satisfied: true
    notes: "Direction notes emphasize warmth and encouragement throughout"
  - constraint: "format: WAV, 48kHz, 24-bit"
    satisfied: true
    notes: "Specified in format_specs"
rationale: "Expanded minimal script to include emotional direction and pacing. Added specific guidance for voice talent and production team. Structure supports both professional VO talent and internal recording."
quality_signals:
  - metric: "Speakability"
    value: "high - natural phrasing, no tongue-twisters"
  - metric: "Direction clarity"
    value: "high - specific emotional and technical guidance"
  - metric: "Flexibility"
    value: "medium - structured but allows interpretation"
accessibility_notes:
  transcript_required: true
  caption_sync_points:
    - "0:00 - Welcome greeting"
    - "0:05 - Tutorial promise"
    - "0:25 - Call to action"
  audio_description: "Not required - voiceover accompanies visual content"
confidence: 0.85
evidence_anchors:
  - "input:script_content"
  - "input:context"
assumptions:
  - "Professional voice talent or experienced internal reader"
  - "Video editor will handle final sync"
  - "Target platform supports WAV or will convert"
safety_notes:
  - "Script contains no sensitive product information"
  - "No claims that require legal review"
  - "Inclusive language used throughout"
  - "No regional idioms that may not translate"
next_actions:
  - "Review script with product team for accuracy"
  - "Cast voice talent or identify internal reader"
  - "Schedule recording session"
  - "Prepare visual timing marks for sync"
```

**Evidence pattern:** Script expansion + production specification + timing calculation

## Verification

- [ ] Duration estimate within constraints
- [ ] All direction notes clear and actionable
- [ ] Technical specs complete
- [ ] Script is speakable (no awkward phrasing)
- [ ] Accessibility requirements documented

**Verification tools:** Read (for context materials)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not create audio that could deceive (fake voices of real people)
- Avoid content that requires legal claims review without flagging
- Consider cultural sensitivity in voice and music choices
- Ensure accessibility options are specified
- Flag copyrighted music or audio references

## Composition Patterns

**Commonly follows:**
- `generate-text` - to create scripts
- `retrieve` - to gather brand guidelines
- `summarize` - to condense content for audio

**Commonly precedes:**
- `verify` - to check timing and format
- `critique` - to review content quality
- `generate-plan` - to plan production workflow

**Anti-patterns:**
- Never generate specifications for voice cloning of real individuals
- Avoid copyrighted music without proper licensing path

**Workflow references:**
- See `workflow_catalog.json#content_production` for media workflows
- See `workflow_catalog.json#tutorial_creation` for educational content
