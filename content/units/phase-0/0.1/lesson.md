# Twenty minutes with one customer's message

On the morning of 3 September, a message arrived in the support inbox at Lantern Home. It was from a customer called Emily Carter, and it said her new kettle had come with a cracked lid. She had attached a photo. She wanted a replacement or her money back, and she said either was fine.

Nobody read it until the afternoon of the 5th.

That gap, two and a half days between a customer asking a simple question and anyone at the shop even seeing it, is the problem this entire course is about. By the end of this chapter you will be able to explain that problem to a friend who knows nothing about computers, in a few sentences, and you will know why three different people at Lantern would each describe "fixing it" in a different way. You will also have written the first page of a document you will keep for the next year.

## What James Miller actually does

James Miller is one of the eight support agents. When he finally opens Emily Carter's message, here is what happens, step by step, because the details are where the time goes.

He reads the message. It mentions order 48213, which is helpful; about a third of customers forget to include an order number, and then he has to search by name or email address and hope there is only one Emily Carter. He opens the orders spreadsheet, finds 48213, and sees an electric kettle, 45.00, ordered on 28 August, paid by card.

He opens the courier's delivery record, a separate file the courier company sends over every evening. Order 48213 was delivered on 1 September and signed for by "E. Carter". So the kettle did arrive, it arrived two days before Emily Carter wrote, and she signed for it herself. That matters, because the rulebook gives a customer 14 days from the delivery date to report a problem, and Emily Carter is well inside it.

He opens the photo. The crack is obvious. Fine.

He opens the rulebook, which is a document of twenty rules that Rachel has built up over the years, and finds the rule about damaged items: with a photo, refund or resend, whichever the customer prefers. Emily Carter said either is fine. The kettle is 45.00, which is under the 200.00 line above which Rachel has to sign off. James Miller can decide this one himself.

He writes back to Emily Carter, offering a replacement kettle, and asks her to confirm. He adds a row to the decisions spreadsheet: message M-1041, order 48213, resend, 45.00, James Miller, and the date.

Twenty minutes, roughly. And this was an easy one. The order number was there, the delivery record matched the story, the photo was clear, the rule was unambiguous, and the amount was small. Now think about Ivan Petrov, whose message says the courier claims to have delivered his charger but nothing arrived. Or Jack Davis, who wants a refund for a rattling fan and did not give an order number at all. Those messages take longer, and some of them James Miller cannot decide alone, so he writes a note to Rachel, and Rachel has forty of those notes waiting.

## Where the two and a half days come from

You might expect the delay to be caused by the twenty minutes. It is not, mostly. Eight agents working seven hours a day could handle three thousand twenty-minute messages a month with time to spare, if that was all they did.

The delay comes from everything around the twenty minutes. Messages from customers who have not been answered yet and write again, angrier, which doubles the pile. Messages that are missing something, so the agent writes back to ask and the case stops for a day. Cases passed to Rachel that sit in her queue. Agents off sick, on holiday, or in training. And a shared inbox, which means nobody owns a message until someone opens it, so the oldest messages are not necessarily the first ones handled.

So when Sarah says she wants a customer to get an answer within an hour, she is not asking James Miller to type faster. She is asking for something structural: the easy cases, which are most of them, should not need to wait for a person at all, so that the people are free for the hard ones.

Try to say, in one sentence, what Lantern's problem is, without mentioning any technology. Then open the fold.

<details><summary>One way to say it</summary>

Lantern gets three thousand customer complaints a month, each one takes a person twenty minutes of looking things up before they can answer, and there are not enough people, so customers wait days for answers that are usually obvious.

Yours will be different. The test is whether your friend, hearing it, would understand what is wrong and roughly why.

</details>

## The same message, read by three people

Here is the part that trips people up when they start building systems for businesses. You will be tempted to think there is one problem and one fix. There is one problem, but there are three different ideas of what "fixed" means, and they pull against each other.

To Sarah, who owns the shop, Emily Carter's message is a customer who is about to become an unhappy customer. Fixed means Emily Carter gets an answer in under an hour. If you built something that answered every message in ten minutes but occasionally paid a refund it should not have, Sarah would probably still be pleased, at least at first.

To Michael, who keeps the books, Emily Carter's message is 45.00 about to leave the company. Fixed means that a year from now, when the accountant or the tax office asks why that 45.00 went out, he can open a record and see exactly what it was based on: this message, this order, this delivery record, this rule, decided by this person on this date. And the record has not been touched since. A system that answered Emily Carter in ten minutes but wrote nothing down, or wrote something down that could be quietly edited later, is worse than useless to Michael, because he is the one who has to answer for it.

To Rachel, who runs the support team and wrote the rulebook, Emily Carter's message is a case, and fixed means the case was decided the way the rulebook says, the same way it would have been decided for anyone else on any other day. And Rachel knows that some cases do not fit the rules. A photo that might show old damage. A customer whose story does not match the courier's record. A refund that a rule allows but that feels wrong. Rachel wants those to reach a human being, and she does not want a system quietly deciding them because it was confident. A system that was fast and kept perfect records but decided the hard cases on its own would frighten her, correctly.

Read those three paragraphs again and notice that none of them contradict each other, and that satisfying one does not satisfy the others. Fast, recorded, and cautious about the edges. You will be held to all three, and the reason is simple: Sarah decides whether to buy, Michael decides whether it can be trusted with money, and Rachel decides whether her team will actually use it. Any one of them can kill the project.

## What you are going to build, in plain words

Over the coming months you will build a system that does most of what James Miller does for an easy case, and none of what he does for a hard one.

It reads the customer's message and finds the order number, or works out who the customer is if there is none. It looks up the order and the delivery record. It finds the rules that apply and checks the message against them: is this within 14 days, is there a photo, is the amount under the line. When everything is clear, it decides, drafts the reply, and writes the record Michael needs. When anything is unclear, it stops, writes down what it found, and hands the case to a person with everything already looked up.

Described like that, it sounds like a few weeks of work. It is not, and understanding why is the second thing this chapter is for.

Making a program that reads Emily Carter's message and guesses "damaged item, refund" is genuinely a weekend's work. Making one that Rachel will let run without watching it, on real customers' money, that still behaves when message number four thousand is in broken English with no order number and a photo of the wrong thing, that Michael can audit a year later, and that does not slowly become wrong as the rulebook changes: that is the work. Almost every project of this kind that fails, fails there, not because the program could not read the message.

So the course is long because the trust is the product. The reading of the message is the easy part, and you will have it working by the end of Phase 1.

## One more thing about words

The curriculum asks you to be able to state Lantern's problem without using the words "AI", "agent", or "LLM". This is not a game. It is the most useful habit you will pick up this year.

When you sit across from someone like Sarah, she does not have a problem called "we need AI". She has a problem called "my customers wait three days and I cannot afford eight more people". If you open with the technology, you have told her what you want to sell before you have understood what she needs, and she will hear a salesperson. If you can describe her problem back to her better than she described it to you, she will hear someone who can fix it. The technology comes later, and often the right answer involves less of it than you expected.

Now write it down. The assignment below asks for one page: the problem, the three people and what "done" means to each, how a message is handled today, and how it should be handled. It is the first version of a document you will revise at the end of every phase, as what you have built changes what is possible. Keep it in plain words. Sarah should be able to read it.
