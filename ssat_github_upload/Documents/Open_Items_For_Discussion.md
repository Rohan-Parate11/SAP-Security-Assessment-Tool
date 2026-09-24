# Open Items for Discussion

Running list of topics flagged for later discussion -- not yet decided or scoped.

## AI component in the Security Assessment Tool

- **Question:** How can we include an AI component in this tool?
- **Context:** The original project vision (`SAP_Security_Framework_Assessment_Context.md`) already calls for "AI-assisted executive and technical reports," "AI-generated findings," and "AI reporting" in the tech stack -- none of that is implemented yet; today the tool only does rule-based data collection and narrative templating.
- **Rationale for scope (2026-09-23):** this is an *assessment* tool -- it should hand back an assessment outcome with recommendations, not just raw collected data. The three selected items below are the ones that directly serve that: turning a run's results into a narrative outcome, turning each finding into actionable remediation, and letting a consultant interrogate the results afterward.

### Selected scope

1. **Auto-generated executive summary narrative** from a run's raw check results (today's "Key Finding" sentences are template-based, not model-generated).
2. **LLM-assisted remediation guidance** tailored to each finding.
3. **Natural-language Q&A over a completed assessment's results.**

### Considered, not selected for now

- Trend/anomaly detection across historical runs (ties into the History/Compare feature)
- Risk/maturity scoring assistance

- **Status:** Scope decided 2026-09-23 -- narrowed from the original brainstorm to the 3 items above. Not yet planned or implemented.
