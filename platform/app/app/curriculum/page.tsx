import type { Metadata } from "next";
import Link from "next/link";
import { isUnitAuthored, loadCurriculumMap } from "@/lib/content";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Curriculum",
  description:
    "Every phase from engineering foundations through deployed AI systems, taught by building one invoice reconciliation and dispute triage pipeline end to end.",
};

export default function CurriculumPage() {
  const map = loadCurriculumMap();
  const totalModules = map.phases.reduce((n, p) => n + p.modules.length, 0);
  const totalHours = map.phases.reduce((n, p) => n + p.est_hours, 0);
  // Counted, not asserted: a unit is open only when its content exists.
  const openModules = map.phases.reduce(
    (n, p) => n + p.modules.filter((m) => isUnitAuthored(m.id)).length,
    0,
  );

  return (
    <div>
      <header className="shell pb-16 pt-14">
        <p className="eyebrow">The full map</p>
        <h1 className="heading-xl mt-4 max-w-[22ch]">
          {map.phases.length} phases. One system. No filler.
        </h1>
        <p className="lead mt-5">
          Here is the whole route before you pay for step one. You build an
          return reconciliation and dispute triage pipeline for OmniCart
          Operations, a simulated B2B wholesale distributor with messy
          real-world data. Each phase adds a part the pipeline needs to run.
          Python and APIs first. Then models, prompts, retrieval, and agents.
          Then the part that keeps it honest in production: evaluation, cost,
          security, and deployment.
        </p>
        <div className="mt-10 flex flex-wrap gap-x-14 gap-y-8">
          <div>
            <p className="stat-number">{map.phases.length}</p>
            <p className="stat-label">Phases</p>
          </div>
          <div>
            <p className="stat-number">{totalModules}</p>
            <p className="stat-label">Units</p>
          </div>
          <div>
            <p className="stat-number">{Math.round(totalHours / 10) * 10}</p>
            <p className="stat-label">Estimated hours</p>
          </div>
        </div>
        <p className="mt-8 max-w-[68ch] text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          {openModules} of these {totalModules} units are open today, and the
          rest are mapped below so you can see the whole route before you
          spend a cent. Planned units show a title only until they open.
        </p>
      </header>

      <div className="shell space-y-10 pb-24">
        {map.phases.map((phase) => (
          <section
            key={phase.id}
            id={phase.id}
            aria-labelledby={`${phase.id}-title`}
            className="card-dark scroll-mt-24"
          >
            <div className="flex flex-wrap items-start justify-between gap-6">
              <div className="max-w-[64ch]">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="chip chip-outline">Phase {phase.phase}</span>
                  {phase.badge ? <span className="chip chip-outline">{phase.badge}</span> : null}
                  <span className="text-[12px] font-medium tracking-[0.1em] text-moss-70">
                    ~{phase.est_hours} HOURS
                  </span>
                </div>
                <h2
                  id={`${phase.id}-title`}
                  className="heading-md mt-4 text-phosphor-white"
                >
                  {phase.title}
                </h2>
                <p className="mt-3 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                  {phase.why}
                </p>
                <p className="mt-2.5 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                  <strong className="font-medium text-phosphor-white">
                    You walk away with:
                  </strong>{" "}
                  {phase.outcome}
                </p>
                <p className="mt-2.5 text-[14px] leading-relaxed text-[color:var(--text-faint-on-dark)]">
                  Its job in the pipeline: {phase.pipeline_role}
                </p>
              </div>
            </div>

            <ul className="mt-8 grid gap-4 md:grid-cols-2">
              {phase.modules.map((m) => {
                // A unit is only a link once its lesson, rubric and checks exist
                // in content/. The rest are listed as planned, not linked into a
                // dead end.
                const authored = isUnitAuthored(m.id);
                return (
                  <li
                    key={m.id}
                    className="flex gap-4 rounded-lg border border-circuit-border bg-carbon-veil p-5"
                  >
                    <span className="font-goga text-[14px] font-medium text-moss-70">
                      {m.id}
                    </span>
                    <div className="min-w-0">
                      {authored ? (
                        <Link
                          href={`/units/${m.id}`}
                          className="font-goga text-[15.5px] font-medium text-phosphor-white underline-offset-4 hover:underline"
                        >
                          {m.title}
                        </Link>
                      ) : (
                        <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1.5">
                          <span className="font-goga text-[15.5px] font-medium text-[color:var(--text-muted-on-dark)]">
                            {m.title}
                          </span>
                          <span className="chip chip-outline">PLANNED</span>
                        </p>
                      )}
                      <p className="mt-1 text-[14px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                        {m.description}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ul>

            {phase.note ? (
              <p className="mt-6 border-t border-[color:var(--line-on-dark)] pt-4 text-[14px] text-[color:var(--text-faint-on-dark)]">
                {phase.note}
              </p>
            ) : null}
          </section>
        ))}
      </div>
    </div>
  );
}
