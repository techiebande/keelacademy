# OmniCart Operations: Client Brief

## The problem

OmniCart handles about 4,000 return requests, damage claims, and payout disputes each month.
Each request waits 2 to 3 days before a clerk begins review.
While cases wait, shoppers grow angry and merchant chargebacks pile up.

## Who cares and why

- Sarah Jenkins, VP of Operations, wants review time cut from 2 to 3 days to under 1 hour.
- The CFO wants every refund tracked in whole integer cents with records that nobody can change.
- The Trust and Safety Officer wants the 14 day return rule enforced with photo proof for damage claims.

## How it works today

1. A shopper files a claim, which arrives as CLM-20841 for order ORD-8821.
2. The ticket sits in a shared inbox for 2 to 3 days before review.
3. A clerk opens the order receipt to check items bought, purchase price, and dates.
4. The clerk opens the courier delivery slip to confirm delivery date and recipient signature.
5. The clerk examines the customer unboxing photo to check the damage claim.
6. The clerk reviews the store return policy to check the 14 day window and category rules.
7. The clerk calculates the refund and keys payment details into the ledger by hand.

## How it should work

1. A customer submits claim CLM-20841 linked to order ORD-8821.
2. A clerk logs the claim at once with an unchangeable record.
3. The clerk checks the order receipt against the delivery slip and unboxing photo.
4. The clerk verifies that the return policy allows the refund under the 14 day rule.
5. Clean requests are approved and refunded in under 1 hour.
6. Refunds are recorded in whole integer cents, such as 4520 cents.
7. Requests with unclear damage photos or policy exceptions go to a human reviewer for final decision.
