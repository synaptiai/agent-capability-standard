---
name: search
description: Find relevant items under uncertainty across repositories, databases, web sources, or any searchable corpus. Use when exploring unknown territory, finding related information, or discovering relevant resources.
argument-hint: "[query] [sources: repo|web|docs] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Web
context: fork
agent: explore
---

## Live Context

Available search context:

- Current directory: !`pwd`
- File types available: !`find . -type f -not -path './.git/*' 2>/dev/null | sed 's/.*\.//' | sort | uniq -c | sort -rn | head -10`
- Total searchable files: !`find . -type f -not -path './.git/*' 2>/dev/null | wc -l | tr -d ' '`
- Common directories: !`find . -type d -maxdepth 2 -not -path './.git/*' 2>/dev/null | head -10`
- README files: !`find . -name 'README*' -not -path './.git/*' 2>/dev/null | head -5`

## Intent

Execute **search** to find relevant information when you don't know exactly where to look. Unlike `retrieve` (which fetches known items), search explores under uncertainty and ranks results by relevance.

**Success criteria:**
- Relevant results are found and ranked
- Search strategy is appropriate for the domain
- Coverage is sufficient for the use case
- Results include relevance scores and evidence
- False positives are minimized

**World Modeling Context:**
Search feeds into the **State Layer** by discovering entities and observations to include in `world-state`. It supports the **Identity & Continuity Layer** by finding candidate matches for `identity-resolution`.
**Compatible schemas:**
- `schemas/output_schema.yaml`


## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `query` | Yes | string | What to search for (natural language or structured) |
| `sources` | No | array | Where to search: `repo`, `web`, `docs`, `database` (default: infer) |
| `constraints` | No | object | Time bounds, file types, domains, result limits |
| `ranking_criteria` | No | string | `relevance`, `recency`, `authority` (default: relevance) |

## Procedure

1) **Parse query**: Understand what the user is looking for
   - Extract key terms and concepts
   - Identify entity types being sought
   - Determine search intent (existence, discovery, comparison)
   - Expand with synonyms or related terms if appropriate

2) **Select search strategy**: Based on sources and query type
   - **Code/repo search**: Use Grep patterns, file globs
   - **Web search**: Use web search tools with keywords
   - **Documentation**: Search docs directories, README files
   - **Semantic**: Expand query with related concepts

3) **Construct search queries**: Formulate effective queries
   - For Grep: Build regex patterns that balance precision/recall
   - For web: Use keywords, exclude noise terms
   - Apply filters (file type, date range, domain)

4) **Execute searches**: Run queries across sources
   - Use multiple query variations if first returns poor results
   - Apply pagination for comprehensive coverage
   - Track which queries were tried

5) **Collect and deduplicate results**: Aggregate findings
   - Merge results from multiple sources
   - Remove duplicates (same content, different paths)
   - Note source and search method for each result

6) **Rank results**: Score by relevance and other criteria
   - **Term match**: How well result matches query
   - **Authority**: Source credibility, recency
   - **Context**: Relevance to broader task
   - **Uniqueness**: Information not found elsewhere

7) **Extract key information**: For top results
   - Relevant snippets that match query
   - Metadata (file, date, author)
   - Context around the match

8) **Assess coverage**: Evaluate search completeness
   - What portion of relevant sources were searched?
   - Any known blind spots?
   - Suggest additional searches if coverage is poor

## Output Contract

Return a structured object:

```yaml
search_results:
  query: string  # Original query
  query_expansions: array[string]  # Variations tried
  sources_searched: array[string]  # Where we looked
  results:
    - id: string  # Result identifier
      type: file | web | doc | record
      source: string  # Where found
      path: string | null  # File path or URL
      title: string | null
      snippet: string  # Relevant excerpt
      relevance_score: number  # 0.0-1.0
      metadata:
        date: string | null
        author: string | null
        size: number | null
      evidence_anchor: string  # Reference for grounding
  total_found: integer  # Total results before filtering
  returned: integer  # Results in this response
coverage:
  sources_available: array[string]
  sources_searched: array[string]
  coverage_ratio: number  # 0.0-1.0
  blind_spots: array[string]  # Known gaps
search_strategy:
  method: string  # How search was conducted
  queries_executed: array[string]  # Actual queries run
  filters_applied: object
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
next_searches: array[string]  # Suggested follow-up searches
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `results` | array | Ranked search results |
| `relevance_score` | number | How well result matches query |
| `coverage` | object | Assessment of search completeness |
| `blind_spots` | array | Known areas not searched |
| `next_searches` | array | Suggested follow-up queries |

## Examples

### Example 1: Code Search for Authentication Logic

**Input:**
```yaml
query: "JWT token validation"
sources: ["repo"]
constraints:
  file_types: [".ts", ".js"]
  exclude_paths: ["node_modules", "test"]
