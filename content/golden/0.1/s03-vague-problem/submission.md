# OmniCart Operations: Client Brief

## The problem

OmniCart receives a lot of return requests, damaged parcel claims, and merchant payout disputes. They sit in a queue for far too long before a clerk opens them. While they wait, shoppers complain, some refunds go to cheats, and courier damage claims lapse.

## Who cares and why

Sarah Jenkins, VP of Operations. She wants every claim triaged in under 1 hour with zero lost tickets. Speed is her whole scorecard.

The CFO. He wants every refund, replacement, and merchant chargeback recorded to exact integer cents, with an audit trail that cannot be altered. Speed matters less to him than a clean ledger.

The Trust and Safety Officer. She enforces the 14 day statutory return window, warranty terms, and the photo evidence standard for damage claims. She wants each decision to name the rule it used.

## How it works today

1. Claim CLM-20841 arrives by email and a clerk links it to order ORD-8821.
2. The clerk opens the order receipt to check item, price, and purchase date.
3. The clerk finds the delivery slip in the courier portal to confirm the delivery date.
4. The clerk views the unboxing photo and judges the damage by eye.
5. The clerk reads the brand return policy to test the 14 day window.
6. The clerk writes the verdict in the ticket and keys any refund by hand.

Six screens. No checklist. Different clerks, different answers.

## How it should work

1. Claim CLM-20841 arrives and the order receipt, delivery slip, unboxing photo, and return policy appear on one screen.
2. The return window and delivery date are checked and each check is logged as pass or fail with a reason.
3. Clear cases get an instant decision and the refund is stored as integer cents, for example 4520 cents, never a decimal.
4. Unclear cases, such as a photo taken after the return window, go to a human specialist with the checks attached.
5. Every decision records the policy clause it used in a log that cannot be edited.

Target: every claim decided in under 1 hour. A person makes the final call on anything the checks cannot settle.
