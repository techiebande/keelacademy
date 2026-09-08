import type { Metadata } from "next";
import Link from "next/link";
import { listUnits, loadCurriculumMap } from "@/lib/content";
import { fetchPrice, formatPrice } from "@/lib/enroll";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "You enroll per unit. You see the price before you pay. You get 15% back at each milestone gate you clear in time.",
};

export default async function PricingPage() {
  const units = listUnits();
  const first = units[0];

  // The same price endpoint checkout reads, so this page cannot quote a number
  // the till would not charge. If it does not answer, we say so.
  const priced = await Promise.all(
    units.map(async (u) => {
      const res = await fetchPrice(u.id);
      return {
        id: u.id,
        phase: u.phase,
        price: res.state === "ok" ? formatPrice(res.data.amount_cents, res.data.currency) : null,
      };
    }),
  );
  const anyPriced = priced.some((p) => p.price !== null);

  const map = loadCurriculumMap();
  const totalHours = map.phases.reduce((sum, p) => sum + p.est_hours, 0);
  const monthsAtFifteen = Math.round(totalHours / 15 / 4.33);
  const monthsAtTwelve = Math.round(totalHours / 12 / 4.33);

  return (
    <div>
      <header className="shell pb-14 pt-14">
        <p className="eyebrow">Pricing</p>
        <h1 className="heading-xl mt-4 max-w-[24ch]">
          Pay per unit. Get paid back for finishing.
        </h1>
        <p className="lead mt-5">
          Subscriptions are how you pay for courses you never finish, so
          there isn&rsquo;t one. You enroll unit by unit, and every unit shows its
          exact price before you pay anything. Clear a milestone gate inside
          its window and we refund 15% of what you paid for that unit to the
          card you paid with.
        </p>
        {first ? (
          <div className="mt-8 flex flex-wrap gap-4">
            <Link href={`/units/${first.id}`} className="btn btn-primary">
              Open Unit {first.id}
            </Link>
            <Link href="/curriculum" className="btn btn-ghost">
              See what each unit covers
            </Link>
          </div>
        ) : (
          <div className="mt-8">
            <Link href="/curriculum" className="btn btn-primary">
              See the curriculum
            </Link>
          </div>
        )}
      </header>

      <div className="shell space-y-10 pb-24">
        <section className="card-dark p-8 lg:p-10" id="prices">
          <p className="eyebrow">What is open today</p>
          <h2 className="heading-lg mt-4">
            {priced.length === 1 ? "One unit is open" : `${priced.length} units are open`}
          </h2>
          <p className="mt-4 max-w-[64ch] text-[16px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            The numbers below come from the same checkout that charges you:
            what you see is what you pay. We publish units as we finish them.
            Each has its own price.
          </p>
          {anyPriced ? (
            <div className="mt-8 overflow-x-auto">
              <table className="data-table">
                <caption className="sr-only">Price per open unit</caption>
                <thead>
                  <tr>
                    <th scope="col">Unit</th>
                    <th scope="col">Phase</th>
                    <th scope="col">Price</th>
                    <th scope="col">
                      <span className="sr-only">Open the unit</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {priced.map((u) => (
                    <tr key={u.id}>
                      <th scope="row">
                        <span className="font-code-mono text-[13px] text-lime-pulse">{u.id}</span>
                      </th>
                      <td>{u.phase}</td>
                      <td>{u.price ?? "No price to show"}</td>
                      <td>
                        <Link href={`/units/${u.id}`} className="btn btn-ghost btn-sm">
                          Open
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="mt-8 rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              We could not load prices. Refresh. Or open a unit. The price is on its enrollment panel.
            </p>
          )}
        </section>

        {/* Rebate mechanic */}
        <section className="card-dark p-8 lg:p-10" id="rebates">
          <p className="eyebrow">The completion rebate</p>
          <h2 className="heading-lg mt-4">Two gates pay 15% back.</h2>
          <p className="mt-4 max-w-[64ch] text-[16px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            You earn the rebate the moment you clear a gate inside its window, with no forms and no asking. A person
            issues the refund to the card you paid with. It lands within 5 business days. Miss the window and the rebate expires, but
            your progress never resets: the units stay open and you keep building. Your dashboard
            shows the state of both rebates and the date each window closes.
          </p>
          <div className="mt-8 grid gap-6 md:grid-cols-2">
            <div className="rounded-lg border border-circuit-border bg-carbon-veil p-7">
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-goga text-[18px] font-medium text-phosphor-white">
                  Phase 5 integration gate
                </h3>
                <span className="chip chip-live">15% back</span>
              </div>
              <p className="mt-3 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                Pass the Phase 5 integration project, the first full multi-agent
                milestone, within its window after you enroll.
              </p>
            </div>
            <div className="rounded-lg border border-circuit-border bg-carbon-veil p-7">
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-goga text-[18px] font-medium text-phosphor-white">
                  Final capstone gate
                </h3>
                <span className="chip chip-live">15% back</span>
              </div>
              <p className="mt-3 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                Clear the capstone: the complete system, plus the two defences against a technical
                reviewer and the budget holder.
              </p>
            </div>
          </div>
        </section>

        {/* What an enrollment includes */}
        <section className="card-dark p-10" id="included">
          <p className="eyebrow">Every unit enrollment includes</p>
          <div className="mt-7 grid gap-x-12 gap-y-5 md:grid-cols-2">
            {[
              "The full written lesson: the concept, the client numbers, the thing you are about to build",
              "A worked example plus a completion problem, graded by automated checks on every save",
              "Retrieval drills that resurface right before you would forget them",
              "An assistant that has read that exact unit, ready to answer questions at 2am",
              "Automated checks and rubric review on every submission, with quoted evidence from your code",
              "Your submission history and every verdict, kept on your dashboard",
            ].map((item) => (
              <p
                key={item}
                className="flex gap-3.5 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]"
              >
                <svg
                  aria-hidden
                  className="mt-1 shrink-0"
                  width="15"
                  height="15"
                  viewBox="0 0 16 16"
                  fill="none"
                >
                  <path
                    d="M3 8.6l3 3 7-7.2"
                    stroke="var(--color-lime-pulse)"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                {item}
              </p>
            ))}
          </div>
        </section>

        {/* Honest expectations */}
        <section className="card-dark p-10" id="expectations">
          <p className="eyebrow">Before you enroll</p>
          <h2 className="heading-lg mt-4">Before you enroll</h2>
          <div className="mt-7 grid gap-8 md:grid-cols-2">
            <div>
              <h3 className="font-goga text-[17px] font-medium text-phosphor-white">
                What this takes
              </h3>
              <ul className="mt-3 space-y-2.5 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                <li>{`The full curriculum takes ${totalHours} hours of hands-on build work.`}</li>
                <li>{`At 12 to 15 hours a week, that is roughly ${monthsAtFifteen} to ${monthsAtTwelve} months.`}</li>
                <li>You read code every session. You write code every session. You ship code every session. That is the whole method, and it never changes.</li>
              </ul>
            </div>
            <div>
              <h3 className="font-goga text-[17px] font-medium text-phosphor-white">
                What we guarantee
              </h3>
              <ul className="mt-3 space-y-2.5 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                <li>
                  Finish, and you leave with a working production system that
                  passed a published bar, plus a proposal you can send to a
                  real client the same week.
                </li>
                <li>
                  Automated checks and rubric review checked every milestone
                  against a published bar.
                </li>
                <li>
                  What we will not promise: clients, jobs, or six figures in
                  six weeks. What we promise: the work, and proof you did it.
                </li>
              </ul>
            </div>
          </div>
          {first ? (
            <div className="mt-9">
              <Link href={`/units/${first.id}`} className="btn btn-primary">
                Start with Unit {first.id}
              </Link>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
