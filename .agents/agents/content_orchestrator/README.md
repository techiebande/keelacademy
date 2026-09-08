# Content Marketing subagent team — how to use

Any AI coding agent can run this pipeline. Claude Code, Gemini, Codex, Antigravity, or anything else that can read markdown instructions and write files.

## Quick start

1. Read this file.
2. Read `AGENTS.md` for project context.
3. Pick a topic from `content/marketing/ideas.md` (or bring your own).
4. Follow the pipeline below, step by step.

## The pipeline

The team has five roles. One agent can play all five roles in sequence, or multiple agents can split the work. The contracts define what each role does, not which tool runs it.

### Step 1 — Strategist

Read the contract: `.agents/agents/content_strategist/agent.md`

Input: a topic (one sentence).
Output: a content brief in YAML (angle, audience, value hook, key points, hook line).

### Step 2 — Writer

Read the contract: `.agents/agents/content_writer/agent.md`

Input: the approved content brief.
Output: `source.md` (800 to 1500 words, full article in dev.to style).

### Step 3 — Adapter

Read the contract: `.agents/agents/platform_adapter/agent.md`

Input: the approved source article and the content brief.
Output: four files: `linkedin.md`, `devto.md`, `twitter.md`, `facebook.md`.

Also generate a cover image for the dev.to post (1000x420px, simple, on-brand).

### Step 4 — Reviewer

Read the contract: `.agents/agents/content_reviewer/agent.md`

Input: the brief and all five content files. Do NOT give the reviewer access to school-architecture.md, curriculum.md, or internal docs. They read cold.
Output: a review report scoring value, voice, platform fit, hook strength, copy violations, and clarity.

### Step 5 — Repair and save

Fix any issues the reviewer found. Re-run the reviewer. Loop up to three times.

Save all files to `content/marketing/posts/<slug>/`:
```
brief.yaml
source.md
linkedin.md
devto.md
twitter.md
facebook.md
cover.png (or cover.jpg)
meta.yaml
```

Mark the idea as `[done]` in `content/marketing/ideas.md`.

## The full orchestrator contract

For the complete sequencing rules, gates, and hard rules, read:
`.agents/agents/content_orchestrator/agent.md`

## Key references

| File | What it contains |
|---|---|
| `content/marketing/brand-guide.md` | Positioning, voice, differentiators, guardrails |
| `content/marketing/ideas.md` | Content ideas backlog (pick next unused) |
| `content/STYLE.md` | Plain-language standard and copy bans |
| `docs/voice.md` | The teaching voice definition |
| `school-architecture.md` | What Keel Academy is (sections 0 to 2) |
| `curriculum.md` | What the curriculum covers (table of contents, lines 1 to 60) |
