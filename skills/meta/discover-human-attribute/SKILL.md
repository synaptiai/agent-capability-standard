---
name: discover-human-attribute
description: Discover human attribute patterns (skills, behaviors, preferences) from evidence while respecting privacy and avoiding sensitive inferences. Use when analyzing work patterns, skill distributions, or team capabilities.
argument-hint: "[data_source] [attribute_types] [aggregation_level]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Discover patterns in human attributes (skills, work styles, collaboration patterns) from behavioral evidence while maintaining strict privacy protections and avoiding inferences about protected characteristics.

**Success criteria:**
- Attributes discovered are job-relevant and actionable
- Individual privacy is protected through aggregation
- No inferences about protected characteristics
- Findings are grounded in observable behavior

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `data_source` | Yes | string\|object | Data to analyze (work artifacts, collaboration logs) |
| `attribute_types` | No | array[string] | Types to discover (skills, work_patterns, collaboration_style) |
| `aggregation_level` | No | string | team, department, organization (default: team) |
| `time_range` | No | object | Period to analyze |
| `privacy_threshold` | No | integer | Minimum group size for reporting (default: 5) |

## Procedure

1) **Validate scope and ethics**: Ensure analysis is appropriate
   - Confirm data access is authorized
   - Verify purpose is legitimate (skill development, team planning)
   - Set privacy thresholds
   - Exclude protected characteristics from analysis

2) **Identify observable evidence**: Gather behavioral signals
   - Work artifacts (code, documents, designs)
   - Collaboration patterns (reviews, meetings, communications)
   - Tool usage and preferences
   - Project contributions

3) **Extract attribute signals**: Map evidence to attributes
   - Technical skills from work products
   - Communication patterns from interactions
   - Work styles from timing and cadence
   - Collaboration preferences from team dynamics

4) **Aggregate for privacy**: Combine individual signals
   - Apply minimum group size thresholds
   - Report distributions, not individuals
   - Suppress outlier details that could identify

5) **Validate findings**: Check for bias and accuracy
   - Compare against known benchmarks
   - Check for sampling bias
   - Identify confounding factors

6) **Generate insights**: Focus on actionable patterns
   - Skill gaps at team/org level
   - Collaboration opportunities
   - Process improvement opportunities

## Output Contract

Return a structured object:

```yaml
discoveries:
  - id: string
    type: skill_pattern | work_style | collaboration_pattern | capability_gap
    description: string
    aggregation_level: team | department | organization
    population_size: integer
    significance: low | medium | high
    novelty: known | suspected | surprising
    evidence:
      - type: behavioral | artifact | metric
        source: string
        aggregated: boolean
skill_patterns:
  - skill_area: string
    distribution:
      high: number  # percentage
      medium: number
      low: number
      none: number
    evidence_sources: array[string]
    benchmark_comparison: string | null
work_style_patterns:
  - pattern_name: string
    prevalence: number  # percentage
    characteristics: array[string]
    correlated_outcomes: array[string]
collaboration_patterns:
  - pattern_name: string
    prevalence: number
    description: string
    team_impact: string
capability_gaps:
  - area: string
    current_level: string
    target_level: string
    gap_size: small | medium | large
    impact: string
    prevalence: number  # percentage affected
privacy_attestation:
  aggregation_level: string
  minimum_group_size: integer
  individuals_identifiable: boolean
  protected_attributes_excluded: boolean
recommendations:
  - action: string
    target: string  # team, department, etc.
    rationale: string
    priority: low | medium | high
methodology: string
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
limitations: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `discoveries` | array | Individual patterns found |
| `skill_patterns` | array | Skill distributions |
| `work_style_patterns` | array | Work style prevalence |
| `collaboration_patterns` | array | Team interaction patterns |
| `capability_gaps` | array | Identified skill gaps |
| `privacy_attestation` | object | Privacy protection confirmation |
| `recommendations` | array | Actionable suggestions |
| `confidence` | number | 0.0-1.0 based on evidence quality |
| `evidence_anchors` | array[string] | Aggregated evidence sources |
| `assumptions` | array[string] | Explicitly stated assumptions |
| `limitations` | array[string] | Analysis limitations |

## Examples

### Example 1: Discovering Team Skill Patterns

**Input:**
```yaml
data_source: "team_artifacts/"
attribute_types:
  - "technical_skills"
  - "collaboration_patterns"
