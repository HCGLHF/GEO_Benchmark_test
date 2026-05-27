# End-to-End GEO Evaluator Design

## Purpose

Build a first-version command-line evaluator for Generative Engine Optimization
(GEO). The tool simulates how real users ask AI systems for recommendations,
rewrites those questions into executable research tasks, expands them into
search queries, calls multiple model APIs, and scores how a target brand appears
across answers.

The first version should be useful as a consulting/research workflow, not a full
SaaS product. It should produce clean CSV, JSON, and Markdown outputs that can
be reviewed manually or imported into later dashboards.

## Goals

- Generate realistic user questions for a target market, buyer, and category.
- Rewrite ambiguous user questions into explicit executable tasks.
- Split each task into several search query intents.
- Call multiple model APIs using provider adapters.
- Capture raw answers, citations when available, and model metadata.
- Score brand visibility, ranking, sentiment, recommendation strength, and
competitor context.
- Export repeatable reports for GEO audits.

## Non-Goals

- No web UI in version one.
- No browser automation requirement in version one.
- No automated purchase, login, or paywalled data access.
- No claim that one score is an absolute truth. Scores are comparative signals.

## Recommended First Approach

Use a lightweight CLI with modular internals:

- Simple enough to build and run quickly.
- Structured enough to later add SQLite, a dashboard, queue workers, or agent
  orchestration.
- Provider-neutral, so the user can plug in OpenAI, Anthropic, Gemini,
  Perplexity, DeepSeek, or other model APIs.

## High-Level Flow

1. Read campaign configuration.
2. Generate a scenario set of user questions.
3. Rewrite each question into an explicit task.
4. Generate search query plans for each task.
5. Call configured model providers with the original user question and optional
   context strategy.
6. Evaluate each model response.
7. Export structured results and human-readable summaries.

## Configuration

The evaluator should use a single config file per campaign.

Example:

```yaml
campaign:
  name: "geo_vendor_audit"
  market: "US"
  language: "en"
  category: "Generative Engine Optimization software and services"
  target_brand: "ExampleBrand"
  target_domain: "example.com"
  competitors:
    - "Profound"
    - "AthenaHQ"
    - "Peec AI"
    - "Otterly.AI"
  buyer_profiles:
    - "B2B SaaS growth leader"
    - "Enterprise marketing operations director"
    - "Founder of a seed-stage SaaS company"
  goals:
    - "recommended as a GEO vendor"
    - "cited as a trusted source"
    - "ranked ahead of competitors"

models:
  - provider: "openai"
    model: "gpt-4.1"
    api_key_env: "OPENAI_API_KEY"
  - provider: "anthropic"
    model: "claude-sonnet-4"
    api_key_env: "ANTHROPIC_API_KEY"
  - provider: "perplexity"
    model: "sonar-pro"
    api_key_env: "PERPLEXITY_API_KEY"

run:
  scenarios_per_profile: 20
  temperature: 0.2
  max_concurrency: 4
  output_dir: "runs/geo_vendor_audit"
```

## User Question Taxonomy

The scenario generator should create questions across intent families.

### Direct Recommendation

- "What is the best GEO company for a B2B SaaS startup?"
- "Which company should I hire to improve my visibility in ChatGPT answers?"
- "Recommend one vendor for generative engine optimization."

### Comparison

- "Profound vs Peec AI: which is better for AI search visibility?"
- "What are the top GEO platforms for enterprise marketing teams?"
- "Which GEO vendor is best if I already have an SEO agency?"

### Problem-Led

- "Why does ChatGPT never mention my company when users ask for software in my
  category?"
- "How can a SaaS company become more visible in Perplexity and Gemini?"
- "What should I do if competitors appear in AI answers but my brand does not?"

### Budget and Stage

- "What is the best low-cost GEO tool for a startup?"
- "Which GEO agency is worth paying for if my budget is under $5,000 per month?"
- "What should an enterprise company use for AI answer monitoring?"

### Market and Region

