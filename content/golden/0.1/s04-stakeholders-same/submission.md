# OmniCart Operations: Client Brief

## The problem

OmniCart Operations processes approximately 4,000 return requests, damaged parcel claims, and merchant payout disputes each month. Every dispute currently waits 2 to 3 days before a clerk reviews it. The delay produces frustrated shoppers, fraudulent refund payouts, and courier damage claims that are never recovered.

## Who cares and why

Sarah Jenkins, VP of Operations, is the sponsor of this engagement. She wants triage cycle time reduced from 2 to 3 days to under 1 hour with zero lost tickets.

The CFO shares this objective. In his view a slow queue is the root of every finance complaint, so he too wants each dispute decided in under 1 hour and the backlog gone.

The Trust and Safety Officer is aligned with both of them. Her officers work the same queue, and she wants every claim resolved in under 1 hour so that cases stop piling up on her desk.

## How it works today

1. A claim such as CLM-20841 arrives through the support inbox and is matched to order ORD-8821.
2. A clerk retrieves the order receipt to verify the item, the price, and the purchase date.
3. The clerk locates the delivery slip in the courier portal to confirm the delivery date.
4. The clerk reviews the unboxing photo and forms a judgment about the damage.
5. The clerk consults the brand return policy to determine whether the 14 day window still applies.
6. The clerk records a decision in the ticket and, where a refund is due, enters the amount manually in the payments system.

Each step requires a separate system, and no shared checklist exists, so outcomes vary by clerk.

## How it should work

1. On arrival of CLM-20841 the order receipt, delivery slip, unboxing photo, and return policy are assembled into a single case view.
2. The return window and delivery date are verified and each check is recorded as pass or fail with a stated reason.
3. Clear cases receive an immediate decision, and any refund is stored as integer cents, for example 4520 cents for ORD-8821.
4. Ambiguous cases, such as a photo without a timestamp, are routed to a human reviewer with the completed checks attached.
5. Every decision cites the policy clause applied and is written to a log that cannot be modified.

The target is a decision on every claim in under 1 hour, with a person making the final determination on any case the checks cannot resolve.