aggregation_level: "team"
time_range:
  start: "2023-10-01"
  end: "2023-12-31"
privacy_threshold: 5
```

**Output:**
```yaml
discoveries:
  - id: "disc-001"
    type: skill_pattern
    description: "Backend team has strong Python skills but limited Kubernetes expertise"
    aggregation_level: team
    population_size: 8
    significance: high
    novelty: suspected
    evidence:
      - type: artifact
        source: "Code review comments, commit patterns, documentation contributions"
        aggregated: true
  - id: "disc-002"
    type: collaboration_pattern
    description: "Cross-team code reviews are 4x less frequent than within-team reviews"
    aggregation_level: department
    population_size: 24
    significance: medium
    novelty: surprising
    evidence:
      - type: metric
        source: "Review assignment patterns, review completion times"
        aggregated: true
  - id: "disc-003"
    type: capability_gap
    description: "Security review capability concentrated in 2 individuals across 3 teams"
    aggregation_level: department
    population_size: 24
    significance: high
    novelty: suspected
    evidence:
      - type: behavioral
        source: "Security-tagged PR reviews, security tool usage"
        aggregated: true
  - id: "disc-004"
    type: work_style
    description: "Teams show two distinct collaboration modes: synchronous (daily standups) vs async (written updates)"
    aggregation_level: department
    population_size: 24
    significance: medium
    novelty: known
    evidence:
      - type: behavioral
        source: "Meeting patterns, communication channel usage"
        aggregated: true
skill_patterns:
  - skill_area: "Python development"
    distribution:
      high: 62.5
      medium: 25.0
      low: 12.5
      none: 0.0
    evidence_sources:
      - "Code complexity metrics"
      - "PR review patterns"
      - "Documentation contributions"
    benchmark_comparison: "Above industry average for backend teams"
  - skill_area: "Kubernetes/container orchestration"
    distribution:
      high: 12.5
      medium: 25.0
      low: 37.5
      none: 25.0
    evidence_sources:
      - "Infrastructure code contributions"
      - "Deployment review participation"
      - "Incident response patterns"
    benchmark_comparison: "Below target for cloud-native team"
  - skill_area: "Technical documentation"
    distribution:
      high: 25.0
      medium: 37.5
      low: 25.0
      none: 12.5
    evidence_sources:
      - "README and doc contributions"
      - "Code comment patterns"
      - "Architecture decision records"
    benchmark_comparison: "Average"
  - skill_area: "Security practices"
    distribution:
      high: 8.3
      medium: 16.7
      low: 41.7
      none: 33.3
    evidence_sources:
      - "Security-tagged reviews"
      - "Secure coding patterns"
      - "Vulnerability response time"
    benchmark_comparison: "Critical gap - below minimum threshold"
work_style_patterns:
  - pattern_name: "Deep work preference"
    prevalence: 45
    characteristics:
      - "Long uninterrupted coding sessions (2+ hours)"
      - "Fewer but larger commits"
      - "Async communication preference"
    correlated_outcomes:
      - "Higher code quality scores"
      - "Longer PR turnaround time"
  - pattern_name: "Collaborative coding"
    prevalence: 35
    characteristics:
      - "Frequent small commits"
      - "High PR comment engagement"
      - "Active in synchronous discussions"
    correlated_outcomes:
      - "Faster PR merge times"
      - "More cross-team reviews"
  - pattern_name: "Hybrid"
    prevalence: 20
    characteristics:
      - "Varies by task type"
      - "Context-dependent communication"
    correlated_outcomes:
      - "Flexible project assignment"
