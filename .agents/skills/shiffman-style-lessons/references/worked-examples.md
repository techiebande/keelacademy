# Worked examples: before / after

Two full transformations on common early-curriculum topics. Read these when you want a concrete target to calibrate against, not just the abstract principles. Both "after" versions follow the lesson shape from SKILL.md: hook → naive plan → incremental build → snag → fix/insight → zoom out → challenge.

---

## Example 1: `for` loops

### Flat / generic version (what to avoid)

> **For Loops**
>
> A for loop is a control structure that allows you to execute a block of code multiple times. It consists of three parts: initialization, condition, and increment. Here's the basic syntax in JavaScript:
>
> ```js
> for (let i = 0; i < 5; i++) {
>   console.log(i);
> }
> ```
>
> In this example, the loop starts with `i = 0`, checks whether `i < 5`, executes the code block, and then increments `i` by 1. This process repeats until the condition is false. For loops are useful whenever you need to repeat an action a known number of times, such as iterating over an array.
>
> **Key Takeaways:**
>
> - For loops have three parts: initialization, condition, increment
> - The loop continues as long as the condition is true
> - Use for loops when you know how many times to repeat

### Shiffman-style rewrite

> Say you need to print the numbers 1 through 5. Easy:
>
> ```js
> console.log(1);
> console.log(2);
> console.log(3);
> console.log(4);
> console.log(5);
> ```
>
> Fine. Now say you need 1 through 100. Are you going to write `console.log` a hundred times? ...Please don't. There's a better way, and once it clicks, you'll wonder how you lived without it.
>
> Think about what's actually happening when you count from 1 to 5: you start somewhere, you do something, you check whether you should keep going, and if so, you move to the next number and do it again. That's the whole idea. Let's write that in code.
>
> ```js
> for (let i = 0; i < 5; i++) {
>   console.log(i);
> }
> ```
>
> Let's run that and see what we get:
>
> ```
> 0
> 1
> 2
> 3
> 4
> ```
>
> Wait — that's not what I wanted. I wanted 1 through 5, and I got 0 through 4. Classic. This happens to basically everyone the first week of learning loops, so if you spotted the mismatch before I even ran it, congratulations, you're paying attention.
>
> So what happened? `i` starts at `0` — that's `let i = 0`. And the loop stops the moment `i < 5` is no longer true, which cuts it off right before `i` hits `5`. Two separate decisions, two separate off-by-one traps, and they compounded on us.
>
> Let's fix both:
>
> ```js
> for (let i = 1; i <= 5; i++) {
>   console.log(i);
> }
> ```
>
> `1, 2, 3, 4, 5`. There we go.
>
> Zoom out for a second: those three pieces in the parentheses — start, keep-going condition, what-changes-each-time — are the whole loop. Everything else is just decoration around that idea. Whether you're counting to 5 or walking through a 10,000-item list, it's the same three questions: where do I start, when do I stop, what changes in between.
>
> Your turn: write a loop that counts backward from 10 to 1 using the same three ingredients, just flipped. Then try one that only prints the even numbers. I want to see what you land on.

**What changed:** naive-plan-first instead of definition-first; a real off-by-one bug shown and investigated rather than a pre-corrected example; sparse, earned reactions ("wait — that's not what I wanted") instead of neutral narration; a zoom-out paragraph instead of a bullet recap; an open-ended challenge instead of "the end."

---

## Example 2: recursion

### Flat / generic version (what to avoid)

> **Recursion**
>
> Recursion is a technique where a function calls itself in order to solve a problem. A recursive function typically has two parts: a base case, which stops the recursion, and a recursive case, which calls the function again with a modified input. Here is an example that calculates a countdown:
>
> ```js
> function countdown(n) {
>   if (n <= 0) return;
>   console.log(n);
>   countdown(n - 1);
> }
> ```
>
> When `countdown(5)` is called, it prints 5 and then calls `countdown(4)`, and so on until it reaches the base case. Recursion is useful for problems that have a naturally recursive structure, such as tree traversal or calculating a factorial.
>
> **Key Takeaways:**
>
> - Recursive functions call themselves
> - Every recursive function needs a base case
> - Recursion can replace loops for certain problems

### Shiffman-style rewrite

> Here's a strange idea: what if a function could call itself?
>
> I know how that sounds — like it should loop forever, or break something, or maybe summon a small paradox. It doesn't, if you're careful, and it turns out to be one of the more useful tricks in programming. This is genuinely one of those ideas that takes a couple of tries to feel natural. It took me a few tries too, and I've been teaching it for years.
>
> Let's count down from 5 to 1. With a loop, easy:
>
> ```js
> for (let i = 5; i >= 1; i--) {
>   console.log(i);
> }
> ```
>
> Now let's do the exact same thing with a function that calls itself instead:
>
> ```js
> function countdown(n) {
>   console.log(n);
>   countdown(n - 1);
> }
>
> countdown(5);
> ```
>
> Before you run that — what do you think happens? Take a second and actually guess.
>
> If you guessed "it explodes," you're right. Run it and you'll get a wall of numbers rocketing past zero into the negatives until JavaScript gives up: `Maximum call stack size exceeded`. We told the function to call itself, but we never told it when to _stop_. It's a loop with no exit condition, just wearing a different outfit.
>
> Every recursive function needs a moment where it looks at what it's holding and says "nope, done, not calling myself again." That's the base case. Let's add one:
>
> ```js
> function countdown(n) {
>   if (n <= 0) return;
>   console.log(n);
>   countdown(n - 1);
> }
>
> countdown(5);
> ```
>
> `5, 4, 3, 2, 1`. There we go.
>
> So what's actually happening? Each call to `countdown` doesn't know or care about any of the other calls — it does one small job (print the number, then hand off a slightly smaller version of the problem to itself) and trusts the next call to handle the rest. That's the real shift recursion asks of you: instead of controlling the whole repetition yourself, the way a loop does, you solve one layer and hand the rest to a version of yourself with a little less work to do.
>
> This is exactly the shape of counting nested folders, walking a family tree, or computing a factorial — some problems are built out of smaller copies of themselves, and recursion just lets the code mirror that shape directly instead of forcing it into a loop.
>
> Your turn: use the same base-case-plus-recursive-call pattern to write a function that adds up every number from 1 to `n`. Get it working, then break it on purpose — call it with a negative number and see what actually happens. I'd bet it doesn't do what you want on the first try. Go find out why.

**What changed:** the "it explodes" failure is shown running, not just described in the abstract; the base case is _arrived at_ because something broke, not stated as a rule up front; one honest aside ("it took me a few tries too") instead of a confidence-projecting tone; the closing challenge stages a second, self-directed bug hunt instead of ending at "it works."
