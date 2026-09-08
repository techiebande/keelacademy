# OmniCart Operations: Client Brief

## The problem

Roughly 4,000 disputes hit OmniCart every month, counting returns, damaged parcels, and merchant payout fights. A dispute sits untouched for 2 to 3 days before anyone looks at it. By then the shopper has emailed twice, the fraudster has been paid, and the courier claim window is closing.

## Who cares and why

Sarah Jenkins runs Operations as VP and she is tired of the backlog. Her goal is plain: get triage from 2 to 3 days down to under 1 hour and lose zero tickets on the way.

The CFO has a different worry. He does not care how fast we move if the numbers are soft. He wants every refund, replacement, and chargeback recorded to exact integer cents in an audit trail that cannot be changed later.

The Trust and Safety Officer wants neither speed nor pennies. She wants the 14 day return rule, warranty clauses, and photo evidence standards applied the same way every time, with the clause named on each decision.

## How it works today

1. A claim such as CLM-20902 arrives in the queue tied to order ORD-9130.
2. One of our support agents opens the order receipt to see the item, the price, and the purchase date.
3. The same person finds the delivery slip in the courier system to confirm the drop date.
4. They open the unboxing photo and decide by eye whether the damage is real and recent.
5. They read the brand return policy to see if the claim falls inside the 14 day window.
6. They type a verdict into the ticket and, if it is a refund, enter the amount in the payments screen.
7. A second person spot checks a handful of refunds at month end.

Seven steps, five screens, and no shared checklist, so two clerks can reach opposite answers on the same claim.

## How it should work

1. The first pass is pure automation: when CLM-20902 arrives, the order receipt, delivery slip, unboxing photo, and return policy are gathered onto one screen.
2. Delivery date and return window are compared and each check is marked pass or fail with a one line reason.
3. Clean cases get a decision right away and the refund is written as integer cents, so a refund of 12999 cents is stored as 12999 and never as a decimal.
4. Anything unclear, like a photo with no timestamp, goes to a human specialist with the checks attached.
5. Every decision records the policy clause used and lands in a log that cannot be rewritten.

Target: a decision on every claim in under 1 hour, and a person signs off on every hard case.
