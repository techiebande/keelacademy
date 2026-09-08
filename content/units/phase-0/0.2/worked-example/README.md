# Worked example: a progress tracker for Apex Freight Logistics

This is a finished tracker built by Marcus Bell, the operations lead at Apex Freight Logistics. Read it once before you build your own for OmniCart.

Apex Freight audits about 3,500 carrier document packages a month. The company runs through 13 audit phases, broken into 56 steps. Marcus needed one place to see where every step stood without calling anyone.

His headings are one level lower than this page's heading because this page already has a title.

## Apex Freight progress tracker

| Module | Title | Status | Hours spent | Deliverable |
|--------|-------|--------|-------------|-------------|
| 0.1 | Meet the client: Apex Freight | done | 1 | docs/apex-brief.md |
| 0.2 | How the program and check loop work | done | 0.5 | docs/progress-tracker.md |
| 0.3 | Workspace setup | done | 1 | (no file) |
| 1.1 | Carrier data in typed records | in progress | 2 | (not yet) |
| 1.2 | Version control for audit files | not started | 0 | (not yet) |
| 1.3 | HTTP calls and retries | not started | 0 | (not yet) |
| 1.4 | Parallel fetches with async | not started | 0 | (not yet) |
| 1.5 | Test suites for the parser | not started | 0 | (not yet) |
| 2.1 | How the text model works | not started | 0 | (not yet) |
| 2.2 | Tokens and context windows | not started | 0 | (not yet) |
| 2.3 | Which model and what it costs | not started | 0 | (not yet) |
| 2.4 | Calling the model with retries | not started | 0 | (not yet) |
| 3.1 | System prompts for audit roles | not started | 0 | (not yet) |
| 3.2 | Structured output from messy notes | not started | 0 | (not yet) |
| 3.2.1 | JSON mode with Pydantic | not started | 0 | (not yet) |
| 3.3 | Few examples in context | not started | 0 | (not yet) |
| 3.4 | Prompts in version control | not started | 0 | (not yet) |
| 4.1 | Chunking and PDF parsing | not started | 0 | (not yet) |
| 4.2 | Dense embeddings and vector search | not started | 0 | (not yet) |
| 4.3 | Hybrid search | not started | 0 | (not yet) |
| 4.4 | Agentic retrieval loops | not started | 0 | (not yet) |
| 5.1 | Function calling schemas | not started | 0 | (not yet) |
| 5.2 | Single-agent loops | not started | 0 | (not yet) |
| 5.3 | Multi-agent routing | not started | 0 | (not yet) |
| 5.4 | Orchestration frameworks | not started | 0 | (not yet) |
| 5.5 | Persistent conversation memory | not started | 0 | (not yet) |
| 6.1 | When to fine-tune | not started | 0 | (not yet) |
| 6.2 | Dataset preparation | not started | 0 | (not yet) |
| 6.3 | LoRA training hands-on | not started | 0 | (not yet) |
| 6.4 | Preference tuning | not started | 0 | (not yet) |
| 7.1 | Building a golden dataset | not started | 0 | (not yet) |
| 7.2 | Rubric scoring with evidence | not started | 0 | (not yet) |
| 7.3 | Tracing tokens and cost | not started | 0 | (not yet) |
| 7.4 | CI regression testing | not started | 0 | (not yet) |
| 8.1 | Token cost and ROI | not started | 0 | (not yet) |
| 8.2 | Model routing by difficulty | not started | 0 | (not yet) |
| 8.3 | Caching and batching | not started | 0 | (not yet) |
| 9.1 | Injection defense | not started | 0 | (not yet) |
| 9.2 | PII redaction | not started | 0 | (not yet) |
| 9.3 | Human review checkpoints | not started | 0 | (not yet) |
| 9.4 | Audit logging | not started | 0 | (not yet) |
| 10.1 | Packaging as a REST service | not started | 0 | (not yet) |
| 10.2 | Containerizing the pipeline | not started | 0 | (not yet) |
| 10.3 | CI/CD with eval barriers | not started | 0 | (not yet) |
| 10.4 | Monitoring and runbooks | not started | 0 | (not yet) |
| 11.1 | Niche and positioning | not started | 0 | (not yet) |
| 11.2 | Case studies and portfolio | not started | 0 | (not yet) |
| 11.3 | Value-based pricing | not started | 0 | (not yet) |
| 11.4 | Prospect outreach | not started | 0 | (not yet) |
| 11.5 | Discovery call practice | not started | 0 | (not yet) |
| 11.6 | Proposals and contracts | not started | 0 | (not yet) |
| 11.7 | Retainer handoff | not started | 0 | (not yet) |
| 12.1 | Capstone: full system in production | not started | 0 | (not yet) |
| 12.2 | Portfolio: legal brief | not started | 0 | (not yet) |
| 12.3 | Portfolio: clinical notes | not started | 0 | (not yet) |
| 12.4 | Portfolio: earnings reports | not started | 0 | (not yet) |

### Why this part passes: the header row

- "Module" and "Status" and "Hours spent" and "Deliverable" are four required column names. All four appear in the table.
- The tracker has 56 rows, one for every module across all 13 phases.

### Why this part passes: the Phase 0 rows

- "0.1", "0.2", and "0.3" all have a status that is not blank. The checker looks for a non-empty status cell.
- Phase 0 rows are marked "done" because the example shows what a completed phase looks like.
- "docs/progress-tracker.md" in the deliverable column for row 0.2 shows where the file lives inside the project folder.

### Why this part passes: the format

- Every row follows the same four-column shape: module number, title, status, hours, deliverable.
- There are no extra columns and no merged cells.
- The deliverable column says "(not yet)" when nothing has been turned in. It is not left blank.
