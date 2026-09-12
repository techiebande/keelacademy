# Evidence brief 1: how a written lesson for absolute-beginner programmers should be shaped

Compiled 2026-09-12 for the lesson-system redesign. Scope: written (text + code) lessons for novices. Effect sizes are Cohen's d unless noted. "Strong" = replicated across many experiments or a meta-analysis; "moderate" = several studies or one large quasi-experiment; "weak" = few or small studies, or theory-led. The synthesis is in `docs/lesson-design.md`.

## 1. Worked examples, fading, expertise reversal

- **Worked-example effect.** Novices learn more from studying fully worked solutions than from solving equivalent problems; the classic algebra demonstration is Sweller & Cooper (1985) (https://doi.org/10.1207/s1532690xci0201_3). Wilson cites a database course redesigned around worked examples, subgoals and removal of split-attention/redundancy that cut exam failure by 34% (https://teachtogether.tech/en/).
- **Fading/completion examples.** Renkl, Atkinson & Maier: a sequence of complete example, then example with last step omitted, then two steps omitted, then full problem beat traditional example-problem pairs on near transfer in field and lab studies; *backward* fading (remove last steps first) worked best, and the effect was mediated by fewer errors during learning (https://mrbartonmaths.com/resourcesnew/8.%20Research/Explicit%20Instruction/Structuring%20the%20Transition%20From%20Example%20Study%20to%20Problem%20Solving.pdf; Renkl et al. 2002 http://www.davidlewisphd.com/courses/EDD8121/readings/2002-Renkl_et_al.pdf). Adding self-explanation prompts to faded examples further improved transfer (https://mrbartonmaths.com/resourcesnew/8.%20Research/Making%20the%20most%20of%20examples/Fading%20out%20and%20Prompts.pdf).
- **Expertise reversal.** Guidance that helps novices (full worked examples, integrated explanations) becomes neutral or harmful as knowledge grows; Kalyuga's review documents the pattern across dozens of experiments (https://link.springer.com/article/10.1007/s10648-007-9054-3; Kalyuga, Ayres, Chandler & Sweller 2003 https://doi.org/10.1207/S15326985EP3801_4).

**Full code vs incremental?** The evidence does not say "hide the finished program". It says: show a *complete, explained* example first (worked-example effect), then have the learner complete progressively larger gaps (backward fading), then write from scratch. Building a program line by line in prose *is* a worked example if each step is explained; a bare final listing with no step explanation is not. Evidence strength: strong for worked examples and expertise reversal; moderate for fading specifics.

## 2. Cognitive load theory and page layout

- Load is intrinsic (element interactivity of the content), extraneous (poor design), germane (schema building). Teaching should minimise extraneous load so working memory (recently estimated at about 4 plus or minus 1 chunks) is spent on intrinsic content (Wilson's summary and sources, https://teachtogether.tech/en/).
- **Split-attention.** Chandler & Sweller (1992) showed that when text and diagram must be mentally integrated, learning suffers; physically integrating explanation into the diagram fixes it (https://www.davidlewisphd.com/courses/EDD8121/readings/1992-ChandlerSweller-SplitAttention.pdf). Mayer's spatial-contiguity data: 22/22 experiments positive, median d about 1.10 (https://www.cambridge.org/core/books/cambridge-handbook-of-multimedia-learning/principles-for-reducing-extraneous-processing-in-multimedia-learning-coherence-signaling-redundancy-spatial-contiguity-and-temporal-contiguity-principles/CD5B7AE1279A9AB81F8EEBB53DBEC86E).
- **Implication for code on a page:** the explanation of a line should sit *next to* that line (interleaved short code blocks with prose, inline comments, or numbered callouts), not in a paragraph three screens away. Long listings followed by "let's walk through this" force split attention. Strong evidence.

## 3. Mayer's principles that transfer to text + code

From the Cambridge Handbook meta-summaries (same URL as above; managing-essential-processing chapter https://www.researchgate.net/publication/292884042_Principles_for_managing_essential_processing_in_multimedia_learning_Segmenting_pre-training_and_modality_principles; summary of Mayer & Fiorella figures http://hdl.handle.net/10170/849):

| Principle | Evidence | Applies to written lessons as |
|---|---|---|
| Coherence (cut extraneous material) | 23/23 experiments, median d about 0.86 | **Strong.** Drop jokes, history asides, "fun facts", decorative images. |
| Signaling (cue structure) | 24/28, median d about 0.41 | **Moderate.** Headings that state the point, bold the key token, highlight the changed line. |
| Redundancy | 16/16, d about 0.86 (narration + identical on-screen text) | **Moderate for text.** Original studies are audio+text; translate as: don't restate the same code twice in words and again in a table. |
| Segmenting (learner-paced chunks) | 10/10, d about 0.79 | **Strong.** One concept per section; short code blocks; explicit stopping points. |
| Pre-training (names/characteristics of parts first) | 13/16, d about 0.75 | **Strong.** Define "variable", "call", "return" before the first program that uses all three. |
| Personalization (conversational "you/we") | 14/17, d about 0.79 | **Moderate.** Second person, direct address; not chattiness. |

## 4. Subgoal labelling

Margulieux, Guzdial & Catrambone (ICER 2012): App Inventor learners given worked examples whose step groups carried short labels ("create the component", "set the handler") completed more tasks, faster, and did better on a transfer task a week later than learners with identical unlabeled examples (n=40; https://doi.org/10.1145/2361276.2361291; details in Guzdial's summary https://computinged.wordpress.com/2012/06/05/instructional-design-principles-improve-learning-about-computing-making-measurable-progress/). Brown & Wilson make this Tip 6, noting labels let novices see that "highest rainfall from a list" and "first surname alphabetically" are the same problem (https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1006023). Strength: moderate (replicated by the same group across languages; modest samples).

## 5. Notional machines and misconceptions

Du Boulay (1986) coined the *notional machine*, the idealised model of what the computer does when it runs your program, and showed that novice errors about assignment and execution come from missing or wrong models, including over-extended mechanical analogies (https://doi.org/10.2190/3lfx-9rrf-67t8-uvk9). Sorva's review concludes that misconceptions, mental-model and threshold-concept research all point to the notional machine as "a major challenge" and that instructors should make it "an explicit learning objective" (https://dl.acm.org/doi/10.1145/2483710.2483713). The 2020 ITiCSE working group formalised how to describe one (https://doi.org/10.1145/3437800.3439202). Wilson gives a concrete example: "Every piece of data ... lives in memory divided between a call stack and a heap..." (https://teachtogether.tech/en/).

**A lesson must make explicit:** what happens when a line executes, in what order; what a variable *is* (a named box vs a label, chosen consistently); that `=` is an action not an equation; where values go when a function is called and returns; that the computer does not "know what you mean". Strength: strong that misconceptions are systematic; moderate that explicit teaching fixes them.

## 6. PRIMM and Parsons problems

- **PRIMM** (Predict, Run, Investigate, Modify, Make): 493 students aged 11 to 14 taught with PRIMM for 8 to 12 weeks outperformed 180 controls on a post-test (Mann-Whitney, p < .05, r about .13, a small effect) (https://suesentance.net/wp-content/uploads/2020/02/teaching_computer_programming_with_primm__a_sociocultural_perspective_author_copy.pdf; teacher study https://qmro.qmul.ac.uk/xmlui/bitstream/handle/123456789/61000/Waite%20Teachers%27%20Experiences%20of%20using%202019%20Published.pdf?sequence=2). Strength: moderate (non-equivalent controls, small effect). The *Predict* step is separately supported: Brown & Wilson report that demonstrations without prior prediction can be "useless or actively harmful" (Tip 4).
- **Parsons problems** (reorder jumbled lines): Ericson, Margulieux & Rick found 2-D Parsons with distractors took significantly less time than fixing or writing equivalent code, with no difference in learning or one-week retention (https://doi.org/10.1145/3141880.3141895); adaptive Parsons replicated "more efficient, just as effective" (https://dl.acm.org/doi/10.1145/3230977.3231000). Learners also attempt them more readily than nearby MCQs (Brown & Wilson Tip 10). Strength: moderate to strong for efficiency.

## 7. Retrieval, elaborative interrogation, self-explanation

Dunlosky et al. (2013) rated **practice testing** and **distributed practice** high-utility; **elaborative interrogation** ("why is this true?"), **self-explanation** and **interleaving** moderate; **rereading, highlighting, summarising, imagery** low (https://journals.sagepub.com/doi/10.1177/1529100612453266; accessible summary https://www.aft.org/ae/fall2013/dunlosky). Dunlosky notes self-explanation didn't change practice success but tripled transfer in one logic study (about 90% vs under 30%). Chi et al. (1989) found "good" learners spontaneously explain each step of a worked example and connect it to principles; "poor" ones don't (https://onlinelibrary.wiley.com/doi/10.1207/s15516709cog1302_1). A meta-analysis of *induced* self-explanation found reliable positive effects, moderated by prompt design (https://doi.org/10.1007/s10648-018-9434-x).

**Living inside prose:** a "what will this print?" line before each output (retrieval + prediction); "why does line 3 need to come before line 4?" after a block (self-explanation); a few recall questions at the end covering *earlier* material (distributed retrieval). Strength: strong for retrieval and spacing; moderate for self-explanation prompts.

## 8. Willingham: memory is the residue of thought; stories

"What ends up in a learner's memory ... is the product of what the learner thought about when he or she encountered the material" (https://www.aft.org/ae/summer2003/willingham). So examples must force thought about the *concept* (why the loop stops), not about the decoration (a cute pizza theme). Stories are "psychologically privileged", easier to comprehend and remember because readers expect **causality, conflict, complications, character**, and lessons can borrow that structure without being fiction (https://www.aft.org/ae/summer2004/willingham). Implication: one running scenario with a goal and obstacles ("the report is wrong because the total is reset inside the loop") beats a series of unrelated toy snippets. Strength: strong for the residue principle; moderate for narrative structure in expository text.

## 9. Brown & Wilson; Wilson; live coding vs static code

Brown & Wilson's ten tips relevant to text: use worked examples with labelled subgoals; make readers predict before revealing output; stick to one language; use authentic tasks; remember novices are not experts ("we teach reading with shorter books, simpler words and larger print"); don't just code, use Parsons problems (https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1006023). Wilson adds: faded examples, "never hesitate to sacrifice truth for clarity", and that redundancy is acceptable for non-native speakers (https://teachtogether.tech/en/).

**Live coding:** Rubin (2013) compared two live-coded and two static-slide sections of a C++ course and found live coding "at least as effective" and better on some measures (https://dl.acm.org/doi/10.1145/2445196.2445388). A 2021 literature review concludes empirical support remains limited and mostly self-report (https://dl.acm.org/doi/10.1145/3430665.3456382). The mechanisms Brown & Wilson credit (slowing down, showing mistakes and diagnosis) *can* be written: build the program in visible steps, include a deliberate error and its fix. Strength: weak to moderate.

## 10. Concreteness fading; analogies

Fyfe, McNeil, Son & Goldstone's review supports concrete, then semi-abstract, then symbolic sequences over either extreme, provided links between stages are explicit (https://eric.ed.gov/?id=EJ1036777). Gentner's structure-mapping: analogies transfer *relations*, and work when the correspondence is transparent and systematic; surface-similar but structurally different analogies mislead (https://groups.psych.northwestern.edu/gentner/papers/GentnerToupin86.pdf; https://loewenstein.web.illinois.edu/papers/Gentner&Loewenstein%20EncyEd03.pdf). Du Boulay documented exactly this for "variable = box" analogies. Strength: moderate; for analogies, use one, map it explicitly, and say where it breaks.

## 11. Readability formulas vs cohesion

Classic formulas (Flesch-Kincaid) proxy difficulty by sentence and word length only; cohesion-aware models (Coh-Metrix, TAACO, CAREC) predict comprehension and reading speed better for adults (https://doi.org/10.1111/1467-9817.12283; Crossley et al. 2017 https://bishtref.com/articles/10.1080/0163853x.2017.1296264) and for L2 readers (https://bishtref.com/articles/10.1002/j.1545-7249.2008.tb00142.x). McNamara & Kintsch: **low-knowledge readers learn more from highly coherent text** (explicit connectives, repeated referents, stated causal links); only high-knowledge readers sometimes gain from gaps (https://doi.org/10.1207/s1532690xci1401_1; https://doi.org/10.1080/01638530709336895). Implication: chopping sentences to hit a grade level can *remove* the connectives that novices need. Strength: strong that cohesion matters for novices; moderate that formulas are poor targets.

---

## Design implications (rules for a written beginner lesson)

1. Open each concept with a complete, line-by-line explained worked example before any exercise. **Strong**
2. Follow it with backward-faded versions: same task, last step blank, then last two, then from scratch. **Moderate**
3. Group example steps under short subgoal labels and reuse the same labels across examples. **Moderate**
4. Put the explanation physically next to the code it explains (interleave short blocks, inline comments, callouts); never a long listing then a distant walkthrough. **Strong**
5. One new idea per section; short code blocks (roughly 10 to 15 lines at most) with a clear stopping point. **Strong**
6. Pre-teach vocabulary and parts (what a variable, call, return is) before the first example that combines them. **Strong**
7. Cut everything not load-bearing: asides, trivia, decorative images, multiple ways to do it. **Strong**
8. Write in second person, plain conversational register. **Moderate**
9. State the notional machine explicitly: what executes when, what `=` does, where values live during a call. **Moderate to strong**
10. Before every shown output, ask the reader to predict it; then show it. **Moderate**
11. After key blocks, insert a self-explanation question ("Why must this line come first?") with a collapsed answer. **Moderate**
12. End sections with 2 to 4 recall questions that reach back to earlier sections (spaced retrieval). **Strong**
13. Use Parsons-style reorder tasks as early practice before free writing. **Moderate to strong**
14. Include PRIMM-style progression: read/predict, run, investigate, modify, make. **Moderate**
15. Use one running scenario with a goal, obstacle and resolution rather than unrelated snippets; make the thinking be about the concept, not the theme. **Moderate**
16. Show at least one realistic error, its message, and the diagnosis. **Weak to moderate**
17. Go concrete to abstract, and explicitly connect each stage. **Moderate**
18. At most one analogy per concept; map it explicitly and state where it breaks. **Moderate**
19. Optimise for cohesion (connectives, consistent terms, stated causal links), not for a grade-level score. **Strong**
20. Stick to one language and one idiom throughout. **Weak to moderate**

## Things commonly done that the evidence does not support

- Dumping the whole finished program first and explaining afterwards (split-attention; violates worked-example structure).
- "Try it yourself first" discovery for brand-new syntax (worked-example effect; Kirschner/Sweller line cited by Wilson).
- Rereading/summary boxes as the main review device (low utility per Dunlosky).
- Showing output without asking for a prediction (demonstrations alone can be useless or harmful).
- Fun asides, motivational trivia, decorative images (coherence principle, d about 0.86 against).
- Targeting a Flesch grade level by shortening sentences and dropping "because/so that" (harms low-knowledge readers).
- Keeping heavy scaffolding for readers who have already mastered the step (expertise reversal).
- Offering several alternative ways to write the same thing in a first lesson (extraneous load; "stick to one language").
- Assuming the learner already has the runtime model: never saying what actually happens when a line runs.
