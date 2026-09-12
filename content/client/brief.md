# Lantern Home

Lantern Home is an online shop. It sells the ordinary things people need at home: kettles, lamps, bedsheets, cooking pots, phone chargers, school bags, fans. You order on the website, and a courier brings a parcel to your door a few days later. The shop is fictional. It was invented for this course so that every program you write has a real-looking business behind it, and everything about it is described here so you never have to guess.

Lantern started eleven years ago as one shop on a busy street and now sells only online, to one country. About sixty people work there. Most of them are in the warehouse, packing parcels. Eight of them are the customer support team, and they are the people this whole course is about.

## The problem

Every month, roughly three thousand customers write to Lantern with a problem. "My parcel has not arrived." "The kettle came with a cracked lid." "You sent me a blue bedsheet and I ordered grey." "I want my money back." The messages arrive by email and through a form on the website, and they land in one shared inbox.

A support agent, say James Miller, opens the next message. He reads it. He finds the order number in it, if the customer included one, and looks the order up. He opens the courier's delivery record to see when the parcel was delivered and who signed for it. If the customer says something is broken, he looks for the photo. He opens the rulebook, a document of about forty rules the team has built up over the years, and works out what the customer is entitled to. He decides: refund, resend, ask for more information, or say no. He writes back. He records the decision in a spreadsheet.

That takes him about twenty minutes when everything is where it should be, and much longer when it is not. With three thousand messages a month and eight agents, a message waits two to three days before anyone opens it. Customers write again to ask why nobody has answered, which adds more messages to the pile. About one refund in fifty is later found to be wrong: too much paid, or paid twice, or paid against the rules.

## The people

**Sarah Johnson** owns Lantern. She started the shop and still knows most of the warehouse staff by name. What she wants is simple to say: a customer with a problem should get an answer within an hour, not within three days, and she does not want to hire eight more agents to get there. She is the person who will decide whether to pay for what you build.

**Michael Brown** keeps the books. Every refund is money leaving the company, and he has to explain every one of them to the tax office and to Sarah. He wants every decision written down in a way that cannot quietly change afterwards: who decided, when, how much, and why. If your system pays a refund, Michael needs to be able to find that refund a year later and see exactly what it was based on.

**Rachel Smith** runs the support team. She wrote most of the rulebook. She wants the rules applied the same way to every customer, whoever is on shift. She also knows that some cases are genuinely hard, a customer whose story does not quite match the records, a photo that could show old damage or new, and she does not want any system deciding those on its own. Hard cases should reach a person. Easy cases should not.

You will meet all three again and again. When a lesson says "Michael would want this written down", it means exactly what it says here.

## What Lantern has

Everything the support team works with is in this folder, in the form you will actually read it with code:

- `messages/`: customer messages, one per file, exactly as customers wrote them, typos included.
- `orders.csv`: one row per order. Order number, customer name, what they bought, the price, the date.
- `deliveries.csv`: the courier's record. Order number, the date the parcel was delivered, and who signed for it, if anyone.
- `rules.md`: the support team's rulebook.

Prices are written as plain numbers, like `45.00`. Lantern sells in one country and the currency does not matter for anything you will build, so there is no symbol.

## What "better" means

Sarah, Michael and Rachel each answer that question differently, and a system that satisfies only one of them will not be bought.

For Sarah: a customer whose case is straightforward gets a correct answer in under an hour.

For Michael: every decision is recorded with what it was based on, and no record is ever edited after the fact.

For Rachel: the rules are applied consistently, and every case the rules do not clearly cover reaches a human being before anything is paid.

Over the course you will build, piece by piece, a system that reads a customer message, finds the order and the delivery record, checks the rulebook, decides what the customer is entitled to when the rules are clear, hands the case to a person when they are not, and writes down everything it did. Phase 1 starts with the smallest possible piece of that: a program that reads one message file and pulls out the order number.
