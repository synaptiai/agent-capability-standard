---
name: compare-people
description: Compare people or roles by evidence-based criteria for hiring, team composition, or role assignment. Use when evaluating candidates, comparing team members for assignments, or assessing role fit.
argument-hint: "[person_a] [person_b] [criteria] [role_context]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Compare individuals or role profiles against defined criteria to support evidence-based decisions about hiring, assignment, or team composition while respecting privacy and avoiding discriminatory factors.

**Success criteria:**
- Comparison uses only job-relevant, non-discriminatory criteria
- Each assessment is tied to observable evidence (work samples, documented performance)
- Recommendation accounts for role context and team dynamics
- Privacy-sensitive information is not accessed or inferred

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `candidates` | Yes | array[object] | People or role profiles to compare |
| `criteria` | Yes | array[string] | Job-relevant evaluation criteria |
| `role_context` | Yes | string | The role, project, or assignment being evaluated for |
| `weights` | No | object | Relative importance of criteria |
| `team_context` | No | object | Existing team composition and needs |
| `constraints` | No | object | Hard requirements (e.g., availability, clearance) |

## Procedure

1) **Validate criteria for fairness**: Screen criteria for job-relevance
   - Reject criteria that could proxy for protected characteristics
   - Ensure criteria are measurable and role-relevant
   - Document any criteria limitations

2) **Profile each candidate**: Gather evidence from appropriate sources
   - Work samples, portfolio, or documented contributions
   - Performance reviews or feedback (if authorized)
   - Skills assessments or certifications
   - Never infer personal characteristics beyond documented evidence

3) **Assess per criterion**: Evaluate each candidate against each criterion
   - Use observable evidence only (not assumptions or stereotypes)
   - Note gaps where evidence is unavailable
   - Apply consistent standards across all candidates

4) **Consider team fit**: If team_context provided
   - Assess complementary skills
   - Identify potential collaboration dynamics
   - Avoid "culture fit" that masks homogeneity preference

5) **Generate recommendation**: Synthesize findings
   - Provide conditional recommendation if criteria are close
   - Highlight where additional information would change outcome
   - Note any concerns about fairness or evidence quality

6) **Document limitations**: Explicitly state
   - Evidence gaps that affected assessment
   - Criteria that may need refinement
   - Contextual factors not captured

## Output Contract

Return a structured object:

```yaml
candidates:
  - id: string
    role_summary: string  # Brief professional summary
criteria:
  - name: string
    weight: number
    type: skill | experience | certification | behavioral
    fairness_note: string | null  # Any fairness considerations
comparison_matrix:
  - candidate_id: string
    scores:
      - criterion: string
        score: number  # 0.0-1.0
        evidence_type: work_sample | review | certification | assessment
        rationale: string
        evidence_anchor: string
        evidence_gap: string | null
recommendation:
  choice: string | null  # May be null if too close to call
  rationale: string
  confidence_factors: array[string]
  additional_info_needed: array[string]
tradeoffs:
  - candidate: string
    strengths: array[string]
    growth_areas: array[string]
team_fit_analysis: object | null  # If team_context provided
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
fairness_attestation: string  # Statement on non-discriminatory process
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `candidates` | array | People being compared with professional summaries |
| `criteria` | array | Job-relevant evaluation criteria |
| `comparison_matrix` | array | Scores with evidence for each candidate-criterion |
| `recommendation` | object | Final choice or explanation of close call |
| `tradeoffs` | array | Strengths and growth areas per candidate |
| `fairness_attestation` | string | Confirmation of non-discriminatory analysis |
| `confidence` | number | 0.0-1.0 based on evidence quality |
| `evidence_anchors` | array[string] | Work samples, reviews, or assessments cited |
| `assumptions` | array[string] | Explicitly stated assumptions |

## Examples

### Example 1: Comparing Candidates for Tech Lead Role

**Input:**
```yaml
candidates:
  - id: "candidate_a"
    profile_ref: "resumes/candidate_a.md"
  - id: "candidate_b"
    profile_ref: "resumes/candidate_b.md"
criteria:
  - "technical_depth"
  - "leadership_experience"
  - "communication_skills"
  - "project_delivery"
role_context: "Tech Lead for 5-person backend team, Series B startup"
weights:
  technical_depth: 0.3
  leadership_experience: 0.3
  communication_skills: 0.2
  project_delivery: 0.2
team_context:
  size: 5
  experience_levels: ["junior", "mid", "mid", "senior", "junior"]
  current_gaps: ["mentorship", "architecture decisions"]
```

**Output:**
```yaml
candidates:
  - id: "candidate_a"
    role_summary: "Senior engineer with 7 years experience, 2 years as team lead at mid-size company"
  - id: "candidate_b"
    role_summary: "Staff engineer with 9 years experience, tech lead for 2 projects, FAANG background"
criteria:
  - name: "technical_depth"
    weight: 0.3
    type: skill
    fairness_note: null
  - name: "leadership_experience"
    weight: 0.3
    type: experience
    fairness_note: "Evaluated based on documented outcomes, not years alone"
  - name: "communication_skills"
    weight: 0.2
    type: behavioral
    fairness_note: "Assessed via writing samples and presentation materials only"
  - name: "project_delivery"
    weight: 0.2
    type: experience
    fairness_note: null