collaboration_patterns:
  - pattern_name: "Within-team review circle"
    prevalence: 78
    description: "PRs reviewed by same 2-3 teammates consistently"
    team_impact: "Fast reviews but limited knowledge sharing"
  - pattern_name: "Cross-team mentorship"
    prevalence: 15
    description: "Senior developers review junior PRs across teams"
    team_impact: "Slower but better knowledge distribution"
  - pattern_name: "Silo pattern"
    prevalence: 7
    description: "Self-approved PRs or single reviewer only"
    team_impact: "Risk of knowledge concentration"
capability_gaps:
  - area: "Kubernetes/container orchestration"
    current_level: "37.5% at medium+ proficiency"
    target_level: "75% at medium+ proficiency"
    gap_size: large
    impact: "Blocking independent deployment capability"
    prevalence: 62.5
  - area: "Security review capability"
    current_level: "8.3% can perform security reviews"
    target_level: "25% per team minimum"
    gap_size: large
    impact: "Bottleneck in security review process; 2 people for 24-person department"
    prevalence: 91.7
  - area: "Cross-team collaboration"
    current_level: "15% of reviews are cross-team"
    target_level: "30% recommended for knowledge sharing"
    gap_size: medium
    impact: "Knowledge silos forming"
    prevalence: 85
privacy_attestation:
  aggregation_level: "team (minimum 8 people)"
  minimum_group_size: 5
  individuals_identifiable: false
  protected_attributes_excluded: true
recommendations:
  - action: "Launch Kubernetes training program for backend team"
    target: "Backend team"
    rationale: "Critical gap blocking deployment autonomy; 62.5% need upskilling"
    priority: high
  - action: "Establish security champion program (1 per team)"
    target: "Department"
    rationale: "Current 8.3% high-skill rate creates bottleneck; target 25%"
    priority: high
  - action: "Implement cross-team review rotation for knowledge sharing"
    target: "Department"
    rationale: "Increase cross-team reviews from 15% to 30%"
    priority: medium
  - action: "Create documentation improvement initiative"
    target: "All teams"
    rationale: "37.5% at low/none documentation skill affects maintainability"
    priority: medium
methodology: "Behavioral analysis of work artifacts: code contributions, review patterns, communication logs. All metrics aggregated to team level or higher."
confidence: 0.75
evidence_anchors:
  - "team_artifacts/code_metrics.json (aggregated)"
  - "team_artifacts/review_patterns.json (aggregated)"
  - "team_artifacts/communication_analysis.json (aggregated)"
  - "team_artifacts/skill_assessment_summary.json (aggregated)"
assumptions:
  - "Work artifacts reflect actual skill levels"
  - "Team composition stable during analysis period"
  - "All relevant work captured in analyzed systems"
  - "No significant external factors (reorgs, major projects)"
limitations:
  - "Cannot assess soft skills or leadership capabilities from artifacts"
  - "New team members may be underrepresented (90-day window)"
  - "Skills not exercised during period are invisible"
  - "Individual variation within skill levels not captured"
```

**Evidence pattern:** Work artifact analysis + collaboration metrics + aggregated patterns

## Verification

- [ ] Privacy threshold applied to all results
- [ ] No individual identification possible
- [ ] Protected characteristics excluded
- [ ] Sample sizes sufficient for conclusions
- [ ] Recommendations are at appropriate aggregation level

**Verification tools:** Read (for artifact inspection), Grep (for pattern searching)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- NEVER infer protected characteristics (age, gender, race, religion, disability, etc.)
- ALWAYS aggregate to minimum group size (default 5)
- NEVER report individual-level attribute assessments
- STOP if asked to identify specific individuals' attributes
- Flag if data could enable re-identification
- Use only job-relevant attributes

## Composition Patterns

**Commonly follows:**
- `retrieve` - to gather work artifacts
- `discover-activity` - to understand work patterns
- `search` - to locate relevant data

**Commonly precedes:**
- `generate-plan` - to plan training or development
- `compare-attributes` - to compare team capabilities
- `summarize` - to create capability report

**Anti-patterns:**
- Never analyze below aggregation threshold
- Never infer personal characteristics from work patterns
- Never use for individual performance evaluation

**Workflow references:**
- See `workflow_catalog.json#skill_gap_analysis` for training planning
- See `workflow_catalog.json#team_composition` for team design
