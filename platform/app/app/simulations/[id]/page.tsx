import type { Metadata } from "next";
import Link from "next/link";
import { redirect, notFound } from "next/navigation";
import { getSessionUser } from "@/lib/auth";
import { ensureStudent } from "@/lib/enroll";
import { getSimulation } from "@/lib/simulation";
import { formatUtc } from "@/lib/grading";
import { SimulationWorkbench } from "@/components/simulation/simulation-workbench";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Saved conversation",
  robots: { index: false },
};

// Display copy only. The personas themselves live in content/personas/.
const PERSONA_LABELS: Record<string, string> = {
  "discovery-call": "Discovery call with Sarah Jenkins",
  "technical-stakeholder": "Defence to Marcus Vance",
  "business-owner": "Defence to Elena Rostova",
};

export default async function SimulationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const user = await getSessionUser();
  if (!user) {
    redirect("/sign-in");
  }

  const bridged = await ensureStudent(user);
  const studentId = bridged.state === "ok" ? bridged.data : 0;

  const { id: idStr } = await params;
  const simulationId = parseInt(idStr, 10);
  if (isNaN(simulationId) || simulationId <= 0) {
    notFound();
  }

  const res = await getSimulation(simulationId, studentId);
  if (res.state !== "ok") {
    notFound();
  }

  const session = res.data;
  const personaLabel = PERSONA_LABELS[session.persona_id] ?? "Practice conversation";

  return (
    <div>
      <header className="shell border-b border-[color:var(--line-on-dark)] pb-10 pt-14">
        <nav
          aria-label="Breadcrumb"
          className="text-[13px] text-[color:var(--text-faint-on-dark)]"
        >
          <Link href="/simulations" className="hover:text-phosphor-white">
            Practice conversations
          </Link>
          <span className="px-2">/</span>
          <span className="text-[color:var(--text-muted-on-dark)]">
            Conversation #{session.id}
          </span>
        </nav>
        <h1 className="heading-xl mt-7 max-w-[28ch]">{personaLabel}</h1>
        <p className="mt-5 text-[15px] text-[color:var(--text-muted-on-dark)]">
          {session.completed_at
            ? `Started ${formatUtc(session.created_at)} · ended ${formatUtc(session.completed_at)}`
            : `Started ${formatUtc(session.created_at)}`}
        </p>
      </header>

      <div className="shell py-12">
        <SimulationWorkbench initialSession={session} studentId={studentId} />
      </div>
    </div>
  );
}
