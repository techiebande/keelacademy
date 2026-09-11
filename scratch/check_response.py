import re
import sys

text = """
We completed Stage 1 of Understanding by Design for Unit 0.1.

Outputs created:
- We designed the learner baseline and anti-prerequisites.
- We defined the target competency and five retrieval seeds.
- We specified the project delta for omnicart-system/docs/client-brief.md.
- We scoped the parallel task for Apex Freight Logistics.
- We wrote content/units/phase-0/0.1/consistency.yaml.
- We saved the design brief to scratch/design-brief-0.1.md.

Understanding by Design Stage 1: Design Brief for Unit 0.1

Unit Metadata
- Unit ID: 0.1.
- Phase ID: phase-0.
- Title: Meet the client: OmniCart Operations.
- Kind: conceptual.
- Estimated time: 1 hr.
- Next unit: 0.2.
- Submission type: file.
- Verification layer: Layer 2 rubric review.

Learner Baseline

assumed_learner_state:
The learner can use a computer and view a web page.
The learner has read the opening story for OmniCart Operations.
The learner knows everyday work pain like late packages and upset buyers.
The learner has no project files or folders yet.
The learner has never written computer code or scripts.

forbidden_assumptions:
We forbid these words: ai, agent, agents, llm, llms, model, models, prompt, prompts, automation, automate, automated.
We also forbid: software, algorithm, algorithms, python, docker, api, apis, database, databases, json, schema, pipeline.
We also forbid: embedding, embeddings, token, tokens, chatbot, machine learning.
We do not assume the learner knows terminal commands, git, or code editors.
We do not assume the learner knows how computers solve business problems.
We do not assume any knowledge of academy grading loops.

spiraled_concepts:
This is the first unit.
No earlier units exist.
We build basic habits here.
We write clear notes in plain English.
We write money as whole integer cents.
We describe manual steps before jumping to fixes.

Target Competency in Plain Language
The learner explains OmniCart dispute troubles to a friend in three plain sentences.
The learner names three leaders and states what success means to each one.
The learner maps current manual steps from customer request to final payout.
The learner maps target steps to finish reviews in under 1 hour.
The learner uses exact business numbers and whole integer cents.
The learner names zero forbidden technology words.

Essential Question:
Who gets hurt when return disputes wait three days?
What does a fix mean to each leader?

Enduring Understanding:
Good systems begin with people, business rules, and money.
If we cannot explain the problem in plain words, we cannot fix it.

Retrieval Seeds
1. OmniCart handles about 4,000 return requests, damage claims, delivery slips, and payout disputes each month.
2. Today a dispute sits for 2 to 3 days before review begins.
3. Operations wants reviews under 1 hour, the CFO wants integer cents tracked, and compliance protects return rules.
4. Money is always written as integer cents, so 45 dollars and 20 cents becomes 4520 cents.
5. We describe the business problem in plain words before we choose any fix.

project_delta
The learner creates the folder omnicart-system/docs/.
The learner writes the initial file omnicart-system/docs/client-brief.md.
The document stays between 300 and 500 words.
It contains five required headings in exact order:
1. # OmniCart Operations: Client Brief
2. ## The problem
3. ## Who cares and why
4. ## How it works today
5. ## How it should work
The brief records the monthly volume of about 4,000 requests.
It records the current delay of 2 to 3 days.
It records the target review time of under 1 hour.
It names four required papers: order receipt, delivery slip, unboxing photo, and return policy.
It records all money in whole integer cents, like 4520 cents.
Later units keep this file and add sections below these headings.

Parallel Task for Apex Freight Logistics
The worked example uses Apex Freight Logistics.
Apex Freight Logistics is a freight broker in Indianapolis.
Apex checks about 3,500 carrier packages each month across 300 carriers.
The author writes apex-freight/docs/client-brief.md as the worked example.
It uses the exact same five headings as OmniCart.
It defines three leaders and their goals:
1. Marcus Bell, Operations Lead, wants package review cut from 2 days to under 1 hour.
2. Priya Nair, Controller, wants carrier payouts tracked to integer cents with records that cannot change.
3. Dana Okafor, Compliance Lead, wants detention pay rules and damage standards enforced fairly.
It maps current manual steps across five carrier papers.
These papers include rate confirmations, bills of lading, driver detention logs, damage claims, and carrier invoices.
It maps target steps with reviews under 1 hour and human review for hard cases.
It writes money in integer cents, like a detention fee of 12500 cents.
It uses zero forbidden technology words.

Contents of content/units/phase-0/0.1/consistency.yaml

```yaml
# Facts that must agree across every file of this unit (read by check-unit-consistency.py).
numbers:
  - "about 4,000"
  - "2 to 3 days"
  - "under 1 hour"
  - "4520 cents"
  - "CLM-20841"
  - "ORD-8821"
  - "14 day"
documents:
  - "order receipt"
  - "delivery slip"
  - "unboxing photo"
  - "return policy"
worked_example_uses_other_documents: true
```

Open Decisions for the Team
1. Should the worked example provide full starter text or annotated paragraphs for Apex Freight?
2. Should the completion task ask for the full brief or start with the problem statement alone?
"""

errors = []
# 1. Punctuation checks
for i, line in enumerate(text.splitlines(), start=1):
    if "\u2014" in line:
        errors.append(f"Line {i}: em dash")
    if "\u2013" in line:
        errors.append(f"Line {i}: en dash")
    if "!" in line:
        errors.append(f"Line {i}: exclamation mark")

# 2. Long sentences
prose = re.sub(r"```[\s\S]*?```", "", text)
sentences = re.split(r"(?<=[.?:])\s+", prose.replace("\n", " "))
for s in sentences:
    s = s.strip()
    if not s:
        continue
    cleaned = re.sub(r"^[#\-\d\.\s]+", "", s).strip()
    words = cleaned.split()
    if len(words) > 20:
        errors.append(f"Sentence over 20 words ({len(words)}): {s}")

# 3. Buzzwords
BUZZWORDS = ["leverage", "synergy", "streamline", "unlock", "empower", "robust", "seamless", "cutting-edge", "revolutionise", "supercharge", "it is worth noting that"]
for b in BUZZWORDS:
    if b in text.lower():
        errors.append(f"Buzzword: {b}")

if errors:
    for e in errors:
        print("FAIL:", e)
    sys.exit(1)
print("PASS: all checks green.")
