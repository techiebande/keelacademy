import Link from "next/link";

export function UnitPaywallCard({
  unitId,
  priceLabel = "$49",
}: {
  unitId: string;
  priceLabel?: string;
}) {
  return (
    <div className="lesson-canvas flow">
      <div id="unit-paywall" className="flow-apparatus apparatus mt-12">
        <div className="apparatus-head">
          <p className="apparatus-label">Subscription required</p>
          <span className="chip chip-outline font-code-mono text-[11px]">
            UNIT LOCKED
          </span>
        </div>

        <p className="apparatus-note">
          We keep Unit 0.1 free so everyone can try our lessons and drills.
          Unit {unitId} and later units require an active all-access subscription.
        </p>

        <div className="mt-6 rounded-lg border border-circuit-border bg-carbon-veil p-5">
          <p className="font-goga text-[15.5px] font-medium text-phosphor-white">
            What you get with all access
          </p>
          <ul className="mt-3 space-y-2 text-[14px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            <li className="flex items-start gap-2.5">
              <span className="select-none text-lime-pulse">•</span>
              <span>Every published lesson, code workbench, and retrieval drill.</span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="select-none text-lime-pulse">•</span>
              <span>Automated tests graded against real server environments.</span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="select-none text-lime-pulse">•</span>
              <span>A 15% rebate back to your card when you clear a milestone gate on time.</span>
            </li>
          </ul>
        </div>

        <div className="mt-7 flex flex-wrap items-center gap-x-4 gap-y-3">
          <Link href="/checkout" className="btn btn-accent btn-sm">
            Subscribe — {priceLabel} / month
          </Link>
          <Link href="/units/0.1" className="btn btn-primary btn-sm">
            Read free sample (Unit 0.1)
          </Link>
          <Link href="/curriculum" className="btn btn-ghost btn-sm">
            View curriculum
          </Link>
        </div>
      </div>
    </div>
  );
}
