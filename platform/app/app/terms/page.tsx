import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms and Conditions",
  description: "The terms that govern your use of Keel Academy.",
};

export default function TermsPage() {
  return (
    <div className="shell section">
      <header className="max-w-[68ch]">
        <p className="eyebrow">Legal</p>
        <h1 className="heading-xl mt-4">Terms and Conditions</h1>
        <p className="lead mt-4">
          These terms govern your access to Keel Academy. When you create an
          account or subscribe, you agree to these rules.
        </p>
      </header>

      <div className="mt-12 max-w-[68ch] space-y-10 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
        <section className="space-y-3">
          <h2 className="heading-md text-phosphor-white">1. What Keel Academy provides</h2>
          <p>
            Keel Academy offers applied AI engineering curriculum, exercises, and
            automated project checks. We provide continuous access to published units
            and learning tools for active subscribers.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="heading-md text-phosphor-white">2. Accounts and subscriptions</h2>
          <p>
            You must provide accurate information when signing in. You are
            responsible for maintaining the security of your account credentials.
          </p>
          <p>
            Subscriptions renew automatically each month until you cancel. Paddle
            serves as our Merchant of Record. Paddle processes all payments,
            handles taxes, and manages invoices.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="heading-md text-phosphor-white">3. Cancellations</h2>
          <p>
            You can cancel your subscription at any time from your account settings.
            Cancellation takes effect at the end of your current billing period.
            We do not issue automatic partial refunds for unused days in a cycle.
            You keep full access to all units until the cycle ends.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="heading-md text-phosphor-white">4. Intellectual property</h2>
          <p>
            You own the code you write for your projects and assignments.
            Keel Academy owns the curriculum, automated tests, rubrics, text,
            and platform design.
          </p>
          <p>
            Do not redistribute or resell our lessons, tests, or platform materials.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="heading-md text-phosphor-white">5. Acceptable use</h2>
          <p>
            We expect genuine learning and honest work. Do not attempt to attack,
            overload, or bypass our automated grading services.
          </p>
          <p>
            You may use AI tools to assist your coding. However, capstone defenses
            require live understanding of your own code.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="heading-md text-phosphor-white">6. Limitation of liability</h2>
          <p>
            We provide Keel Academy on an &quot;as is&quot; basis. We work hard to keep
            the platform fast and reliable, but we cannot guarantee uninterrupted uptime.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="heading-md text-phosphor-white">7. Contact us</h2>
          <p>
            Questions about these terms? Email us directly at{" "}
            <a
              href="mailto:support@keelacademy.com"
              className="text-lime-pulse underline underline-offset-4"
            >
              support@keelacademy.com
            </a>
            .
          </p>
        </section>
      </div>
    </div>
  );
}
