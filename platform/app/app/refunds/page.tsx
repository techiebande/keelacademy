import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Refund and Cancellation Policy",
  description: "How cancellations, refunds, and milestone rebates work at Keel Academy.",
};

export default function RefundsPage() {
  return (
    <div className="shell section">
      <header className="max-w-[68ch]">
        <p className="eyebrow">Billing</p>
        <h1 className="heading-xl mt-4">Refund and Cancellation Policy</h1>
        <p className="lead mt-4">
          We keep billing clear and fair. Here is how cancellations, refunds, and
          milestone rebates work.
        </p>
      </header>

      <div className="mt-12 max-w-[68ch] space-y-10 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
        <section className="space-y-3">
          <h2 className="heading-md text-phosphor-white">1. Self-serve cancellation</h2>
          <p>
            You can cancel your subscription at any time. You do not need to call
            or email us to cancel.
          </p>
          <p>
            When you cancel, your subscription stops renewing immediately. You keep
            full access to all units until your current billing period ends.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="heading-md text-phosphor-white">2. 14-day refund window</h2>
          <p>
            We want you to be confident in your learning investment. If you find
            the curriculum is not right for you within your first 14 days, let us know.
          </p>
          <p>
            Send an email to{" "}
            <a
              href="mailto:support@keelacademy.com"
              className="text-lime-pulse underline underline-offset-4"
            >
              support@keelacademy.com
            </a>{" "}
            with your account email. We will process a full refund to your original
            payment card via Paddle.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="heading-md text-phosphor-white">3. Milestone rebates</h2>
          <p>
            We reward steady progress through our milestone rebate program.
            Two milestone gates pay 15% back: the Phase 5 integration gate and the final capstone gate.
          </p>
          <p>
            When you clear a gate within its designated window, we issue 15% back
            to your payment card. A team member reviews the gate clearance and
            processes the payout within 5 business days.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="heading-md text-phosphor-white">4. Payment processor</h2>
          <p>
            Paddle is our Merchant of Record. All refunds and rebates return
            directly to the original payment method through Paddle.
          </p>
          <p>
            Depending on your bank, refunded funds usually appear in your account
            within 3 to 7 business days.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="heading-md text-phosphor-white">5. Contact support</h2>
          <p>
            Need help with a charge, cancellation, or refund? Email us anytime at{" "}
            <a
              href="mailto:support@keelacademy.com"
              className="text-lime-pulse underline underline-offset-4"
            >
              support@keelacademy.com
            </a>
            . We answer every message.
          </p>
        </section>
      </div>
    </div>
  );
}
