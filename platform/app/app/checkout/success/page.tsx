import type { Metadata } from "next";
import Link from "next/link";
import { requireSession } from "@/lib/auth";
import { fetchSubscriptionStatus } from "@/lib/enroll";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Subscription status",
  robots: { index: false },
};

type Props = { searchParams: Promise<{ transaction_id?: string }> };

export default async function CheckoutSuccessPage({ searchParams }: Props) {
  const { transaction_id: transactionId } = await searchParams;
  await requireSession("/me");

  const result = transactionId
    ? await fetchSubscriptionStatus(transactionId)
    : null;

  return (
    <div className="shell section">
      {result?.state === "ok" &&
      (result.data.status === "active" || result.data.status === "trialing") ? (
        <div className="card-dark max-w-[62ch]">
          <span className="chip chip-live">ALL ACCESS</span>
          <h1 className="heading-lg mt-4">Your subscription is active</h1>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            Every unit is open to you now. Start with the lesson, work the
            drills, then build, in that order, and it will go well.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href="/map" className="btn btn-accent btn-sm">
              Open the progress map
            </Link>
            <Link href="/me" className="btn btn-ghost btn-sm">
              Back to dashboard
            </Link>
          </div>
        </div>
      ) : result?.state === "ok" && result.data.status === "pending" ? (
        <div className="card-dark max-w-[62ch]">
          <span className="chip chip-outline">CONFIRMING</span>
          <h1 className="heading-lg mt-4">Confirming your subscription</h1>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            The payment provider still shows the checkout as pending. Check
            again — it almost always lands within a minute.
          </p>
          <Link
            href={`/checkout/success?transaction_id=${encodeURIComponent(transactionId ?? "")}`}
            className="btn btn-primary btn-sm mt-7"
          >
            Check again
          </Link>
        </div>
      ) : (
        <div className="card-dark max-w-[62ch]">
          <span className="chip chip-outline">PROCESSING</span>
          <h1 className="heading-lg mt-4">The payment provider has not confirmed yet</h1>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            Your access appears on your dashboard as soon as the subscription is
            confirmed. Nothing is lost if you close this page.
          </p>
          <Link href="/me" className="btn btn-primary btn-sm mt-7">
            Back to dashboard
          </Link>
        </div>
      )}
    </div>
  );
}
