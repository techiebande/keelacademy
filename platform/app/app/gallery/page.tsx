import type { Metadata } from "next";
import Link from "next/link";
import { fetchGalleryProjects } from "@/lib/gallery";
import { loadCurriculumMap } from "@/lib/content";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "What students built",
  description:
    "Projects students chose to publish, each one attached to the verdict that passed it.",
};

type Props = {
  searchParams: Promise<{ phase?: string; unit_id?: string; search?: string }>;
};

export default async function GalleryPage({ searchParams }: Props) {
  const { phase, unit_id, search } = await searchParams;
  const phaseNum = phase !== undefined && phase !== "" ? parseInt(phase, 10) : undefined;
  const result = await fetchGalleryProjects({
    phase: isNaN(phaseNum as number) ? undefined : phaseNum,
    unitId: unit_id || undefined,
    search: search || undefined,
    limit: 50,
  });
  const projects = result.state === "ok" ? result.data.projects : [];
  const total = result.state === "ok" ? result.data.total : 0;

  const phaseFilters = [
    { label: "All phases", value: undefined as string | undefined },
    ...loadCurriculumMap().phases.map((p) => ({
      label: `Phase ${p.phase}`,
      value: String(p.phase),
    })),
  ];

  return (
    <div>
      <header className="shell border-b border-[color:var(--line-on-dark)] pb-10 pt-14">
        <p className="eyebrow">Published work</p>
        <h1 className="heading-xl mt-4">What students built</h1>
        <p className="lead mt-5 max-w-[68ch]">
          Every project here passed its unit. The student who wrote it chose to publish
          it. Each one shows how many rubric criteria it cleared.
        </p>
        <p className="mt-6 font-code-mono text-[13px] text-moss-70">
          {result.state === "ok"
            ? total === 1
              ? "1 published project"
              : `${total.toLocaleString("en-US")} published projects`
            : "Count unavailable"}
        </p>
      </header>

      <div className="shell py-12">
        <section aria-label="Filters" className="space-y-6">
          <nav aria-label="Filter by phase">
            <ul className="flex flex-wrap gap-2">
              {phaseFilters.map((f) => {
                const href = f.value !== undefined ? `/gallery?phase=${f.value}` : "/gallery";
                const active = (phase ?? undefined) === f.value;
                return (
                  <li key={f.label}>
                    <Link
                      href={href}
                      aria-current={active ? "page" : undefined}
                      className={
                        active
                          ? "chip chip-live no-underline"
                          : "chip chip-outline no-underline hover:text-phosphor-white"
                      }
                    >
                      {f.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>

          <form action="/gallery" method="get" className="flex flex-wrap items-end gap-3">
            {phase ? <input type="hidden" name="phase" value={phase} /> : null}
            <div className="min-w-[16rem] flex-1">
              <label htmlFor="gallery-search" className="field-label">
                Search titles and descriptions
              </label>
              <input
                id="gallery-search"
                name="search"
                type="search"
                defaultValue={search ?? ""}
                placeholder="invoice reconciliation"
                className="field-input"
              />
            </div>
            <button type="submit" className="btn btn-primary btn-sm">
              Search
            </button>
          </form>
        </section>
        {result.state !== "ok" ? (
          <div className="card-dark mt-10 max-w-[62ch]">
            <h2 className="heading-md">We could not load the gallery</h2>
            <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              We could not load the gallery. Refresh.
            </p>
          </div>
        ) : projects.length === 0 ? (
          <div className="card-dark mt-10 max-w-[62ch]">
            <h2 className="heading-md">Nothing matches that</h2>
            <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              {search || phase
                ? "No published project matches those filters yet. Widen the search, as the gallery is young."
                : "No projects have been published yet. Yours could be first."}
            </p>
          </div>
        ) : (
          <ul className="mt-10 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {projects.map((proj) => (
              <li key={proj.id} className="card-dark flex flex-col">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="chip chip-outline">UNIT {proj.unit_id}</span>
                  <span className="font-code-mono text-[12.5px] text-[color:var(--text-faint-on-dark)]">
                    Phase {proj.phase}
                  </span>
                </div>
                <h2 className="mt-4 font-goga text-[19px] leading-snug font-medium">
                  <Link
                    href={`/gallery/${proj.id}`}
                    className="text-phosphor-white underline-offset-4 hover:underline"
                  >
                    {proj.title}
                  </Link>
                </h2>
                <p className="mt-2 text-[13.5px] text-[color:var(--text-faint-on-dark)]">
                  {proj.student_name}
                </p>
                <p className="mt-4 flex-1 text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                  {proj.description}
                </p>
                <p className="mt-6 border-t border-[color:var(--line-on-dark-strong)] pt-4 font-code-mono text-[13px] text-moss-70">
                  {`${proj.verdict.criteria_passed} of ${proj.verdict.total_criteria} criteria passed`}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
