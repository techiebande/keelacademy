# Voice guide: phrase bank and do/don't table

Use this when you're drafting sentences and want concrete phrasing to reach for, rather than re-deriving tone from the principles in SKILL.md each time. These are patterns to riff on, not a script to insert verbatim — reusing the exact same line in every lesson is its own tell.

## Predicting before revealing

- "Before I run this — what do you think is going to happen?"
- "Take a guess. I'll wait."
- "My gut says this prints [X]. Let's find out if my gut is right."
- "If you had to bet, would you say this loop runs three times or four?"

## Reacting to output (use sparingly — one or two real ones per lesson)

- "Okay — that's not what I expected."
- "Huh. That's actually kind of interesting, let's look at why."
- "There we go, that's the shape I wanted."
- "Wait, that number looks wrong — let's back up."
- "Nice, okay, that's working now."

## Narrating a build, step by step

- "So the first thing I need is some way to keep track of..."
- "Let's just try the simplest possible version of this first."
- "I'm going to guess this isn't quite right, but let's see what it gives us."
- "Okay, next problem: right now this only works for one [thing] — what if I have a bunch of them?"
- "Let's not worry about that yet — I'll come back to it."

## Naming confusion honestly

- "This is the part that trips almost everyone up the first time, myself included."
- "If this doesn't click yet, that's completely normal — it took me a while too."
- "I'm going to explain this twice, two different ways, because one way rarely lands the first time."
- "Don't worry about fully understanding [X] yet — just watch what it does, and the 'why' will come."

## Transitioning between ideas (avoid corporate transitions — see don't list)

- "Okay, so that works — but here's where it gets interesting."
- "Now — here's a question that's going to break what we just built."
- "Let's push on this a little and see where it falls apart."
- "That's the easy version. Here's the version that actually shows up in real code."

## Inviting experimentation

- "Try changing that `3` to a `10` and see what happens before you keep reading."
- "Go ahead and break this on purpose — comment out that line and run it again."
- "What happens if you flip that condition? Try it before you scroll."

## Closing with a challenge, not a summary

- "Your turn: make it do [related but different thing]. There's more than one right way — I'd genuinely like to see what you come up with."
- "Take this and push it further: what if there were three of them instead of one?"
- "I'm curious what breaks when you try [X] — go find out."

## Self-deprecating / human asides (use at most one per lesson)

- A brief, plausible admission of not being the "math person" in the room, while still teaching the math clearly.
- A short, specific-sounding aside about prepping the lesson ("I actually got this wrong the first time I wrote this example...").
- Keep these short — one sentence, then back to the lesson. They're seasoning, not a subplot.

---

## Do / don't table

| Don't (flat/AI-flavored)                                             | Do (this style)                                                                                                                                              |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| "In this lesson, we will explore how for loops work."                | "Let's say you need to print the numbers 1 through 100. Are you going to write `print` a hundred times? ...Please don't. Let's find a better way."           |
| Presents final, correct code immediately.                            | Shows a first attempt, runs it, reacts to what happens, _then_ arrives at correct code.                                                                      |
| "It is important to note that off-by-one errors are common."         | "This is going to be off by one. It always is, the first time. Let's find out which direction."                                                              |
| "Now that we've covered loops, let's move on to arrays."             | "Okay, loops are solid. But there's a problem they can't solve yet — what if I don't just want to repeat something, I want to _remember_ a bunch of things?" |
| Generic variable/example names: `foo`, `data`, `Widget`, `Employee`. | Names with a little life: a `wanderer`, a `mood`, a stack of pancakes, a conga line of array elements.                                                       |
| Ends with a bulleted "Key Takeaways" recap.                          | Ends with an open-ended challenge or a "go try this" prompt.                                                                                                 |
| Uniform, hedged, textbook-neutral tone throughout.                   | Real variation: flat and clear when explaining, a little charged when something surprising happens, plainly honest when something is hard.                   |
| Apologizes for or hides a mistake in example code.                   | Treats the mistake as the actual teaching moment and investigates it in the open.                                                                            |
| Exclamation points on every sentence.                                | Exclamation points reserved for the one or two moments that are actually a little exciting.                                                                  |

---

## Vocabulary substitutions (prefer the right column on first use)

The audience includes non-native English speakers. On **first use**, prefer the plain alternative. After you have explained a term once, you can use the short form freely.

| Formal / Academic           | Plain alternative                                     |
|-----------------------------|-------------------------------------------------------|
| velocity                    | speed                                                 |
| latency                     | delay                                                 |
| pipeline                    | process, system, flow                                 |
| ingestion                   | reading in, taking in, loading                        |
| normalization               | cleaning up, making consistent                        |
| reconciliation              | matching, cross-checking                              |
| escalation                  | sending to a human, flagging for review               |
| auditability                | being able to check and prove every step              |
| statutory                   | required by law, legally required                     |
| fiscal discipline           | keeping money under control                           |
| conforming                  | clean, normal, standard                               |
| autonomous                  | automatic, on its own                                 |
| verbatim                    | word-for-word, exact                                  |
| attribution                 | linking back to, citing                               |
| governance                  | rules, oversight                                      |
| enterprise                  | large company, business                               |
| immutable                   | cannot be changed, permanent                          |
| deterministic               | predictable, same every time                          |
| substantive                 | real, meaningful                                      |
| infrastructure              | the system, the setup, the tools                      |
| quantitative                | number-based, measured                                |
| trilemma                    | three-way conflict, three-way tug-of-war              |
| lifecycle                   | from start to finish, full journey                    |
| bottleneck                  | slowest point, chokepoint, jam                        |
| compliance                  | following the rules                                   |
| idempotent                  | safe to repeat, same result every time                |
| ephemeral                   | temporary, short-lived                                |
