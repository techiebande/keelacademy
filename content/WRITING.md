# Writing a Keel lesson

This is the whole writing guide. There is no style file behind it, no voice skill, no linter that enforces it. If you are about to write a lesson, read this once, then read one finished lesson (`content/units/phase-1/1.1.1/lesson.md` is the reference), then write. The reasons behind every rule here are in `docs/lesson-design.md` and the research under `docs/research/`.

## Who you are writing to

One person. They are an adult, they can use a computer, and they have never written a line of code. English may be their second or third language. They are reading on their own, probably at night, and there is nobody in the room to ask. They are smart. They are not familiar.

They cannot see this repository. They cannot see `content/client/`, `unit.yaml`, internal Markdown files, source code, agent instructions, or the author's notes. The lesson is the only briefing they receive. If the student needs to know a person, rule, file, number, path, or decision, state it in the lesson before using it. A source path is never a student instruction. A course-folder path is valid only when the assignment explicitly gives the student that artifact.

Everything below follows from taking that person seriously.

## The shape of a chapter

A lesson is a chapter, and a chapter has whatever shape its material needs. There is no template. But every good chapter does these things, and you should be able to point to where yours does each one.

**It opens with the problem and a promise.** In the first hundred words the reader learns what is wrong or missing right now, and what they will be able to do when they reach the end. Not "In this lesson we will cover variables." Rather: "Right now the support team at Lantern reads every customer message by eye and copies the order number into a spreadsheet by hand. By the end of this chapter you will have a program that reads a message file and pulls that number out for them." The promise is the contract; the chapter keeps it.

**It builds the thing in front of the reader, a few lines at a time.** You write two to twelve lines, you say what they do and why they are there, the reader sees them run, and only then do you write the next piece. If a program is forty lines long by the end, the reader has seen and understood every one of those forty lines before they see the whole file. The whole file appears once, at the end, so they have something to compare their own against.

**It shows before it names.** The reader sees `name = "Sarah"` and watches it work before the word *variable* appears. Then the word appears, in the same sentence or the next, and from then on you use that word and no other. Never "variable" in one paragraph and "identifier" or "binding" in the next. Beginners cannot tell a synonym from a new concept.

**It says what the computer does.** When you show `count = count + 1`, you say what actually happens: Python works out the right-hand side first, using the value `count` has right now, and then stores the result under the name `count`, replacing what was there. You say this even though it seems obvious to you, because it is not obvious to someone who has spent their life reading `=` as "equals". Most beginner bugs come from a wrong picture of what the machine does with a line. Give them the right picture, every time a new kind of line appears.

**It asks before it shows.** Before you show output, ask what the reader expects. Put the answer behind a fold so they have to commit:

```html
<details><summary>What do you think this prints?</summary>

`Sarah Johnson`, with a space, because `print` puts a space between the things you give it.

</details>
```

If the natural guess is wrong, say what the natural guess is and why the real answer is different. A prediction the reader gets wrong and then understands is worth a page of explanation.

**It lets something break.** Show the version a sensible person would write first. Let it fail. Paste the actual error, the whole thing, exactly as the terminal prints it. Then read the error together, line by line, and fix it. Students will spend most of their lives looking at error messages; the chapter is where they learn that an error message is information, not a verdict.

**It teaches one idea per section.** A section heading states the point of the section, in plain words, the way you would say it to a friend: "A name that remembers a value" rather than "Variables". Inside the section, one new idea. If you find a second one, you have found the next section.

**It ends by handing the reader work.** The last paragraph of the chapter points at the assignment: here is what we built, here is the piece I left for you, go. No summary. No "in this chapter we learned". The reader was there.

## The sentences

Write the way a careful person talks when they are explaining something they understand well to someone they respect.

**Connect your sentences.** Start with what the reader already has, end with what is new. "The program stores that number in `total`. `total` starts at zero, so after the first message it holds the price of the first refund." The second sentence picks up `total` from the end of the first. That is what makes text feel like it flows: not short sentences, connected ones. Keep "because", "so", "which means", "but", "then". A beginner needs the joints between ideas spelled out. Cutting them to make sentences shorter makes the text harder, not easier.

**Vary the rhythm because you mean to.** A long sentence that walks through a chain of cause and effect, then a short one that lands the point. A one-sentence paragraph when something matters. Text in which every sentence is the same length reads as manufactured, and it is tiring.

