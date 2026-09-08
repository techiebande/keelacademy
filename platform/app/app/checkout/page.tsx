import type { Metadata } from "next";
import Link from "next/link";
import { requireSession } from "@/lib/auth";
import { fetchSubscriptionPrice, formatPrice } from "@/lib/enroll";
import { CommitmentForm } from "@/components/commitment-form";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Checkout",
  robots: { index: false },
};

export default async function CheckoutPage() {
  const user = await requireSession("/checkout");

  // The same price endpoint the real charge uses, so this page cannot quote
  // a number Paddle would not bill.
  const priceRes = await fetchSubscriptionPrice();

  if (priceRes.state !== "ok") {
    return (
      <div className="shell section">
        <div className="card-dark max-w-[62ch]">
          <p className="eyebrow">Checkout unavailable</p>
          <h1 className="heading-lg mt-3">We could not load the price</h1>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            We could not load the price, so we will not guess at a number. Nothing
            was charged. Refresh and try again.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href="/checkout" className="btn btn-primary btn-sm">
              Try again
            </Link>
            <Link href="/pricing" className="btn btn-ghost btn-sm">
              Back to pricing
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const priceLabel = formatPrice(priceRes.data.amount_cents, priceRes.data.currency);

  return (
    <div className="shell section">
      <header className="max-w-[62ch]">
        <p className="eyebrow">Checkout</p>
        <h1 className="heading-xl mt-4">The whole program, one subscription</h1>
        <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          Every unit — the ones written today and the ones published while you
          study — stays open while your subscription is active. Clearing a
          milestone gate sends 15% back to the card you used.
        </p>
      </header>

      <div className="mt-10 grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="details-title" className="card-dark">
          <h2 id="details-title" className="heading-md">
            What you are buying
          </h2>
          <dl className="mt-6 space-y-4">
            <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-[color:var(--line-on-dark)] pb-4">
              <dt className="text-[14px] text-[color:var(--text-muted-on-dark)]">Account</dt>
              <dd className="text-[15px] text-phosphor-white">{user.email}</dd>
            </div>
            <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-[color:var(--line-on-dark)] pb-4">
              <dt className="text-[14px] text-[color:var(--text-muted-on-dark)]">Plan</dt>
              <dd className="font-code-mono text-[15px] text-phosphor-white">All access</dd>
            </div>
            <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-[color:var(--line-on-dark)] pb-4">
              <dt className="text-[14px] text-[color:var(--text-muted-on-dark)]">Price</dt>
              <dd className="stat-number">
                {priceLabel}
                <span className="text-[15px] text-[color:var(--text-muted-on-dark)]"> / month</span>
              </dd>
            </div>
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <dt className="text-[14px] text-[color:var(--text-muted-on-dark)]">Cancel</dt>
              <dd className="text-[15px] text-phosphor-white">Any time, self-serve</dd>
            </div>
          </dl>
        </section>

        <section aria-labelledby="commit-title" className="card-dark">
          <h2 id="commit-title" className="heading-md">
            Three things to agree to
          </h2>
          <CommitmentForm priceLabel={priceLabel} />
        </section>
      </div>

      <p className="mt-8">
        <Link
          href="/pricing"
          className="text-[15px] text-fern-link underline underline-offset-4 hover:text-phosphor-white"
        >
          Back to pricing
        </Link>
      </p>
    </div>
  );
}
