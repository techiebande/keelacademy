# Evidence brief 2: how clear explanatory technical prose is actually written

Compiled 2026-09-12 for the lesson-system redesign. Part A summarises primary texts fetched directly where possible (Gopen & Swan, Orwell, Pinker's WSJ adaptation, McEnerney transcript); Williams and Zinsser are drawn from published excerpts and notes. Part B is based on fetching one full chapter or post from six exemplars and running word and line counts on the fetched text (figures are approximate). The synthesis is in `docs/lesson-design.md`.

---

## Part A: craft scholarship

### Gopen & Swan, "The Science of Scientific Writing" (1990)
Source: https://cseweb.ucsd.edu/~swanson/papers/science-of-writing.pdf (reprint of the American Scientist article)

Core thesis: "Readers do not simply read; they interpret," and they interpret partly from *where* information sits in a sentence. Length is not the problem: "Long sentences need not be difficult to read; they are only difficult to write." The seven concrete principles they state at the end:

1. Follow a grammatical subject as soon as possible with its verb.
2. Put the "new information" you want emphasized in the **stress position** (sentence end).
3. Put the person or thing whose "story" the sentence tells at the start: the **topic position**.
4. Put appropriate **old information** in the topic position "for linkage backward and contextualization forward."
5. Articulate the action of every clause in its verb.
6. Provide context before asking the reader to consider anything new.
7. Make structural emphasis coincide with substantive emphasis.

They explicitly warn these are not rules: "Our best stylists turn out to be our most skillful violators."

### Joseph Williams, *Style: Toward Clarity and Grace*
Sources: excerpt in Michigan Bar Journal https://www.michbar.org/file/generalinfo/plainenglish/pdfs/92_jan.pdf ; notes https://www.june.kim/reading/prose-writing/williams-1981/

- **Characters as subjects, actions as verbs.** Readers judge prose clear when the grammatical subject names a concrete character and the verb names its key action. "Our lack of knowledge precluded determination" becomes "We could not determine."
- **Nominalizations** (decision, allocation, establishment) bury both actor and action; diagnostic: underline every subject and check whether it is a character.
- **Cohesion (given-new):** begin sentences with what the previous sentence made familiar; end with the new.
- **Coherence (topic strings):** a passage feels unified when the subjects of consecutive sentences form a short, consistent set of topics rather than shifting each sentence.

### Steven Pinker, *The Sense of Style* / "The Source of Bad Writing"
Source: https://stevenpinker.com/files/pinker/files/the_source_of_bad_writing_-_wsj_0.pdf ; https://news.harvard.edu/gazette/story/2012/11/exorcising-the-curse-of-knowledge/

- "Call it the Curse of Knowledge: a difficulty in imagining what it is like for someone else not to know something that you know."
- Mechanism: the expert "doesn't bother to explain the jargon, or spell out the logic, or supply the necessary detail," because the missing steps "seem too obvious to mention."
- "We do not notice the curse because the curse prevents us from noticing it." Remedies: show drafts to representative readers; let time pass before re-reading.
- **Classic style** (from Thomas & Turner, adopted by Pinker): the writer has seen something and directs the reader's gaze to it, as if in conversation; prose is a window onto the world, not a record of the writer's hedging or process.

### Larry McEnerney, "The Craft of Writing Effectively"
Source: transcript https://singjupost.com/the-craft-of-writing-effectively-larry-mcenerney-transcript/ ; video https://www.youtube.com/watch?v=vtIzMaLkCaM

- Writers use text to think; readers use text to change how they see the world: "you generate a text on the horizontal axis, but whether it does its job depends on the vertical axis."
- "There's no such thing as value here [in the text]. Value is here [in readers]... which is why it's so much about readers and not about content."
- Most school writing opens in "the mode of explanation"; valuable writing opens with **instability**: "tension. Challenge. Contradiction. Red flag", a problem the reader's community cares about.

### Zinsser and Orwell
Zinsser, *On Writing Well*: https://richardcolby.net/writ2000/wp-content/uploads/2017/09/On-Writing-Well-30th-Anniversa-Zinsser-William.pdf ; notes https://calvinrosser.com/notes/on-writing-well-william-zinsser/
- "Clutter is the disease of American writing": cut qualifiers, adverbs that duplicate verbs, long words where short ones do.
- **Unity:** decide one point, one tense, one pronoun, one attitude per piece.
- **The lead** must do real work; the most important sentence is the first. **The ending** should leave the reader with a single fresh thought, not a recap.

Orwell, "Politics and the English Language": https://www.orwellfoundation.com/the-orwell-foundation/orwell/essays-and-other-works/politics-and-the-english-language/
Six rules: never use a stale metaphor; never a long word where a short one will do; if you can cut a word, cut it; never passive where active works; never jargon "if you can think of an everyday English equivalent"; "Break any of these rules sooner than say anything outright barbarous."

### Plain-language research and readability formulas
- The Coh-Metrix L2 Reading Index (word frequency, sentence similarity, content-word overlap) classified simplified texts far better than Flesch-Kincaid, which reached about 48% accuracy overall and 22% on intermediate texts: https://files.eric.ed.gov/fulltext/EJ926371.pdf
- Semi-automated simplification (Acrolinx) lowered Flesch-Kincaid grade but **did not improve recall** for lay readers; the authors attribute this to cohesion not being improved: http://doras.dcu.ie/23796
- Eye-tracking with 37 adult L2 readers: linguistic simplification improved comprehension mostly for lower-proficiency readers; narrative organization aided recall: https://onlinelibrary.wiley.com/doi/10.1111/jcal.12517
- Plain-language abstracts increased understanding and reader confidence among 170 undergraduates: https://pmc.ncbi.nlm.nih.gov/articles/PMC8430246/
- Topic familiarity determines whether simpler summaries help; simplification tends to drop details: https://arxiv.org/pdf/2403.04979

**Takeaway:** shortening sentences to hit a grade-level target is a surface fix. What the evidence supports for non-native readers is (a) familiar, high-frequency words, (b) referential cohesion (repeating key nouns rather than varying them), (c) explicit connectives, and (d) narrative or concrete framing, with FK used only as a diagnostic, never an authoring goal.

---

## Part B: close reading of exemplars

Counts below are from the fetched text of one chapter or post each.

| Exemplar (text fetched) | Prose words | Code blocks | Median block (lines) | Max block | Prose words per code line | Median paragraph (words) | Mean sentence (words) | Questions | "I" | "we/let's" | "you" |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Nystrom, *Crafting Interpreters* ch. 4 Scanning | 4,700 | 69 | 2 | 20 | 15 | 32 | 16 | 15 | 12 | 152 | 43 |
| Haverbeke, *Eloquent JS* ch. 2 | 4,800 | 39 | 4 | 13 | 27 | 41 | 18 | 2 | 11 | 31 | 83 |
| Rust Book ch. 2 Guessing Game | 5,100 | 36 | 10 | 30 | 12 | 40 | 19 | 1 | 0 | 86 | 93 |
| Nielsen, *NN&DL* ch. 1 | 15,000 | 19 | 3 | 128 | 52 | 86 | 20 | 47 | 60 | 382 | 94 |
| Evans, "Examples of floating point problems" | 2,400 | 12 | 3 | 11 | 49 | 27 | 20 | 4 | 30 | 23 | 37 |
| Ciechanowski, "Gears" | 4,800 | 0 (interactive figures) | n/a | n/a | n/a | 40 | 27 | 0 | 18 | 48 | 35 |

### Bob Nystrom, *Crafting Interpreters*, "Scanning"
Source: https://craftinginterpreters.com/scanning.html
- **Opening:** definition first, then a promise: "By the end of this chapter, we'll have a full-featured, fast scanner..."
- **Code introduction:** 69 tiny snippets, median 2 lines, each labeled with file and location ("in *identifier*(), replace 1 line"). Prose precedes code and states its purpose; code is then re-explained only where non-obvious. A 20-line file is the largest chunk.
- **Jargon:** term appears bold at first use immediately after a concrete example: "`var language = \"lox\";`... Here, `var` is the keyword", then "lexemes." Principle named after being shown: "**maximal munch**... whichever one matches the most characters wins."
- **First person/opinion:** rare "I" in the body, frequent "we"; opinion is quarantined in a Design Note: "It's a mess... don't do what JavaScript did."
- **Transitions:** anticipates the reader's state: "Stick that in a text file... I'll be right here when you're ready. Good? OK!"
- **Errors:** a full subsection on error handling, justified pragmatically: "if you care about making a language that's actually *usable*..."
- **Ending:** an instruction to test ("Fire up the REPL... Does it produce the tokens you expect?"), then numbered Challenges, then the Design Note. No summary.
- **Rhythm:** paragraphs of 4 to 97 words; jokes shorten sentences: "a `switch` statement with delusions of grandeur."

### Marijn Haverbeke, *Eloquent JavaScript*, ch. 2
Source: https://eloquentjavascript.net/02_program_structure.html
- **Opening:** an epigraph, then an analogy carried from ch. 1: moving "beyond the nouns and sentence fragments... to express meaningful prose."
- **Code:** median 4 lines; a deliberately bad version first ("console.log(0); console.log(2);...") then "That works, but the idea of writing a program is to make something *less* work, not more."
- **Jargon:** italicized at definition, always after the concept is motivated: "A fragment of code that produces a value is called an *expression*."
- **Opinion, lightly:** "I like to use two spaces for every open block, but tastes differ."
- **Transitions:** sections open with questions in the reader's voice: "How does a program keep an internal state? How does it remember things?"
- **Errors:** anticipates them: "When creating a binding produces an unexpected syntax error, check whether you're trying to define a reserved word."
- **Ending:** an explicit **Summary** section restating what "You now know," then exercises with hints.

### The Rust Programming Language, ch. 2
Source: https://doc.rust-lang.org/book/ch02-00-guessing-game-tutorial.html
- **Opening:** states the payoff list ("You'll learn about `let`, `match`, methods...") and describes the finished program in plain words before any code.
- **Code:** largest chunks of the set (median 10 lines, max 30); the *same* program is re-shown growing, and shown full at the end ("Listing 2-6: Complete guessing game code"). Every listing is followed by a line-by-line walk.
- **Jargon:** defined at use with a forward pointer: "*Shadowing* lets us reuse the `guess` variable name... We'll cover this in more detail in Chapter 3."
- **Voice:** zero "I"; "we" and "you" throughout, staged as a dialogue: "But wait, doesn't the program already have a variable named `guess`?"
- **Errors:** compiler output is pasted verbatim ("error[E0308]: mismatched types") and read as a teaching object.
- **Ending:** "Congratulations!" plus a bridge paragraph listing what the next four chapters cover.

### Michael Nielsen, *Neural Networks and Deep Learning*, ch. 1
Source: http://neuralnetworksanddeeplearning.com/chap1.html
- **Opening:** a concrete image and an inversion of expectation: "Most people effortlessly recognize those digits as 504192. That ease is deceptive."
- **Code:** withheld until about two-thirds through; then explained class by class ("Let me explain the core features... before giving a full listing") and finally dumped as one 128-line listing.
- **Jargon:** named after intuition; terminology is judged: "I'm not going to use the MLP terminology in this book, since I think it's confusing."
- **Questions:** 47, the highest rate, used as pacing devices; interleaved "Exercises" and "Problems."
- **Paragraphs** are long (median 86 words) but sentence length stays around 20.
- **Ending:** a forward-looking analogy (deep nets compared to function calls in programming languages) rather than a recap.

### Julia Evans, "Examples of floating point problems"
Source: https://jvns.ca/blog/2023/01/13/examples-of-floating-point-problems/
- **Opening:** first person and motive: "Hello! I've been thinking about writing a zine..." then "I find all of this a little abstract... I really wanted some specific examples."
- **Structure:** table of contents up front; each section is one real bug, reproduced in 11 lines or fewer of C/Python with printed output.
- **Jargon:** deferred: "I'm not going to write a long explanation of how floating point works", with a link to a comic.
- **Bugs as content:** each example ends with a stated lesson: "instead of checking for float equality, usually you want to check if two numbers are different by some very small amount."
- **Ending:** candid about scope: "we've already written 2000 words and I'm going to just publish this."

### Bartosz Ciechanowski, "Gears"
Source: https://ciechanow.ski/gears/
- **Opening:** personal fascination, then a two-sentence contract: "I'll explain how gears affect the properties of rotational motion and how the shape of their teeth is way more sophisticated..."
- **Concept introduction:** everyday object first ("a cool breeze from a desk fan"), interactive figure, then the term in italics: "we use the term *angular velocity*."
- **Transitions:** each section ends by naming a loose thread: "However, it's not all this contraption is doing." Then "# Torque."
- **Directing attention:** "You may have already noticed that some of those points move more than the others..."
- **No questions, no code**; longest sentences of the set (mean 27) because figures carry the load.
- **Ending:** "Final Words" admits idealization ("The physical world is messy") and restates the one big idea.

---

## What the exemplars have in common

1. **A contract in the first 150 words**: what you will be able to do or see by the end (Nystrom, Rust, Ciechanowski, Haverbeke all do this explicitly).
2. **Concrete before abstract**: a line of code, a fan, six digits, then the term, italic or bold, in the same or next sentence. Definitions never precede examples.
3. **Small code chunks**: median 2 to 4 lines in the book chapters written by single authors; only the Rust book routinely exceeds 10, and it compensates with line-by-line commentary.
4. **Prose dominates**: 12 to 50 words of explanation per line of code; never a code dump without a preceding sentence saying what to look for.
5. **Bad version first**: the naive or broken program appears before the correct one (Haverbeke's seven `console.log`s; Rust's paste of a compiler error; Evans's failing loop).
6. **Compiler/runtime errors are quoted verbatim** and treated as evidence, not embarrassment.
7. **"We" and "you" outnumber "I" by 3 to 10x** in the books; blog posts (Evans, Ciechanowski) use "I" freely for motive and opinion but still switch to "we/let's" when doing the work.
8. **Opinion is signposted and confined**: Design Notes, "tastes differ," "I think it's confusing", never smuggled into definitions.
9. **Transitions name an unresolved thread** rather than announcing a heading ("it's not all this contraption is doing"; "But wait, doesn't the program already have...").
10. **Questions are used as pacing**, at wildly different rates (0 to 47 per chapter); they are a stylistic choice, not a requirement.
11. **Paragraphs vary 4 to 130 words**, with one-sentence paragraphs used for emphasis; sentence means cluster at 16 to 20 words with maxima of 45 to 75.
12. **Endings assign action**: test it, do the challenges, read the next chapter. Only Haverbeke writes a formal "Summary"; the rest end on an instruction, an admission of scope, or a forward analogy.
13. **Forward pointers instead of digressions**: "We'll cover this in Chapter 3" appears in every book chapter.
14. **Everyday-word vocabulary with technical terms kept sparse and stable**: the same noun is repeated rather than varied, matching the cohesion evidence in Part A.

## What none of them do

- Open with a definition, history, or "In this chapter we will discuss..." without stating a payoff.
- Present a code block longer than a screen without first saying what to look at.
- Introduce a term before the reader has seen the thing it names.
- Hide mistakes: none show only the finished, working artifact.
- Use hedging or passive constructions for authorial cover ("it is generally considered...").
- Pad the ending with a recap of headings; none restate the outline as a summary (Haverbeke summarizes *ideas*, not sections).
- Vary synonyms for the same object ("the scanner / the lexer / the tokenizer"): every term is fixed on first use.
- Address the reader with generic enthusiasm ("Exciting!") disconnected from a specific result; exclamation is tied to something the reader just made work.
