# TRIAL DRAFT — Unit 1.1 learn-phase opener (keel-unit + keel-copy trial)

Status: scratch evaluation draft. NOT wired into content/ (no unit.yaml,
no checks, no rubric). Purpose: let the human judge voice + markers on a
real upcoming unit before C1b production. Delete or promote after review.

Trial seeds (invented for this draft only):
1. why stringly-typed dispute dicts fail silently at pipeline scale
2. how dataclasses move the shape promise into code the checker enforces
3. where the parse boundary sits in load-validate-normalize-export

---

# Unit 1.1: Python for AI Engineering

::: phase learn

Your dispute parser works. Feed it ten tidy JSON files and it hands back a
CSV you can open in four seconds. That is genuinely useful — and it is
also the last time in this program your data will ever be that polite.

Everything after this wants shapes. The FastAPI endpoint wants a body it
can reject. The extractor wants fields it can switch on. The audit log
wants rows it can replay. Not one of them can read your intentions.

So the parser has to stop trafficking in bare dicts. That part is
obvious. The part that costs people a week is the next question: where
does the promise about a record's shape actually get kept — in your head,
or in your code?

> **Predict, then check.** You parse a dispute into a plain dict and pass
> it straight to the credit calculator. It works on the first ten files,
> so you point it at a hundred real merchant reports.
>
> How many distinct ways does it come apart?
>
> Hint 1: Think about what `amount` looks like when a warehouse clerk
> typed it by hand.
> Hint 2: Think about what happens three functions later, nowhere near
> the line that caused it.

At least four, and not one of them is Python malfunctioning. The amount
arrives as `"$40k"` and your multiplication quietly produces nonsense.
A key is `claimType` in one file and `claim_type` in the next, so a
lookup returns `None` and the record sails on, wrong. A missing severity
becomes a falsy zero and sorts the dispute into the wrong queue. And the
expensive one: everything type-checks in your head, nothing checks it on
the machine, so the crash lands three functions from the cause and the
traceback blames the victim.

Hold on to that last one. We come back to it.

## Why bare dicts betray you at pipeline scale

### What your program actually receives

Back when I was first writing parsers, I loved dicts. They never said
no. Any key, any value, no paperwork. It felt like speed — and for ten
files, it was.

Then file eleven arrives with `"amount": "40k-ish, waiting on recount"`
and my pipeline does exactly what I told it to do, which was nothing in
particular. A dict doesn't know what an amount is. It holds strings the
way a shoebox holds receipts.

**A dict with the right keys is not a Dispute. A Dispute is a shape your
code enforces.**

Read that twice, because it is the whole unit. With a bare dict, the
contract about a record's shape exists only as a hope in the author's
head. I call that *hope-typed* — my own word, and you will see why it
stings. Nothing enforces it, and nothing is even checking.

### How checked shapes change who finds the bug

Look again at the four failures above and notice what they share. Every
one is Python behaving inside normal variation for dynamic code. You are
not catching Python misbehaving. You are catching it behaving exactly as
advertised, while you hoped it would not.

Here is an experiment worth running on code you have already written.
Take your dict-based parser, feed it the messy hundred, and count how
many failures surface at the parse line versus three functions later.
For most first drafts the answer is nearly zero at the parse line. That
distance — between where bad data enters and where it explodes — is the
real defect. Checked shapes (dataclasses today, Pydantic from here on)
collapse that distance to zero: bad data dies at the boundary, holding
the offending input in its hand, with a named reason.

::: aside Can't I just validate with a few ifs?
You can, and plenty of shipped code does: a length check here, a
`try/except KeyError` there, and a comment that says "TODO: proper
validation".

It buys a few percentage points and costs you the thing you needed most,
which is one place where the shape is defined. Scattered ifs rot —
every new field adds a new place to forget. Define the shape once, at
the boundary, and let every downstream function assume it. That is what
the `Dispute` dataclass in the worked example is for.
:::

### The pipeline shape you will reuse all year

Checked data wants a checked route through your program. Ours is four
small functions, and you will see it in every unit from here on:

**load → validate → normalize → export.**

Load reads bytes. Validate enforces the shape and either returns a real
`Dispute` or a named failure — never a hopeful dict. Normalize converts
("40k" becomes `40000` with low confidence flagged, never silently).
Export writes rows a stranger's system can read. Each step takes the
previous step's proven output, so a failure always points at its cause.

> **Predict, then check.** A nightly job parses 20 dispute files and
> writes them to the review queue. Someone wraps the whole pipeline in
> `try/except Exception: continue` to stop it paging them at 3am. It
> works, and the job has not failed once in six weeks.
>
> What did that cost, and when does the invoice arrive?

Nineteen files a night reach the queue and one does not exist anywhere.
The cost is unreviewed merchant claims, and the invoice arrives when a
merchant disputes a balance or a rebate deadline expires — whichever
comes first — and then a second time when somebody reconstructs six
weeks of dropped records from raw inbox files. The exception was never
the problem. The silence was.

### The version you should be able to say out loud

Bare dicts fail silently because the shape promise lives only in your
head. Move it into code: define the record once as a checked type,
enforce it at the boundary where data enters, and make every downstream
step assume it. When input is bad — and over enough messy merchant data
it will be — fail there, loudly, with the input and the reason attached.

::: recap The contract in one line
Hope-typed data is unparseable because the promise lives only in prose
(or your head). Define the shape once, enforce it at the boundary, and
let bad input die there with its name on. That keeps every downstream
function honest.
:::
