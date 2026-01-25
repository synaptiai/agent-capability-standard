---
name: generate-image
description: Generate image specifications, prompts, or SVG/diagram code under constraints. Use when creating visual assets, image prompts, diagrams, or visual specifications.
argument-hint: "[subject] [style] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Create image specifications, generation prompts, or code-based visual assets (SVG, diagrams) that meet specified visual, technical, and safety constraints.

**Success criteria:**
- Output is usable for intended purpose (prompt, spec, or code)
- Visual style matches requirements
- Technical constraints satisfied (dimensions, format, colors)
- Safety and appropriateness guidelines followed

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `subject` | Yes | string | What the image should depict |
| `purpose` | No | string | How the image will be used |
| `output_type` | No | string | prompt, specification, svg, mermaid, ascii (default: specification) |
| `style` | No | object | Visual style requirements (photorealistic, illustration, diagram, etc.) |
| `constraints` | No | object | Dimensions, colors, format, forbidden elements |
| `brand_guidelines` | No | object | Brand colors, fonts, logo usage rules |

## Procedure

1) **Clarify visual requirements**: Understand the image need
   - Subject matter and key elements
   - Visual style and mood
   - Technical requirements (size, format, resolution)
   - Usage context (web, print, social media)

2) **Apply constraints**: Map requirements to output
   - Dimension and aspect ratio
   - Color palette restrictions
   - Required and forbidden elements
   - Brand guideline compliance

3) **Generate appropriate output**: Based on output_type
   - Prompt: Detailed generation prompt for AI image tools
   - Specification: Structured description for designers
   - SVG: Scalable vector code
   - Mermaid: Diagram code
   - ASCII: Text-based visual

4) **Add technical metadata**: Include specifications
   - Recommended dimensions
   - Color codes (hex, RGB)
   - Format recommendations
   - Accessibility considerations

5) **Document safety considerations**: Note content restrictions
   - Avoided inappropriate content
   - Copyright/trademark considerations
   - Representation and bias awareness

## Output Contract

Return a structured object:

```yaml
artifact:
  type: image_specification | prompt | svg | mermaid | ascii
  content: string  # The generated output
  format: string  # text, svg, mermaid, etc.
  metadata:
    subject: string
    style: string
    recommended_dimensions:
      width: integer
      height: integer
      unit: pixels | inches | cm
    color_palette: array[string]  # Hex codes
    file_format_recommendation: string
constraints_used:
  - constraint: string
    satisfied: boolean
    notes: string | null
rationale: string
alternatives_considered: array[string]
quality_signals:
  - metric: string
    value: string
technical_notes:
  - note: string
    category: dimensions | colors | format | accessibility
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
safety_notes: array[string]
next_actions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `artifact` | object | Generated image asset or specification |
| `constraints_used` | array | How each constraint was addressed |
| `rationale` | string | Explanation of visual decisions |
| `technical_notes` | array | Technical specifications |
| `confidence` | number | 0.0-1.0 confidence in output quality |
| `evidence_anchors` | array[string] | References used |
| `assumptions` | array[string] | Explicitly stated assumptions |
| `safety_notes` | array[string] | Content safety considerations |
| `next_actions` | array[string] | Suggested follow-ups |

## Examples

### Example 1: Generating a System Architecture Diagram

**Input:**
```yaml
subject: "Microservices architecture showing user service, order service, and payment service with message queue"
purpose: "Technical documentation for developer onboarding"
output_type: "mermaid"
style:
  type: "architecture_diagram"
  detail_level: "component"
constraints:
  colors: "use standard mermaid styling"
  labels: "clear, concise service names"