**Use the plain word.** "Use", not "utilize". "Is", not "serves as". "Because", not "due to the fact that". "Start", not "initialize", until you have shown initialization and named it. When a technical word is the right word, use it, after you have shown what it means. Do not avoid the words "software" or "computer" or "program"; the reader is here to learn programming.

**Address the confusion you know is coming.** "You might expect this to print 10. It prints 9, and the reason is worth a minute." "This next part trips up almost everyone, so go slowly." You know where the hard parts are. Say so, before the reader gets there, and slow down when you arrive.

**Say I when it is you.** "I prefer to name this `message_text`, because in a month `m` will mean nothing to you." Your judgment and your experience are part of what the reader is paying for. Use "we" when you and the reader are doing the work together. Use "you" for what the reader does or sees. Do not perform enthusiasm; if something is genuinely pleasing when it finally runs, one plain sentence saying so is enough.

**Say why, not just what.** Every rule you give the reader has a reason. Give the reason. "Put the imports at the top, so that anyone opening the file sees at a glance what it depends on." A rule without a reason is memorized and forgotten; a reason can be reconstructed.

## Code on the page

A code block is two to twelve lines when you are introducing something. The sentence before it says what to look at. The sentences after it say what happened, if that is not obvious from the output.

Output goes in its own block, fenced as `text`, immediately after the code that produced it, exactly as the terminal shows it. If you run `python3 read_message.py` and the terminal prints `Order 48213 from Sarah Johnson`, that is what the block contains. Not a paraphrase, not a tidied version. The tool `content/tools/run-lesson-code.py` will run your Python blocks and compare; if they disagree, the lesson is wrong.

Name things the way you want the reader to name things. `message_text`, not `s`. `order_number`, not `x`. The code in the chapter is the reader's model of what good code looks like.

When a block changes an earlier block, show only the changed part if the change is small and say where it goes ("replace the last line of the loop with this"), or show the whole function again if it is short. Never make the reader diff two long blocks by eye.

Use a comment in code only when the comment says something the code cannot: why, not what. Never explain code in comments that you also explain in prose beside it.

## What to leave out

Anything that is not carrying weight. Fun facts. History, unless the history is the reason a design is the way it is. Analogies beyond one per concept, and that one you map explicitly and say where it breaks. A second way of doing the same thing, in a first lesson. Diagrams, unless the relationship is genuinely spatial and hard to say. Jokes that need a beat. Motivational asides about how this will be useful someday. Bullet lists for things that are not lists. Bold on words that are not the one term being introduced.

Anything that talks about the lesson instead of the subject. "In this section we will explore." "As mentioned above." "Now that we have covered X, let's turn to Y." "It's important to note that." The reader can see what section they are in. Just say the thing.

Anything that summarizes what was just said. Recaps, key-takeaway boxes, "to sum up". If the reader needs to hold a fact, ask them for it later as a recall question. Rereading a summary is one of the least effective ways to remember anything; being asked a question days later is one of the most.

## The assignment

The assignment is the chapter's program, on the client's real files, with the last piece missing. In `assignment.md` you tell the reader, in prose, what the finished program does, which files in `starter/` they are given, what is left for them to write, and how they will know it works. Then you say how the checks work: what each one looks at and what its message means. Then a section for where people get stuck, with a heading per snag and a fix under each; those headings are what `unit.yaml` points at.

Write the assignment after the chapter and in the same voice. It is the chapter's last paragraph continued, not a form.

## Recall questions

In `unit.yaml`, under `practice.retrieval_seeds`, write four to eight questions the platform will ask the student from memory after the chapter and again days later. Real questions, with a reference answer: "What does `=` do in Python, and why is the word 'equals' misleading?" Not facts to be recognized: "Variables store values." A good recall question makes the student explain the mechanism in their own words. The tutor grades against the chapter, so ask only what the chapter taught.

## Before you call it done

Run the code tool. Then read the whole chapter aloud, or as close to aloud as you can manage, from the top, as the person described at the start of this guide. Every place you stumble, they will stop. Fix those. Then give it to the first reader.

The signs that a chapter was assembled rather than written, so you can check for them yourself (the full catalogue with sources is `docs/research/03-machine-written-tells.md`): sentences all the same length; one sentence per line; "First, Second, Third, Finally"; a question answered in the next sentence with no pause; three of everything; "not just X but Y"; "serves as", "plays a key role", "robust", "delve", "crucial", "landscape"; a paragraph that ends by restating its first sentence; a closing that summarizes; anything that says "this lesson" or "this section". One of these is nothing. Five in a page is a chapter that needs rewriting, not editing.