```

**Output:**
```yaml
search_results:
  query: "JWT token validation"
  query_expansions:
    - "jwt.*valid"
    - "token.*verify"
    - "jsonwebtoken"
  sources_searched: ["repo:src/"]
  results:
    - id: "r1"
      type: file
      source: "repo"
      path: "src/middleware/auth.ts"
      title: null
      snippet: |
        export function validateToken(token: string): JWTPayload {
          return jwt.verify(token, process.env.JWT_SECRET) as JWTPayload;
        }
      relevance_score: 0.95
      metadata:
        date: "2025-01-20"
        author: null
        size: 2450
      evidence_anchor: "src/middleware/auth.ts:45-48"
    - id: "r2"
      type: file
      source: "repo"
      path: "src/services/user-service.ts"
      title: null
      snippet: |
        const decoded = validateToken(authHeader.split(' ')[1]);
      relevance_score: 0.75
      metadata:
        date: "2025-01-15"
        size: 5200
      evidence_anchor: "src/services/user-service.ts:23"
    - id: "r3"
      type: file
      source: "repo"
      path: "src/utils/jwt-helpers.ts"
      title: null
      snippet: |
        export const JWT_ALGORITHM = 'HS256';
        export const TOKEN_EXPIRY = '24h';
      relevance_score: 0.60
      metadata:
        date: "2024-12-01"
        size: 800
      evidence_anchor: "src/utils/jwt-helpers.ts:1-5"
  total_found: 8
  returned: 3
coverage:
  sources_available: ["repo", "docs"]
  sources_searched: ["repo:src/"]
  coverage_ratio: 0.85
  blind_spots:
    - "Config files not searched"
    - "Documentation not searched"
search_strategy:
  method: "grep_pattern_search"
  queries_executed:
    - "grep -r 'jwt.*valid' --include='*.ts' src/"
    - "grep -r 'token.*verify' --include='*.ts' src/"
  filters_applied:
    file_types: [".ts", ".js"]
    excluded: ["node_modules", "test"]
confidence: 0.9
evidence_anchors:
  - "src/middleware/auth.ts:45-48"
  - "src/services/user-service.ts:23"
  - "src/utils/jwt-helpers.ts:1-5"
assumptions:
  - "All JWT logic is in TypeScript files"
  - "No JWT validation in excluded test files matters"
next_searches:
  - "Search config/ for JWT_SECRET references"
  - "Search docs/ for authentication documentation"
```

**Evidence pattern:** Used Grep with multiple patterns to find JWT-related code, ranked by directness of validation logic.

---

### Example 2: Web Search for API Documentation

**Input:**
```yaml
query: "OpenAI API rate limits 2025"
sources: ["web"]
ranking_criteria: recency
```

**Output:**
```yaml
search_results:
  query: "OpenAI API rate limits 2025"
  query_expansions:
    - "OpenAI rate limit tiers"
    - "GPT-4 API quota"
  sources_searched: ["web"]
  results:
    - id: "w1"
      type: web
      source: "web"
      path: "https://platform.openai.com/docs/guides/rate-limits"
      title: "Rate limits - OpenAI API"
      snippet: "Rate limits are measured in tokens per minute (TPM) and requests per minute (RPM). Tier 1 users: 500 RPM, 100,000 TPM..."
      relevance_score: 0.95
      metadata:
        date: "2025-01-15"
        author: "OpenAI"
      evidence_anchor: "url:https://platform.openai.com/docs/guides/rate-limits"
    - id: "w2"
      type: web
      source: "web"
      path: "https://community.openai.com/t/rate-limit-changes-2025"
      title: "Rate Limit Changes in 2025"
      snippet: "As of January 2025, we've updated rate limit tiers..."
      relevance_score: 0.85
      metadata:
        date: "2025-01-10"
      evidence_anchor: "url:https://community.openai.com/t/rate-limit-changes-2025"
  total_found: 15
  returned: 2
coverage:
  sources_available: ["web", "docs"]
  sources_searched: ["web"]
  coverage_ratio: 0.7
  blind_spots:
    - "Internal documentation not accessible"
search_strategy:
  method: "web_search"
  queries_executed:
    - "OpenAI API rate limits 2025"
    - "OpenAI rate limit tiers"
  filters_applied:
    recency: "2025"
confidence: 0.85
evidence_anchors:
  - "url:https://platform.openai.com/docs/guides/rate-limits"
assumptions:
  - "Official documentation is current"
next_searches:
  - "Search OpenAI changelog for rate limit updates"
```

## Verification

- [ ] All returned results have valid evidence anchors
- [ ] Relevance scores are between 0.0 and 1.0
- [ ] Coverage assessment identifies blind spots
- [ ] Search strategy is documented
- [ ] Suggested next searches address coverage gaps

**Verification tools:** Link validators, file existence checks

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not search paths marked as sensitive
- Rate-limit web searches appropriately
- Flag when search coverage is < 50%
- Distinguish authoritative from user-generated sources

## Composition Patterns

**Commonly follows:**
- None typically - search is often a starting point
- May follow `inspect` when inspection reveals knowledge gaps

**Commonly precedes:**
- `retrieve` - After finding, retrieve full content
- `world-state` - Search results inform state construction
- `identity-resolution` - Find candidate entities to resolve
- `grounding` - Search for evidence to ground claims

**Anti-patterns:**
- Avoid searching when exact path is known (use `retrieve`)
- Never search without considering coverage limitations

**Workflow references:**
- See `reference/composition_patterns.md#world-model-build` for search in model construction
- See `reference/composition_patterns.md#debug-code-change` for search during debugging
