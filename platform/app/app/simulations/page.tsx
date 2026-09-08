import type { Metadata } from "next";
import Link from "next/link";
import { getSessionUser } from "@/lib/auth";
import { ensureStudent } from "@/lib/enroll";
import { fetchStudentDefenses, listStudentSimulations } from "@/lib/simulation";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Practice conversations",
  description:
    "Run a discovery call and defend your build to a technical reviewer and a business owner, against personas grounded in the OmniCart Operations brief.",
};

// Display copy only. The behaviour of each persona comes from
// content/personas/*.yaml and content/personas/backstory/*.md. Keep the names
// and roles here in step with those files.
const TRACKS = [
  {
    id: "discovery-call",
    slug: "discovery",
    title: "Run a discovery call",
    persona: "Sarah Jenkins",
    role: "VP of Operations, OmniCart Operations",
    description:
      "Find what costs her time before you offer to build anything.",
    href: "/simulations/discovery",
  },
  {
    id: "technical-stakeholder",
    slug: "technical-stakeholder",
    title: "Defend it to an engineer",
    persona: "Marcus Vance",
    role: "Staff AI Architect, OmniCart Operations",
    description:
      "Answer for accuracy, cost, latency, and failure handling. Bring numbers, as charm does not count.",
    href: "/simulations/technical-stakeholder",
  },
  {
    id: "business-owner",
    slug: "business-owner",
    title: "Defend it to the budget holder",
    persona: "Elena Rostova",
    role: "Managing Director, OmniCart Operations",
    description:
      "Say what it saves in hours and money. Plain words only, because she signs invoices, not architecture diagrams.",
    href: "/simulations/business-owner",
  },
] as const;

export default async function SimulationsDirectoryPage() {
  const user = await getSessionUser();
  const bridged = user ? await ensureStudent(user) : null;
  const studentId = bridged && bridged.state === "ok" ? bridged.data : 0;
  const [defensesRes, allSimsRes] = await Promise.all([
    studentId > 0 ? fetchStudentDefenses(studentId) : null,
    studentId > 0 ? listStudentSimulations(studentId) : null,
  ]);
  const defenses = defensesRes && defensesRes.state === "ok" ? defensesRes.data : null;
  const allSims = allSimsRes && allSimsRes.state === "ok" ? allSimsRes.data : [];
  const discoverySims = allSims.filter((s) => s.persona_id === "discovery-call");
  const hasPassedDiscovery = discoverySims.some((s) => s.passed === true);
  const hasActiveDiscovery = discoverySims.some((s) => s.status === "in_progress");

  const getStatus = (trackId: string): "Passed" | "In progress" | "Not started" => {
    if (trackId === "discovery-call") {
      if (hasPassedDiscovery) return "Passed";
      if (hasActiveDiscovery || discoverySims.length > 0) return "In progress";
      return "Not started";
    }
    if (trackId === "technical-stakeholder") {
      const s = defenses?.technical_stakeholder;
      if (s?.passed) return "Passed";
      if (s?.latest_simulation_id) return "In progress";
      return "Not started";
    }
    if (trackId === "business-owner") {
      const s = defenses?.business_owner;
      if (s?.passed) return "Passed";
      if (s?.latest_simulation_id) return "In progress";
      return "Not started";
    }
    return "Not started";
  };

  return (
    <div>
      <header className="shell border-b border-[color:var(--line-on-dark)] pb-10 pt-14">
        <p className="eyebrow">Practice conversations</p>
        <h1 className="heading-xl mt-4 max-w-[28ch]">
          The part of the job where you talk
        </h1>
        <p className="lead mt-5 max-w-[68ch]">
          Sooner or later someone who did not build it will ask you to explain what you
          built. These three conversations are the rehearsal room: run them as many
          times as you want.
        </p>
        <p className="mt-6 max-w-[68ch] rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          You talk with an AI following a written brief. No real employee joins these calls.
          You can read the brief in the curriculum before you start.
        </p>
      </header>

      <div className="shell space-y-8 py-12">
        {!user ? (
          <div className="card-dark max-w-[52ch]">
            <h2 className="heading-md">Sign in to start one</h2>
            <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              We save conversations to your account. Come back to a transcript and spot what
              you would say differently.
            </p>
            <Link href="/sign-in?next=/simulations" className="btn btn-primary btn-sm mt-7">
              Sign in
            </Link>
          </div>
        ) : (
          <>
            {defenses ? (
              <section aria-labelledby="clearance-title" className="card-dark">
                <h2 id="clearance-title" className="heading-md">
                  Where your two defences stand
                </h2>
                <p className="mt-3 max-w-[70ch] text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                  Both have to pass before the capstone counts as defended.
                </p>
                <dl className="mt-7 grid gap-px overflow-hidden rounded-lg border border-circuit-border bg-circuit-border sm:grid-cols-3">
                  <DefenceStat
                    label="Technical reviewer"
                    passed={defenses.technical_stakeholder.passed}
                  />
                  <DefenceStat label="Budget holder" passed={defenses.business_owner.passed} />
                    <DefenceStat label="Both" passed={defenses.defense_cleared} />
                </dl>
              </section>
            ) : null}

            <section aria-labelledby="tracks-title">
              <h2 id="tracks-title" className="heading-lg">
                Pick a conversation
              </h2>
              <ul className="mt-7 grid gap-6 lg:grid-cols-3">
                {TRACKS.map((track) => {
                  const status = getStatus(track.id);
                  return (
                    <li key={track.id} className="card-dark flex flex-col">
                      <span
                        className={
                          status === "Passed"
                            ? "chip chip-live"
                            : status === "In progress"
                              ? "chip chip-outline"
                              : "chip chip-outline"
                        }
                      >
                        {status.toUpperCase()}
                      </span>
                      <h3 className="mt-5 font-goga text-[19px] leading-snug font-medium">
                        <Link
                          href={track.href}
                          className="text-phosphor-white underline-offset-4 hover:underline"
                        >
                          {track.title}
                        </Link>
                      </h3>
                      <p className="mt-2 text-[13.5px] text-[color:var(--text-faint-on-dark)]">
                        {`${track.persona} · ${track.role}`}
                      </p>
                      <p className="mt-4 flex-1 text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                        {track.description}
                      </p>
                      <Link href={track.href} className="btn btn-primary btn-sm mt-6 self-start">
                        {status === "Not started" ? "Start" : "Open"}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function DefenceStat({ label, passed }: { label: string; passed: boolean }) {
  return (
    <div className="bg-ground-iron p-5">
      <dt className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
        {label}
      </dt>
      <dd className="mt-3">
        <span className={passed ? "chip chip-live" : "chip chip-outline"}>
          {passed ? "PASSED" : "NOT YET"}
        </span>
      </dd>
    </div>
  );
}
