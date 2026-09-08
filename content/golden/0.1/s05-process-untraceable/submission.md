# OmniCart Operations: Client Brief

## The problem

Picture about 4,000 unhappy shoppers a month, each one filing a return, a damage claim, or a payout dispute with OmniCart. Every one of them waits 2 to 3 days before a clerk even opens the file. In that gap the honest shopper gives up, the dishonest one gets paid, and the courier claim quietly expires.

## Who cares and why

Sarah Jenkins, the VP of Operations, feels this daily. Her people are drowning, and she wants triage down from 2 to 3 days to under 1 hour without losing a single ticket.

The CFO sees a different problem. He is less bothered by the wait than by the money. He wants every refund, replacement, and merchant chargeback tracked to exact integer cents with an audit trail nobody can touch.

The Trust and Safety Officer worries about something else again. She guards the 14 day statutory return window, the warranty clauses, and the photo evidence rules for damage claims, and she wants every decision to show which rule it leaned on.

## How it works today

1. A claim like CLM-20841 lands in the inbox and a clerk gathers the paperwork for order ORD-8821 from three different systems.
2. The clerk reads through everything and decides whether the shopper deserves a refund.
3. The clerk enters the refund and closes the ticket.

That is the whole process as anyone can describe it, which is part of the problem. Nobody can say exactly which document settles which question, so no two clerks work a claim the same way.

## How it should work

1. When CLM-20841 arrives, the order receipt, delivery slip, unboxing photo, and return policy are gathered onto one screen.
2. The return window and delivery date are checked and each check is written down as pass or fail with a reason.
3. Clear cases are decided on the spot and the refund is stored as integer cents, so 4520 cents for ORD-8821, never a decimal.
4. Hard cases, like a photo that does not match the order, go to a human specialist with the checks already done.
5. Every decision names the policy clause it used and goes into a log that cannot be changed.

The goal is a decision on every claim in under 1 hour, with a person making the call on anything the checks cannot settle.