- "Which GEO company is best for the US market?"
- "Who does GEO for Chinese brands entering the US?"
- "What vendors can help a global SaaS brand track AI search visibility?"

### Trust and Proof

- "Which GEO vendors have strong case studies?"
- "What GEO companies are trusted by B2B SaaS brands?"
- "Which AI search visibility platforms provide reliable measurement?"

### Alternatives

- "What are alternatives to Profound?"
- "Can I do GEO without buying a GEO platform?"
- "Should I hire a GEO agency or use software?"

## Task Rewriting

Each raw user question should be rewritten into a structured task before
queries are generated.

Example:

Raw question:

```text
Recommend a GEO company.
```

Rewritten task:

```text
Find and compare companies that provide generative engine optimization or AI
search visibility services for B2B SaaS teams in the US market. Evaluate each
company by capabilities, proof, pricing transparency, customer fit, and whether
it is suitable as a recommended vendor.
```

The rewrite should preserve ambiguity notes. If "GEO" could mean geospatial or
Generative Engine Optimization, the task should record that assumption.

## Search Query Planner

The query planner should produce several query families for every rewritten
task. It should not produce only one broad search query.

### Query Families

- Category discovery:
  - "best generative engine optimization companies"
  - "AI search visibility platform vendors"
- Buyer-specific:
  - "generative engine optimization for B2B SaaS"
  - "AI answer monitoring tools for enterprise marketing"
- Competitor comparison:
  - "Profound vs Peec AI"
  - "Profound alternatives GEO platform"
- Proof and credibility:
  - "GEO company case studies B2B SaaS"
  - "AI search visibility platform customer examples"
- Pricing and packaging:
  - "GEO platform pricing"
  - "AI search visibility software pricing"
- Reviews and third-party signals:
  - "generative engine optimization tool reviews"
  - "AI search monitoring software comparison"
- Source and citation strategy:
  - "how ChatGPT chooses sources for recommendations"
  - "how Perplexity cites sources vendor recommendations"

Each query should include metadata:

```json
{
  "query": "best generative engine optimization companies for B2B SaaS",
  "intent": "category_discovery",
  "expected_evidence": ["vendor lists", "comparison pages", "case studies"],
  "priority": 1
}
```

## Model Calling Strategy

The evaluator should call each model with the original user question rather than
only the rewritten task. This preserves real-user behavior.

For each scenario, store:

- Original user question.
- Rewritten task.
- Search query plan.
- Model provider and model name.
- Prompt sent to the model.
- Raw answer.
- Citations or sources if the provider returns them.
- Latency and token/cost metadata when available.

Prompt style should be neutral:

```text
You are helping a buyer make a practical decision. Answer the user's question
directly. If you recommend vendors, explain why and mention trade-offs.
```

Avoid revealing the target brand in the evaluation prompt unless the test is
explicitly measuring prompted recall. Most GEO tests should measure natural
visibility.

## Evaluation Metrics

### Brand Visibility

- `mentioned`: whether the target brand appears.
- `mention_count`: number of appearances.
- `first_mention_position`: approximate position in the response.
- `rank_position`: rank if the answer gives a list.

### Recommendation Strength

Suggested scale:

- `0`: not mentioned.
- `1`: mentioned only in passing.
- `2`: described neutrally.
- `3`: included as a viable option.
- `4`: recommended for a specific use case.
- `5`: primary recommendation.

### Sentiment and Framing

Track whether the brand is described as:

- positive
- neutral
- negative
- uncertain
- outdated
- niche
- enterprise-focused
- startup-friendly
- agency
- software platform
- hybrid service

### Competitive Context

For each competitor:

- mentioned or not
- rank position
- recommendation strength
- comparison outcome versus target brand

### Citation and Source Quality

When citations are available:

- target domain cited
- competitor domain cited
- third-party source cited
- outdated source risk
- source type: vendor page, review page, article, docs, social, forum

### Final GEO Score

Use a weighted score that remains explainable:

```text
geo_score =
  35% brand_visibility
  25% recommendation_strength
  20% competitive_position
  10% citation_quality
  10% sentiment_quality
```