comparison_matrix:
  - candidate_id: "candidate_a"
    scores:
      - criterion: "technical_depth"
        score: 0.75
        evidence_type: work_sample
        rationale: "Strong backend fundamentals, system design doc shows good patterns"
        evidence_anchor: "resumes/candidate_a.md:42"
        evidence_gap: null
      - criterion: "leadership_experience"
        score: 0.7
        evidence_type: review
        rationale: "Led team of 4, documented mentorship of 2 junior developers"
        evidence_anchor: "resumes/candidate_a.md:28"
        evidence_gap: "No direct reports feedback available"
      - criterion: "communication_skills"
        score: 0.8
        evidence_type: work_sample
        rationale: "Technical blog posts clear and well-structured"
        evidence_anchor: "https://blog.example.com/candidate_a"
        evidence_gap: null
      - criterion: "project_delivery"
        score: 0.75
        evidence_type: assessment
        rationale: "3 major project deliveries documented, one with delays"
        evidence_anchor: "resumes/candidate_a.md:55"
        evidence_gap: null
  - candidate_id: "candidate_b"
    scores:
      - criterion: "technical_depth"
        score: 0.9
        evidence_type: work_sample
        rationale: "Complex distributed systems experience, open source contributions"
        evidence_anchor: "resumes/candidate_b.md:38"
        evidence_gap: null
      - criterion: "leadership_experience"
        score: 0.6
        evidence_type: review
        rationale: "Tech lead on projects but no direct people management"
        evidence_anchor: "resumes/candidate_b.md:22"
        evidence_gap: "Mentorship outcomes not documented"
      - criterion: "communication_skills"
        score: 0.65
        evidence_type: work_sample
        rationale: "Technical docs comprehensive but dense"
        evidence_anchor: "github.com/candidate_b/project-docs"
        evidence_gap: "No non-technical communication samples"
      - criterion: "project_delivery"
        score: 0.85
        evidence_type: assessment
        rationale: "All documented projects delivered on time, high complexity"
        evidence_anchor: "resumes/candidate_b.md:48"
        evidence_gap: null
recommendation:
  choice: "candidate_a"
  rationale: "Better leadership and communication fit for team with many juniors; technical depth sufficient for role"
  confidence_factors:
    - "Clear mentorship track record"
    - "Communication style matches startup context"
  additional_info_needed:
    - "Reference check on leadership style"
    - "Candidate B interview for mentorship approach"
tradeoffs:
  - candidate: "candidate_a"
    strengths:
      - "Proven people management experience"
      - "Strong communication across experience levels"
      - "Startup-appropriate pragmatism"
    growth_areas:
      - "Less depth in distributed systems"
      - "Smaller scale experience (4 vs larger teams)"
  - candidate: "candidate_b"
    strengths:
      - "Exceptional technical depth"
      - "Experience with high-scale systems"
      - "Strong delivery track record"
    growth_areas:
      - "No direct people management experience"
      - "Communication may need adaptation for junior audience"
team_fit_analysis:
  complementary_skills: "candidate_a fills mentorship gap; candidate_b fills architecture gap"
  recommendation_context: "Team has 3 junior/mid members needing mentorship - weights leadership higher"
  risk_note: "candidate_b could be better if team matures in 12 months"
confidence: 0.7
evidence_anchors:
  - "resumes/candidate_a.md:28"
  - "resumes/candidate_a.md:42"
  - "resumes/candidate_a.md:55"
  - "resumes/candidate_b.md:22"
  - "resumes/candidate_b.md:38"
  - "resumes/candidate_b.md:48"
  - "https://blog.example.com/candidate_a"
  - "github.com/candidate_b/project-docs"
assumptions:
  - "Resumes and portfolios are accurate"
  - "Team composition will remain similar for 12 months"
  - "Role priorities leadership over deep technical work"
fairness_attestation: "Analysis used only job-relevant criteria based on documented evidence. No inferences made about protected characteristics."
```

**Evidence pattern:** Resume analysis + work sample review + public portfolio assessment

## Verification

- [ ] All criteria are job-relevant and non-discriminatory
- [ ] Each score cites observable evidence (not assumptions)
- [ ] Evidence gaps are documented for each candidate equally
- [ ] Fairness attestation is accurate and complete
- [ ] Recommendation rationale aligns with scored criteria

**Verification tools:** Read (for reviewing profiles and work samples)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Never access or infer protected characteristics (age, race, gender, religion, disability, etc.)
- Reject criteria that proxy for protected characteristics
- Use only authorized, job-relevant information sources
- Document evidence gaps consistently across all candidates
- Stop if asked to compare on discriminatory criteria
- Flag if evidence quality varies significantly between candidates

## Composition Patterns

**Commonly follows:**
- `retrieve` - to gather candidate profiles
- `search` - to find relevant work samples
- `identify-person` - to disambiguate candidate identities

**Commonly precedes:**
- `generate-plan` - to plan interview or onboarding
- `summarize` - to create executive summary for hiring committee
- `explain` - to justify recommendation to stakeholders

**Anti-patterns:**
- Never compare without documented, job-relevant criteria
- Avoid "culture fit" as criterion (too subjective, discriminatory risk)
- Never infer skills from demographic proxies

**Workflow references:**
- See `workflow_catalog.json#hiring_decision` for full hiring workflow