```

**Output:**
```yaml
artifact:
  type: mermaid
  content: |
    graph TB
        subgraph "Client Layer"
            WEB[Web Application]
            MOB[Mobile App]
        end

        subgraph "API Gateway"
            GW[API Gateway<br/>Authentication & Routing]
        end

        subgraph "Services"
            US[User Service<br/>Authentication & Profiles]
            OS[Order Service<br/>Order Management]
            PS[Payment Service<br/>Payment Processing]
            NS[Notification Service<br/>Email & Push]
        end

        subgraph "Message Queue"
            MQ[(RabbitMQ<br/>Event Bus)]
        end

        subgraph "Data Stores"
            UDB[(User DB<br/>PostgreSQL)]
            ODB[(Order DB<br/>PostgreSQL)]
            PDB[(Payment DB<br/>PostgreSQL)]
            CACHE[(Redis Cache)]
        end

        WEB --> GW
        MOB --> GW

        GW --> US
        GW --> OS
        GW --> PS

        US --> UDB
        US --> CACHE
        OS --> ODB
        OS --> MQ
        PS --> PDB
        PS --> MQ

        MQ --> NS
        MQ --> OS

        classDef service fill:#e1f5fe,stroke:#01579b
        classDef database fill:#fff3e0,stroke:#e65100
        classDef queue fill:#f3e5f5,stroke:#7b1fa2
        classDef gateway fill:#e8f5e9,stroke:#2e7d32

        class US,OS,PS,NS service
        class UDB,ODB,PDB,CACHE database
        class MQ queue
        class GW gateway
  format: mermaid
  metadata:
    subject: "Microservices architecture"
    style: "component-level architecture diagram"
    recommended_dimensions:
      width: 1200
      height: 800
      unit: pixels
    color_palette:
      - "#e1f5fe"  # Services
      - "#fff3e0"  # Databases
      - "#f3e5f5"  # Message Queue
      - "#e8f5e9"  # Gateway
    file_format_recommendation: "PNG or SVG for documentation"
constraints_used:
  - constraint: "use standard mermaid styling"
    satisfied: true
    notes: "Used classDef for consistent color coding"
  - constraint: "clear, concise service names"
    satisfied: true
    notes: "Each service has name and brief purpose"
rationale: "Top-to-bottom flow shows request path clearly. Grouped components by layer for readability. Color coding distinguishes component types. Included both sync (arrows) and async (via MQ) communication patterns."
alternatives_considered:
  - "Left-to-right layout - rejected for better fit in docs"
  - "Sequence diagram - rejected, this shows structure not flow"
  - "C4 model notation - considered but kept simpler for onboarding"
quality_signals:
  - metric: "Readability"
    value: "high - clear groupings and labels"
  - metric: "Completeness"
    value: "covers all specified services plus supporting infrastructure"
  - metric: "Renderability"
    value: "tested valid mermaid syntax"
technical_notes:
  - note: "Render at minimum 1200px width for legibility"
    category: dimensions
  - note: "Colors are accessible with sufficient contrast"
    category: accessibility
  - note: "Export as SVG for scalability in documentation"
    category: format
confidence: 0.9
evidence_anchors:
  - "input:subject specification"
assumptions:
  - "Services communicate via both sync HTTP and async messaging"
  - "Each service has dedicated database"
  - "Redis is shared cache layer"
  - "RabbitMQ is the message broker"
safety_notes:
  - "No sensitive endpoints or credentials depicted"
  - "Generic service names used, not production URLs"
  - "Architecture represents typical pattern, not specific client data"
next_actions:
  - "Add sequence diagrams for specific flows (user registration, order placement)"
  - "Create detailed API documentation for each service"
  - "Add deployment diagram showing infrastructure"
```

**Evidence pattern:** Requirements analysis + mermaid syntax generation + style application

### Example 2: Generating an AI Image Prompt

**Input:**
```yaml
subject: "Professional headshot placeholder for user profile"
purpose: "Default avatar for business application"
output_type: "prompt"
style:
  type: "illustration"
  mood: "friendly, professional"
  aesthetic: "modern, minimal"
constraints:
  colors: "blue and gray tones"
  forbidden: "identifiable faces, gender-specific features"
  aspect_ratio: "1:1"
