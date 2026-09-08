"use client";

import { useState } from "react";
import { startSubscriptionAction } from "@/app/auth/actions";

export function CommitmentForm({ priceLabel }: { priceLabel: string }) {
  const [ack1, setAck1] = useState(false);
  const [ack2, setAck2] = useState(false);
  const [ack3, setAck3] = useState(false);

  const canSubmit = ack1 && ack2 && ack3;

  const row =
    "flex gap-3 rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]";
  const box = "mt-0.5 size-4 shrink-0 accent-lime-pulse";

  return (
    <form action={startSubscriptionAction} className="mt-6">
      <fieldset className="space-y-3">
        <legend className="field-label">Before you pay</legend>
        <label className={row}>
          <input
            type="checkbox"
            checked={ack1}
            onChange={(e) => setAck1(e.target.checked)}
            className={box}
          />
          <span>
            All access is a monthly subscription. It renews every month until
            you cancel, and every unit stays open while it is active.
          </span>
        </label>
        <label className={row}>
          <input
            type="checkbox"
            checked={ack2}
            onChange={(e) => setAck2(e.target.checked)}
            className={box}
          />
          <span>
            Your work is graded by automated checks and a rubric review of the code you
            push. A verdict can come back &ldquo;Not yet&rdquo;, and you can resubmit.
          </span>
        </label>
        <label className={row}>
          <input
            type="checkbox"
            checked={ack3}
            onChange={(e) => setAck3(e.target.checked)}
            className={box}
          />
          <span>
            Rebates go back to the card you paid with after a Passed verdict inside the
            window for that gate.
          </span>
        </label>
      </fieldset>

      <button type="submit" disabled={!canSubmit} className="btn btn-accent mt-7 w-full">
        Subscribe — {priceLabel} / month
      </button>
      <p className="mt-3 text-[13px] text-[color:var(--text-faint-on-dark)]">
        Paddle handles payment. We never see your card number, and we never want to.
      </p>
    </form>
  );
}