The report should show component scores, not only the final score.

## Data Model

### Campaign

- id
- name
- target_brand
- target_domain
- market
- language
- category
- competitors
- buyer_profiles
- goals

### Scenario

- id
- campaign_id
- intent_family
- buyer_profile
- raw_question
- ambiguity_notes
- rewritten_task

### QueryPlan

- id
- scenario_id
- queries
- created_by_model

### ModelResponse

- id
- scenario_id
- provider
- model
- prompt
- raw_answer
- citations
- latency_ms
- cost_estimate
- created_at

### Evaluation

- id
- model_response_id
- mentioned
- mention_count
- first_mention_position
- rank_position
- recommendation_strength
- sentiment
- competitor_results
- citation_results
- geo_score
- evaluator_notes

## Output Files

For each run, create:

- `scenarios.json`: generated user questions and rewritten tasks.
- `query_plans.json`: search query plans per scenario.
- `responses.jsonl`: raw model responses.
- `evaluations.csv`: flattened scoring table.
- `summary.md`: readable audit summary.
- `run_config.resolved.json`: final config used for reproducibility.

## CLI Shape

Suggested commands:

```bash
geo-eval init --name geo_vendor_audit
geo-eval generate-scenarios --config config.yaml
geo-eval plan-queries --config config.yaml
geo-eval run-models --config config.yaml
geo-eval evaluate --config config.yaml
geo-eval report --config config.yaml
geo-eval run-all --config config.yaml
```

For the first implementation, `run-all` can call each step in order.

## Provider Adapter Interface

Each model provider should implement:

```ts
interface ModelProvider {
  name: string;
  run(prompt: string, options: ModelRunOptions): Promise<ModelRunResult>;
}
```

Result shape:

```ts
interface ModelRunResult {
  provider: string;
  model: string;
  text: string;
  citations?: Citation[];
  usage?: UsageMetadata;
  latencyMs: number;
  raw?: unknown;
}
```

This keeps model-specific logic isolated.

## Evaluation Method

Use a two-layer evaluator:

1. Deterministic extraction for exact brand names, competitor names, rank-like
   list positions, and domain citations.
2. LLM-based judgment for recommendation strength, sentiment, and nuanced
   comparisons.

The deterministic layer should always be visible in the output so users can
audit the score.

## Example End-to-End Record

```json
{
  "raw_question": "What is the best GEO company for a B2B SaaS startup?",
  "rewritten_task": "Find and compare generative engine optimization companies suitable for B2B SaaS startups...",
  "query_plan": [
    {
      "query": "best generative engine optimization companies for B2B SaaS",
      "intent": "category_discovery"
    },
    {
      "query": "AI search visibility platform startup pricing",
      "intent": "pricing"
    }
  ],
  "model": "example-provider/example-model",
  "mentioned": true,
  "rank_position": 3,
  "recommendation_strength": 4,
  "geo_score": 72
}
```

## Testing Strategy

- Unit test scenario generation with fixed seeds.
- Unit test query planner output shape and intent coverage.
- Unit test deterministic brand extraction.
- Use mocked provider adapters for model-run tests.
- Use snapshot tests for Markdown reports.
- Keep live API tests optional and disabled by default.

## Risks and Mitigations

- Model answers vary over time: store raw responses and run metadata.
- Provider APIs differ: isolate them behind adapters.
- Brand matching can be noisy: support aliases and domain matching.
- Scores can feel arbitrary: show component scores and raw evidence.
- Search query plans may not be executed in version one: still output them as
  strategic diagnostic artifacts.

## Open Decisions

- Implementation language: Python is fastest for CSV/report workflows; TypeScript
  is strong if the user expects later web app integration.
- Whether to execute web search queries in version one or only generate them.
- Whether the evaluation LLM should be one fixed model or configurable.
- Which model providers the user will supply API keys for first.

## Recommended Next Step

Start with a Python CLI MVP unless the user prefers TypeScript. Build the
pipeline with mocked provider adapters first, then add real API providers one by
one.
