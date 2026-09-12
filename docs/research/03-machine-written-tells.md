# Evidence brief 3: what makes explanatory text read as machine-written, and what marks it as human

Compiled 2026-09-12 for the lesson-system redesign. Every claim carries its source URL. This is one of three briefs; the synthesis is in `docs/lesson-design.md`.

## 1. The empirical core: LLM prose is measurably flatter and lexically skewed

**Vocabulary shift is documented at corpus scale.** Kobak et al. analysed 14 to 15M PubMed abstracts (2010 to 2024) with an "excess vocabulary" method modelled on excess-mortality studies and found an abrupt post-2022 rise in "style words"; they estimate at least 13.5% of 2024 abstracts were LLM-processed, up to about 40% in some sub-corpora (https://arxiv.org/abs/2406.07016). Liang et al. (Stanford) found that in ICLR 2024 peer reviews the adjectives *commendable*, *meticulous* and *intricate* became about 9.8x, 34.7x and 11.2x more likely, and that adverbs, verbs and non-technical nouns show the same skew (https://arxiv.org/pdf/2403.07183; https://hai.stanford.edu/news/how-much-research-being-written-large-language-models). Wikipedia's WikiProject AI Cleanup consolidates these into a watch-list: *Additionally* (sentence-initial), *align with*, *boasts*, *bolstered*, *crucial*, *deep dive*, *delve*, *enduring*, *enhance*, *fostering*, *garner*, *highlight* (verb), *interplay*, *intricate*, *key* (adj.), *landscape* (abstract), *meticulous*, *pivotal*, *robust*, *showcase*, *tapestry*, *testament*, *underscore* (verb), *vibrant*, noting they co-occur: "where there is one, there are likely others" (https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing).

**Rhythm is flatter ("burstiness").** A 2026 study of 60,779 human academic texts and AI rewrites by eight model configurations found human sentence-length coefficient of variation of about 0.449 vs about 0.376 for AI; 79.3% of AI rewrites were flatter than their human source, converging on medium-length sentences (https://textpulse.ai/research/textpulse-burstiness-sentence-length-2026.pdf). A 2,400-pair Polish student-report study (220 features) found LLM text has lower perplexity, lower burstiness and more uniform sentence lengths (https://doi.org/10.1515/psicl-2025-0063). Tarım & Onan confirm burstiness (variance in sentence-level perplexity) is lower for autoregressive and diffusion LLM text than for humans, though the gap is narrowing and no single metric is reliable on an individual text (https://arxiv.org/html/2507.10475). Biber-style register analysis across the RAID dataset finds LLM output "information-dense and noun-heavy," especially from instruction-tuned chat models (https://arxiv.org/html/2604.14111).

**Caveat every source repeats:** these are population-level signals. Wikipedia lists "perfect grammar," mixed casual/formal register and "bland" tone as *ineffective* indicators, warns of false accusations, and says style-only detection "is not as easy as it seems" (https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing#Ineffective_indicators). Editors' guides agree: the signal is *density and clustering* of tells, not any one instance (https://matthewvollmer.substack.com/p/i-asked-the-machine-to-tell-on-itself; https://proofed.com/knowledge-hub/ai-editing-checklist-how-to-spot-and-fix-ai-writing-patterns/).

## 2. The structural and rhetorical catalogue (Wikipedia AI Cleanup and editors)

The Wikipedia page groups tells into content, language, style, meta-communication, markup and citations (https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing). The ones relevant to explanatory prose:

- **Undue significance/legacy framing**: *stands as a testament*, *plays a pivotal role*, *underscores its importance*, *reflects broader trends*, *setting the stage for*, *marks a shift*.
- **Superficial analysis via trailing participles**: "..., highlighting/ensuring/fostering/reflecting X" bolted onto factual sentences: analysis-shaped filler.
- **Promotional register** ("puffery") inherited from marketing copy.
- **Vague attribution**: *experts argue*, *observers have cited*, *industry reports*.
- **Outline-like "Challenges and Future Outlook"** sections: "Despite its [praise], X faces challenges..." closing on a vaguely upbeat note.
- **Copula avoidance**: *serves as / functions as / represents / boasts / features* instead of *is/has*.
- **Vague connection**: *in connection with*, *associated with* instead of stating the actual relation.
- **Negative parallelism**: *not just X, but Y*; *not X, but Y*; *Y rather than X*: the text pretends to correct a misconception nobody held.
- **Rule of three** everywhere: three adjectives, three phrases, three bullets.
- **Formatting**: boldface on every key term; bullet lists with inline bold headers plus colon; em-dash overuse (now flagged as declining in newer models); title-case headings; heading levels containing only more headings; horizontal rules; emoji as bullets.
- **Meta-communication leaking in**: *Certainly!*, *I hope this helps*, *Would you like...*, *here is a...*; knowledge-cutoff disclaimers; *While specific details are limited...*
- **Historical (2022 to 24) tells** now less common but still diagnostic of templated writing generally: "It's important to note...", "In conclusion/In summary/Overall" section summaries, and forced *elegant variation* from repetition penalties.

Practitioner guides converge on the same short list: em-dash asides, "It's not X; it's Y," mechanical triads, hedging preambles ("It's worth noting," "Generally speaking," "In many cases"), performative openers ("Great question"), throat-clearing ("in order to," "importantly"), unnecessary passive voice, and hype vocabulary (*effortlessly*, *next-generation*, *revolutionize*, *leverage*) (https://proofed.com/knowledge-hub/ai-editing-checklist-how-to-spot-and-fix-ai-writing-patterns/; https://captainrandom.co.uk/writing/2026-05-28-pre-publish-style-audit/; https://donatassimkus.com/blog/how-to-spot-ai-writing-fix-it). Vollmer's field guide adds the "vibe" summary: surface polish with no substantive depth (https://matthewvollmer.substack.com/p/i-asked-the-machine-to-tell-on-itself).

## 3. Why templated prose looks like this: Goodhart's law on writing

**Prefabrication predates LLMs.** Orwell (1946) diagnosed the same failure: writers who "gum together long strips of words which have already been set in order by someone else," dying metaphors, pretentious diction and meaningless words, "ready-made phrases" that "partially conceal your meaning even from yourself." His antidote is six rules and five questions starting with "What am I trying to say?" (https://www.orwellfoundation.com/the-orwell-foundation/orwell/essays-and-other-works/politics-and-the-english-language/). Fowler's "elegant variation" (1906) named the tic of synonym-swapping to seem pretty, which Wikipedia editors later identified as a symptom of deeper syntactic trouble, not a fix (https://en.wikipedia.org/wiki/Elegant_variation; https://signpost.news/2022-04-24/Essay).

**Metrics get gamed.** Readability formulas count only sentence length and syllables; Redish shows they were built for children's schoolbooks, ignore content, organisation, tone and reader differences, and that "improving a score does not guarantee better understanding": a short sentence can be harder than a longer well-built one (https://redish.net/wp-content/uploads/Redish_on_Readability_Formulas.pdf). AHRQ explicitly warns writers not to "game" scores or overfit text to a formula (https://www.ahrq.gov/talkingquality/resources/writing/tip6.html). SEO critics document the Yoast-era result: "optimized readability" delivered as a product, producing text that is easy to read and empty (https://wskpf.com/takes/readability-is-not-what-you-think). Google's Panda (2011) and Helpful Content (2022) updates were direct responses to content written "for search engines first": formulaic, templated, automation-heavy pages that summarise others without adding value (https://searchengineland.com/google-forecloses-on-content-farms-with-farmer-algorithm-update-66071; https://developers.google.com/search/docs/fundamentals/creating-helpful-content). The pattern is identical whether the optimiser is a content farm, a Flesch score, or a checklist: prose converges on the measurable proxy and sheds the unmeasurable thing (specificity, judgment, a reason to exist).

**Paul Graham's diagnosis** connects this to thought: fancy or padded writing "can also conceal the lack of [ideas]," whereas "if you say nothing simply, it will be obvious to everyone, including you" (https://paulgraham.com/simply.html). In "Writes and Write-Nots" he argues writing *is* thinking (quoting Lamport: "If you're thinking without writing, you only think you're thinking"), so outsourced or templated text is text without thinking behind it (https://paulgraham.com/writes.html).

## 4. What marks text as genuinely human

**Choices, not averages.** Ted Chiang argues that a piece of writing is the accumulation of thousands of small choices at every scale; generative systems fill most of those choices with averages, which is why the output reads bland and derivative (https://www.newyorker.com/culture/the-weekend-essay/why-ai-isnt-going-to-make-art). In "Blurry JPEG" he adds that starting from an approximate rephrasing of existing text forecloses originality; real writing comes from struggling to say the thing clearly (https://www.newyorker.com/tech/annals-of-technology/chatgpt-is-a-blurry-jpeg-of-the-web).

**Discernment and voice.** Cory Doctorow, after about 1,700 daily posts, says quality comes from "authorial discernment": knowing which word fits your intent and when a suggested edit is wrong; expertise in the subject is what lets you recognise defective output (https://pluralistic.net/2026/07/28/hitl-ers/).

**Classic style and no metadiscourse.** Pinker's *Sense of Style* identifies the two hallmarks of stuffy prose as excessive metadiscourse (signposting, "in this section we will...") and thoughtless hedging (*virtually*, *allegedly*) that adds no precision; classic style instead points the reader at the object as if in conversation between equals (https://newrepublic.com/article/119687/steven-pinker-language-interview-jesse-singal; https://philosophicaldisquisitions.blogspot.com/2014/09/steven-pinkers-guide-to-classic-style.html).

**Humanity as a craft principle.** Zinsser's four "articles of faith" are clarity, brevity, simplicity and *humanity*: the writer's personality on the page (https://theclimatecommunicator.theclimatehub.co/p/clarity-brevity-simplicity-humanity). Lamott's "shitty first drafts" tradition treats the visible mess and honesty of the process as part of what readers trust (https://newrepublic.com/article/203899/anne-lamott-battle-writer-block).

**Wikipedia's positive tests**: a human can *explain their own editorial choices* (why a sentence is there, how a mistake happened) and shows idiosyncratic syntax rather than uniform polish (https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing#Signs_of_human_writing).

---

## List 1: tells (checkable markers of machine-written or templated explanation)

**Vocabulary**
1. Three or more watch-list words per 500 words (*delve, crucial, pivotal, robust, tapestry, landscape, testament, underscore, foster, showcase, intricate, meticulous*): statistically LLM-skewed (Kobak; Liang; Wikipedia).
2. Copula avoidance: *serves as / represents / boasts / features* for *is/has*: periphrasis that adds syllables, not meaning (Wikipedia AINOCOPULA).
3. Trailing participle "analysis": "..., highlighting the importance of X": evaluation-shaped filler with no new fact (Wikipedia SUPERFICIAL).
4. Significance inflation: *plays a key role*, *stands as a testament*, *marks a turning point*: the writer hasn't decided what specifically matters (Wikipedia AILEGACY).
5. Vague relation words: *associated with*, *in connection with*: hides the actual causal/temporal relation (Wikipedia AICONNECT).
6. Marketing hype: *seamlessly, effortlessly, cutting-edge, leverage, empower*: register borrowed from sales copy (Wikipedia AIPUFFERY; Simkus).
7. Elegant variation: synonym-cycling to avoid repeating a plain noun: repetition-penalty artefact / Fowler's fault (Wikipedia; Elegant variation).
8. Dying metaphors and stock idioms used without a picture in mind (Orwell).

**Sentence rhythm**
9. Sentence-length CV under about 0.38; almost every sentence 15 to 25 words; no bursts, no fragments (textpulse; psicl-2025-0063).
10. Consistently low perplexity: every next word is the expected word (Tarım & Onan).
11. Tricolons everywhere ("clear, concise, and compelling"): cadence substituting for content (Wikipedia RO3; Proofed).
12. Negative parallelism: "not just X but Y," "it's not about X, it's about Y": corrects a misconception nobody held (Wikipedia AIPARALLEL; Vollmer).
13. Em-dash asides in most paragraphs, especially the "trio" pattern (Proofed; Captain Random).
14. Noun-heavy, information-dense sentences with few verbs of action (arXiv 2604.14111).

**Structure**
15. Paragraphs of near-identical length, each opening with a topic sentence and closing with a mini-summary (Wikipedia section summaries).
16. Predictable skeleton: Intro, Background, Key Features, Challenges, Future Outlook, Conclusion (Wikipedia FACESCHALLENGES).
17. "Despite its X, Y faces several challenges..." pivot followed by upbeat close (Wikipedia).
18. Headings that contain only sub-headings; skipped heading levels; horizontal rules between sections (Wikipedia Style).
19. Content that summarises other sources without adding anything a reader couldn't get elsewhere (Google Helpful Content).

**Meta-text**
20. "It's important/worth noting that...", "Generally speaking...", "In many cases..." hedge preambles (Wikipedia DIDACTIC; Proofed).
21. Signposting metadiscourse: "In this section we will explore...", "As mentioned above..." (Pinker).
22. Empty rhetorical questions used as paragraph openers ("So what does this mean for you?") (Adpharm playbook "question-then-answer rhythm").
23. Vague attribution: *experts agree*, *studies show*, *observers note* without a name (Wikipedia AIWEASEL).
24. Chat leakage: "Certainly!", "I hope this helps", "Would you like a more detailed breakdown?" (Wikipedia COLLABCOMM).
25. Knowledge-cutoff or source-gap disclaimers: "While specific details are limited..." (Wikipedia AICUTOFF).

**Openings and closings**
26. Opens by defining the obvious or restating the title ("X is a concept that refers to...").
27. Opens with "In today's fast-paced/ever-evolving landscape...": setup-then-pivot cliché (Adpharm; Wikipedia AITREND).
28. Closes with "In conclusion / Overall / Ultimately" plus a restatement of the intro (Wikipedia INCONCLUSION).
29. Closes with a moral or "moving forward" exhortation not earned by the body (Wikipedia FACESCHALLENGES).

**Lists and formatting**
30. Bullets with inline **Bold Header:** followed by one sentence, in threes or fives (Wikipedia AILIST).
31. Boldface on every occurrence of a chosen term (Wikipedia AIBOLD).
32. Title Case Headings on prose that isn't a title (Wikipedia).
33. Emoji or check marks as bullets; tables used for non-tabular content (Wikipedia).
34. Every list item grammatically parallel and identical in length: machine symmetry (Vollmer).

**Tone**
35. Uniformly upbeat, promotional evaluation of the subject with no downside stated concretely (Wikipedia AIPUFFERY).
36. Zero first-person experience, opinion, or admitted uncertainty about a specific point; only generic hedges (Proofed notes AI hedges *because* it lacks experience).
37. Never addresses a specific reader confusion; explains what is easy and skips what is hard (Pinker's curse of knowledge, inverted).
38. Polish without depth: nothing is wrong, nothing is memorable (Vollmer; Chiang).

## List 2: human marks (practices that read as a real person wrote it)

1. Make and own specific choices at word level rather than accepting the default phrase (Chiang, https://www.newyorker.com/culture/the-weekend-essay/why-ai-isnt-going-to-make-art).
2. Be able to explain why each sentence is there and how any error happened (Wikipedia "Signs of human writing", https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing#Signs_of_human_writing).
3. Vary sentence length deliberately: fragments, one long unwinding sentence, then a short one (burstiness evidence, https://textpulse.ai/research/textpulse-burstiness-sentence-length-2026.pdf).
4. Use *is* and *has*; say the actual relationship ("In 2017 she was CEO") instead of "associated with" (Wikipedia AINOCOPULA/AICONNECT).
5. Ordinary words, simple sentences; cut hard in editing (Graham, https://paulgraham.com/simply.html).
6. Ask Orwell's five questions before writing a sentence; never use a metaphor you're used to seeing in print (https://www.orwellfoundation.com/the-orwell-foundation/orwell/essays-and-other-works/politics-and-the-english-language/).
7. Repeat the plain noun instead of synonym-cycling (Fowler / Wikipedia essay, https://signpost.news/2022-04-24/Essay).
8. Delete metadiscourse; point at the object and let the reader see it (classic style; Pinker, https://philosophicaldisquisitions.blogspot.com/2014/09/steven-pinkers-guide-to-classic-style.html).
9. Hedge only where the uncertainty is real, and name what's uncertain and why (Pinker, https://newrepublic.com/article/119687/steven-pinker-language-interview-jesse-singal).
10. Name the source: a person, a paper, a number, instead of "experts say" (Wikipedia AIWEASEL).
11. Include concrete, checkable detail (dates, quantities, a specific example that could be wrong) (Google's "first-hand expertise" criterion, https://developers.google.com/search/docs/fundamentals/creating-helpful-content).
12. Bring first-hand experience and opinion; say "I" when it's your judgment (Doctorow, https://pluralistic.net/2026/07/28/hitl-ers/).
13. Address the reader's likely confusion directly ("You'd expect X here; it isn't, because...") (Pinker on the curse of knowledge).
14. Let structure follow the argument, not a template; drop "Challenges/Future Outlook" unless you have something specific (Wikipedia FACESCHALLENGES).
15. End when you're done; no summary of what was just said (Wikipedia INCONCLUSION).
16. Write prose where prose works; use lists only for genuinely list-shaped information (Wikipedia AILIST, citing MOS "use prose where understood easily").
17. Prefer asymmetry: two items or four if that's how many there are; never pad to three (Wikipedia RO3).
18. Leave the honest mess of the draft's thinking visible where it helps: show a false start and why it was wrong (Lamott tradition, https://newrepublic.com/article/203899/anne-lamott-battle-writer-block).
19. Aim for Zinsser's humanity: the writer's personality on the page, not a brand voice (https://theclimatecommunicator.theclimatehub.co/p/clarity-brevity-simplicity-humanity).
20. Test with real readers instead of optimising a readability score (Redish, https://redish.net/wp-content/uploads/Redish_on_Readability_Formulas.pdf; AHRQ, https://www.ahrq.gov/talkingquality/resources/writing/tip6.html).
21. Write to think, not to fill a word count; if the sentence says nothing, it should be obvious to you first (Graham, https://paulgraham.com/writes.html).
22. Audit your own drafts for clustered tells before publishing (em-dash density, hedges, throat-clearing) (Captain Random, https://captainrandom.co.uk/writing/2026-05-28-pre-publish-style-audit/).

**Note:** Zinsser is cited via a secondary source (his four principles) because the primary text was not fetchable; all other claims cite the source examined.
