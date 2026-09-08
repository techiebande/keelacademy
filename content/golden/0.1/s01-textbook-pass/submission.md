# OmniCart Operations: Client Brief

## The problem

OmniCart handles about 4,000 return requests, damaged parcel claims, and merchant payout disputes every month. Each one waits 2 to 3 days before a clerk reviews it. During that wait shoppers grow angry, fraudulent refunds slip through, and courier damage claims expire unclaimed.

## Who cares and why

Sarah Jenkins, VP of Operations, owns the queue. She wants triage cut from 2 to 3 days to under 1 hour with zero lost tickets.

The CFO cares about the money, not the clock. Every refund, replacement, and merchant chargeback must be tracked to exact integer cents with a record nobody can edit after the fact.

The Trust and Safety Officer cares about the rules. She enforces the 14 day statutory return window, warranty clauses, and the photo evidence standard for damage claims, and she needs every decision to cite the policy it relied on.

## How it works today

1. A shopper files a claim, which lands in the shared inbox as CLM-20841 with a link to order ORD-8821.
2. A clerk opens the order receipt to confirm what was bought, when, and for how much.
3. The clerk pulls the delivery slip from the courier portal to confirm the delivery date.
4. The clerk opens the unboxing photo the shopper attached and judges whether the damage looks real.
5. The clerk reads the store return policy for that brand to check the 14 day window and any warranty clause.
6. The clerk writes a decision in the ticket and, if approved, keys a refund into the payments tool by hand.

Each step means a different screen, and the queue is worked oldest first.

## How it should work

1. When CLM-20841 arrives, the system pulls the order receipt, delivery slip, unboxing photo, and return policy into one view within 5 minutes.
2. The system checks the return window and the delivery date and records each check as a pass or fail with a reason.
3. Clear cases are approved or declined at once, and the refund is written as integer cents, for example 4520 cents for ORD-8821.
4. Hard cases, such as a blurry photo or a claim filed on day 14, go to a human reviewer with the checks already done.
5. Every decision, human or system, is stamped with the policy clause it relied on and stored in a log that cannot be edited.

The target is a decision on every claim in under 1 hour, with a person making the final call on anything the checks cannot settle.
