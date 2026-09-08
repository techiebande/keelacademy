"use client";

import * as React from "react";
import type {
  OperationsSummaryResponse,
  MacroFunnelResponse,
  DropoffBreakdownResponse,
  UnitDetailResponse,
  FailureModeRecord,
  RetrievalSeedFailureRecord,
  ConciergeQuestionRecord,
} from "@/lib/analytics";
import { humanizeId } from "@/lib/text";

interface AnalyticsDashboardProps {
  initialSummary: OperationsSummaryResponse | null;
  initialFunnel: MacroFunnelResponse | null;
  initialDropoff: DropoffBreakdownResponse | null;
}

type SortKey = "friction" | "dropoff" | "attempts" | "retrieval" | "concierge";

export function AnalyticsDashboard({
  initialSummary,
  initialFunnel,
  initialDropoff,
}: AnalyticsDashboardProps) {
  const [selectedPhase, setSelectedPhase] = React.useState<number | "all">("all");
  const [searchQuery, setSearchQuery] = React.useState("");
  const [sortBy, setSortBy] = React.useState<SortKey>("friction");
  const [sortAsc, setSortAsc] = React.useState(false);

  const [drilldownUnitId, setDrilldownUnitId] = React.useState<string | null>(null);
  const [drilldownLoading, setDrilldownLoading] = React.useState(false);
  const [drilldownError, setDrilldownError] = React.useState<string | null>(null);
  const [drilldownData, setDrilldownData] = React.useState<UnitDetailResponse | null>(null);

  // Phases come from the rows we were given, never from a hardcoded list.
  const phases = React.useMemo(() => {
    const seen = new Set<number>();
    for (const u of initialDropoff?.units ?? []) seen.add(u.phase);
    return [...seen].sort((a, b) => a - b);
  }, [initialDropoff]);

  const units = React.useMemo(() => {
    if (!initialDropoff?.units) return [];
    let list = [...initialDropoff.units];

    if (selectedPhase !== "all") {
      list = list.filter((u) => u.phase === selectedPhase);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (u) =>
          u.unit_id.toLowerCase().includes(q) ||
          u.title.toLowerCase().includes(q) ||
          `phase ${u.phase}`.toLowerCase().includes(q),
      );
    }

    list.sort((a, b) => {
      let valA = 0;
      let valB = 0;
      if (sortBy === "friction") {
        valA = a.friction_score;
        valB = b.friction_score;
      } else if (sortBy === "dropoff") {
        valA = a.drop_off_rate_pct;
        valB = b.drop_off_rate_pct;
      } else if (sortBy === "attempts") {
        valA = a.avg_attempts_to_pass;
        valB = b.avg_attempts_to_pass;
      } else if (sortBy === "retrieval") {
        valA = a.retrieval_first_try_fail_rate_pct;
        valB = b.retrieval_first_try_fail_rate_pct;
      } else if (sortBy === "concierge") {
        valA = a.concierge_turn_volume;
        valB = b.concierge_turn_volume;
      }
      return sortAsc ? valA - valB : valB - valA;
    });

    return list;
  }, [initialDropoff, selectedPhase, searchQuery, sortBy, sortAsc]);

  const handleOpenDrilldown = async (unitId: string) => {
    setDrilldownUnitId(unitId);
    setDrilldownLoading(true);
    setDrilldownError(null);
    setDrilldownData(null);
    try {
      const res = await fetch(`/api/admin/analytics/units/${encodeURIComponent(unitId)}`);
      if (!res.ok) {
        setDrilldownError("We could not load that unit.");
        return;
      }
      setDrilldownData((await res.json()) as UnitDetailResponse);
    } catch {
      setDrilldownError("We could not load that unit.");
    } finally {
      setDrilldownLoading(false);
    }
  };

  const handleCloseDrilldown = () => {
    setDrilldownUnitId(null);
    setDrilldownData(null);
    setDrilldownError(null);
  };

  return (
    <div className="space-y-10">
      {!initialSummary && !initialFunnel && !initialDropoff ? (
        <div className="card-dark max-w-[62ch]">
          <h2 className="heading-md">No telemetry came back</h2>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            No telemetry came back. Refresh. This page shows live numbers or nothing, never
            stale ones.
          </p>
        </div>
      ) : null}

      {initialSummary ? (
        <section aria-labelledby="summary-title">
          <h2 id="summary-title" className="heading-lg">
            Where the cohort stands
          </h2>
          <dl className="mt-7 grid gap-px overflow-hidden rounded-lg border border-circuit-border bg-circuit-border sm:grid-cols-2 lg:grid-cols-3">
            <Stat
              label="Enrolled students"
              value={initialSummary.total_enrolled_students.toLocaleString("en-US")}
            />
            <Stat
              label="Active in the last 30 days"
              value={`${initialSummary.active_30d_students.toLocaleString("en-US")} (${initialSummary.active_30d_rate_pct}%)`}
            />
            <Stat
              label="Weekly pod check-ins filed"
              value={`${initialSummary.weekly_pod_post_compliance_rate_pct}%`}
            />
            <Stat
              label="Reached the capstone"
              value={`${initialSummary.capstone_completion_rate_pct}%`}
            />
            <Stat
              label="Capstone graduates"
              value={initialSummary.total_capstone_graduates.toLocaleString("en-US")}
            />
            <Stat
              label="Average days to capstone"
              value={initialSummary.avg_days_to_capstone.toFixed(1)}
            />
          </dl>
        </section>
      ) : null}

      {initialFunnel ? (
        <section aria-labelledby="funnel-title">
          <h2 id="funnel-title" className="heading-lg">
            How far students get
          </h2>
          <p className="mt-3 font-code-mono text-[13px] text-moss-70">
            {`${initialFunnel.total_enrolled.toLocaleString("en-US")} enrolled`}
          </p>
          <div className="mt-6 overflow-x-auto">
            <table className="data-table">
              <caption className="sr-only">
                Enrollment funnel by stage, with conversion and drop-off rates
              </caption>
              <thead>
                <tr>
                  <th scope="col">Stage</th>
                  <th scope="col">Students</th>
                  <th scope="col">Carried on</th>
                  <th scope="col">Stopped here</th>
                </tr>
              </thead>
              <tbody>
                {initialFunnel.stages.map((st) => (
                  <tr key={st.id}>
                    <th scope="row">{st.name}</th>
                    <td>{st.count.toLocaleString("en-US")}</td>
                    <td>{`${st.conversion_pct}%`}</td>
                    <td>{`${st.drop_off_pct}%`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <section aria-labelledby="friction-title">
        <h2 id="friction-title" className="heading-lg">
          Unit by unit
        </h2>
        <p className="mt-3 max-w-[70ch] text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          Friction scores each unit. Sort to find what to rewrite first.
        </p>

        <div className="mt-7 flex flex-wrap items-end gap-4">
          <div>
            <label htmlFor="phase-filter" className="field-label">
              Phase
            </label>
            <select
              id="phase-filter"
              value={selectedPhase === "all" ? "all" : selectedPhase}
              onChange={(e) =>
                setSelectedPhase(e.target.value === "all" ? "all" : parseInt(e.target.value, 10))
              }
              className="field-input"
            >
              <option value="all">All phases</option>
              {phases.map((ph) => (
                <option key={ph} value={ph}>
                  {`Phase ${ph}`}
                </option>
              ))}
            </select>
          </div>

          <div className="min-w-[14rem] flex-1">
            <label htmlFor="search-input" className="field-label">
              Search unit or title
            </label>
            <input
              id="search-input"
              type="search"
              placeholder="3.2.1"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="field-input"
            />
          </div>

          <div>
            <label htmlFor="sort-filter" className="field-label">
              Sort by
            </label>
            <select
              id="sort-filter"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortKey)}
              className="field-input"
            >
              <option value="friction">Friction score</option>
              <option value="dropoff">Stopped here</option>
              <option value="attempts">Attempts to pass</option>
              <option value="retrieval">Retrieval checks missed first try</option>
              <option value="concierge">Questions asked</option>
            </select>
          </div>

          <button
            type="button"
            onClick={() => setSortAsc(!sortAsc)}
            aria-pressed={sortAsc}
            className="btn btn-ghost btn-sm"
          >
            {sortAsc ? "Lowest first" : "Highest first"}
          </button>
        </div>

        <p className="mt-5 font-code-mono text-[13px] text-moss-70" aria-live="polite">
          {`${units.length} ${units.length === 1 ? "unit" : "units"} shown`}
        </p>

        {units.length === 0 ? (
          <div className="card-dark mt-6 max-w-[62ch]">
            <h3 className="heading-md">Nothing matches that</h3>
            <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              No unit in the telemetry matches those filters.
            </p>
          </div>
        ) : (
          <div className="mt-6 overflow-x-auto">
            <table className="data-table">
              <caption className="sr-only">Per-unit friction metrics</caption>
              <thead>
                <tr>
                  <th scope="col">Unit</th>
                  <th scope="col">Phase</th>
                  <th scope="col">Stopped here</th>
                  <th scope="col">Attempts</th>
                  <th scope="col">Retrieval first try</th>
                  <th scope="col">Questions</th>
                  <th scope="col">Friction</th>
                  <th scope="col">
                    <span className="sr-only">Detail</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {units.map((u) => (
                  <tr key={u.unit_id}>
                    <th scope="row">
                      <span className="font-code-mono text-[13px] text-lime-pulse">
                        {u.unit_id}
                      </span>
                      <span className="mt-1 block text-[14px] text-[color:var(--text-muted-on-dark)]">
                        {u.title}
                      </span>
                    </th>
                    <td>{u.phase}</td>
                    <td>{`${u.drop_off_rate_pct}%`}</td>
                    <td>{u.avg_attempts_to_pass.toFixed(1)}</td>
                    <td>{`${u.retrieval_first_try_fail_rate_pct}% missed`}</td>
                    <td>{u.concierge_turn_volume.toLocaleString("en-US")}</td>
                    <td>{u.friction_score.toFixed(1)}</td>
                    <td>
                      <button
                        type="button"
                        onClick={() => handleOpenDrilldown(u.unit_id)}
                        className="btn btn-ghost btn-sm"
                      >
                        Open
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {drilldownUnitId ? (
        <section aria-labelledby="drilldown-title" className="card-dark">
          <div className="flex flex-wrap items-baseline justify-between gap-4">
            <h2 id="drilldown-title" className="heading-md">
              {`Unit ${drilldownUnitId} in detail`}
            </h2>
            <button type="button" onClick={handleCloseDrilldown} className="btn btn-ghost btn-sm">
              Close
            </button>
          </div>

          {drilldownLoading ? (
            <p className="mt-6 font-code-mono text-[13px] text-moss-70" aria-live="polite">
              Loading
            </p>
          ) : drilldownError ? (
            <p
              role="alert"
              className="mt-6 rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[14.5px] leading-relaxed text-phosphor-white"
            >
              {drilldownError}
            </p>
          ) : drilldownData ? (
            <div className="mt-6 space-y-8">
              <div>
                <h3 className="font-goga text-[18px] leading-snug font-medium text-phosphor-white">
                  {drilldownData.unit.title}
                </h3>
                <p className="mt-1 text-[13.5px] text-[color:var(--text-faint-on-dark)]">
                  {`Phase ${drilldownData.unit.phase}`}
                </p>
                <dl className="mt-6 grid gap-px overflow-hidden rounded-lg border border-circuit-border bg-circuit-border sm:grid-cols-3">
                  <Stat
                    label="Started it"
                    value={drilldownData.unit.starts_count.toLocaleString("en-US")}
                  />
                  <Stat
                    label="Finished it"
                    value={drilldownData.unit.completions_count.toLocaleString("en-US")}
                  />
                  <Stat
                    label="Median hours to pass"
                    value={String(drilldownData.unit.median_time_to_clear_hrs)}
                  />
                </dl>
              </div>

              {drilldownData.failure_modes?.length > 0 ? (
                <div>
                  <h4 className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
                    {`What the rubric catches most · ${drilldownData.failure_modes.length}`}
                  </h4>
                  <ul className="mt-4">
                    {drilldownData.failure_modes.map((fm: FailureModeRecord, i: number) => (
                      <li
                        key={i}
                        className="flex flex-wrap items-baseline justify-between gap-3 border-t border-[color:var(--line-on-dark-strong)] py-3 first:border-t-0 first:pt-0"
                      >
                        <span className="text-[15px] text-phosphor-white">
                          {humanizeId(fm.criterion_id)}
                        </span>
                        <span className="font-code-mono text-[12.5px] text-[color:var(--text-faint-on-dark)]">
                          {`${fm.type} · ${fm.occurrences.toLocaleString("en-US")} times`}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {drilldownData.retrieval_seed_failures?.length > 0 ? (
                <div>
                  <h4 className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
                    {`Retrieval prompts students miss first try · ${drilldownData.retrieval_seed_failures.length}`}
                  </h4>
                  <ul className="mt-4">
                    {drilldownData.retrieval_seed_failures.map(
                      (rs: RetrievalSeedFailureRecord, i: number) => (
                        <li
                          key={i}
                          className="border-t border-[color:var(--line-on-dark-strong)] py-4 first:border-t-0 first:pt-0"
                        >
                          <p className="text-[15px] text-phosphor-white">{rs.seed_prompt}</p>
                          <p className="mt-2 max-w-[74ch] text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                            {rs.feedback}
                          </p>
                        </li>
                      ),
                    )}
                  </ul>
                </div>
              ) : null}

              {drilldownData.concierge_questions?.length > 0 ? (
                <div>
                  <h4 className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
                    {`What students asked here · ${drilldownData.concierge_questions.length}`}
                  </h4>
                  <ul className="mt-4">
                    {drilldownData.concierge_questions.map(
                      (q: ConciergeQuestionRecord, i: number) => (
                        <li
                          key={i}
                          className="border-t border-[color:var(--line-on-dark-strong)] py-3 first:border-t-0 first:pt-0"
                        >
                          <span className="chip chip-outline">{q.mode.toUpperCase()}</span>
                          <p className="mt-3 max-w-[74ch] text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                            {q.question}
                          </p>
                        </li>
                      ),
                    )}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-ground-iron p-5">
      <dt className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
        {label}
      </dt>
      <dd className="mt-3 font-code-mono text-[22px] text-phosphor-white">{value}</dd>
    </div>
  );
}