```

**Output:**
```yaml
artifact:
  type: prompt
  content: |
    Create a minimal, modern illustration of an abstract professional avatar.

    Style: Clean vector illustration, flat design, geometric shapes

    Subject: Abstract human silhouette, gender-neutral, using simple geometric forms.
    Head represented as a circle, shoulders as gentle curves. No facial features.

    Colors: Primary fill in soft blue (#4A90D9), outline/accent in warm gray (#6B7280).
    Background: Light gray (#F3F4F6) or transparent.

    Composition: Centered, head and shoulders only, square 1:1 aspect ratio.
    Generous negative space around the figure.

    Mood: Approachable, professional, inclusive. Suitable for business context.

    Avoid: Detailed facial features, gender indicators, realistic human proportions,
    busy backgrounds, harsh colors, cartoonish style.

    Technical: Vector-style output suitable for scaling. Clean edges.
    Export ready for both light and dark UI backgrounds.
  format: text
  metadata:
    subject: "Abstract professional avatar"
    style: "minimal vector illustration"
    recommended_dimensions:
      width: 400
      height: 400
      unit: pixels
    color_palette:
      - "#4A90D9"  # Primary blue
      - "#6B7280"  # Gray accent
      - "#F3F4F6"  # Light background
    file_format_recommendation: "SVG or PNG with transparency"
constraints_used:
  - constraint: "blue and gray tones"
    satisfied: true
    notes: "Specified exact hex codes within constraint"
  - constraint: "forbidden: identifiable faces"
    satisfied: true
    notes: "Prompt explicitly requests no facial features"
  - constraint: "forbidden: gender-specific features"
    satisfied: true
    notes: "Abstract, geometric representation specified"
  - constraint: "aspect_ratio: 1:1"
    satisfied: true
    notes: "Square composition specified"
rationale: "Abstract geometric approach ensures inclusivity and avoids identity-specific representation. Minimal style fits modern UI aesthetics. Specific color codes ensure brand consistency."
alternatives_considered:
  - "Photorealistic placeholder - rejected per constraints"
  - "Initials-based avatar - different use case"
  - "Animal/object avatar - less professional context fit"
quality_signals:
  - metric: "Prompt specificity"
    value: "high - includes style, colors, avoid list"
  - metric: "Reproducibility"
    value: "high - specific enough for consistent results"
  - metric: "Safety"
    value: "high - explicitly avoids identity-specific content"
technical_notes:
  - note: "Request vector output for scalability"
    category: format
  - note: "Test on both light and dark backgrounds"
    category: accessibility
  - note: "400x400 is standard avatar size, scale as needed"
    category: dimensions
confidence: 0.85
evidence_anchors:
  - "input:style and constraints"
assumptions:
  - "Target is AI image generation tool (DALL-E, Midjourney, etc.)"
  - "Business/professional context"
  - "Need for inclusive, non-specific representation"
safety_notes:
  - "Explicitly avoided identifiable human features"
  - "Gender-neutral design ensures inclusivity"
  - "No copyrighted or trademarked elements"
  - "Suitable for professional/business use"
next_actions:
  - "Generate test images using prompt"
  - "Iterate on colors if brand guidelines change"
  - "Create variants for different contexts (error state, loading)"
```

**Evidence pattern:** Requirements translation + constraint mapping + prompt engineering

## Verification

- [ ] Output type matches specification
- [ ] All constraints reflected in output
- [ ] Technical metadata complete
- [ ] Safety considerations documented
- [ ] Output is syntactically valid (for code outputs)

**Verification tools:** Read (for reference materials)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Never generate content depicting real individuals without consent
- Avoid stereotypical or biased representations
- Do not generate trademarked/copyrighted content
- Flag requests for potentially harmful imagery
- Consider accessibility in visual designs
- Document representation choices and alternatives

## Composition Patterns

**Commonly follows:**
- `retrieve` - to gather brand guidelines or references
- `search` - to find style examples
- `identify-entity` - to clarify visual subjects

**Commonly precedes:**
- `verify` - to check technical validity
- `critique` - to review visual design
- `transform` - to convert between formats

**Anti-patterns:**
- Never generate identifying imagery without explicit consent
- Avoid generating complex images when diagrams suffice

**Workflow references:**
- See `workflow_catalog.json#visual_asset_creation` for design workflows
- See `workflow_catalog.json#documentation_with_diagrams` for technical docs
