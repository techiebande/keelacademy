# OmniCart Operations: Client Brief

## The problem

OmniCart handles about 4,000 returns, damage claims, and payout disputes a month. Each one waits 2 to 3 days for a clerk. Shoppers churn, fraud gets paid, and courier claims expire.

## Who cares and why

VP of Operations, Sarah Jenkins. Wants triage under 1 hour with zero lost tickets. Her team fields the angry calls in the meantime.

CFO. Wants every refund and chargeback tracked to exact integer cents in a log that cannot be edited. Speed is not his problem, leakage is.

Trust and Safety Officer. Wants the 14 day return window, warranty clauses, and photo evidence rules applied the same way every time. She also wants the rule named on each decision.

## How it works today

1. Claim CLM-20841 arrives and a clerk opens the order receipt for ORD-8821 to check item, price, and date.
2. The clerk pulls the delivery slip from the courier portal to confirm delivery.
3. The clerk views the unboxing photo and reads the brand return policy to test the 14 day window.
4. The clerk writes a decision in the ticket and keys any refund by hand.

Four screens. No checklist. Oldest ticket first. A simple case waits behind a hard one.

## How it should work

1. On arrival, the order receipt, delivery slip, unboxing photo, and return policy for CLM-20841 load on one screen.
2. The return window and delivery date are checked and each result is logged with a reason.
3. Clear cases are decided at once and the refund is stored as integer cents, for example 4520 cents.
4. Hard cases go to a human specialist with the checks attached.

Target: a decision on every claim in under 1 hour. A person decides anything the checks cannot settle. The log names the rule used on every case.
