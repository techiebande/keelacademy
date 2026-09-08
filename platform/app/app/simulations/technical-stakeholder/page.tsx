import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/auth";
import { ensureStudent } from "@/lib/enroll";
import { listStudentSimulations, getSimulation, type SimulationSession } from "@/lib/simulation";
import { SimulationWorkbench } from "@/components/simulation/simulation-workbench";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Defend it to an engineer",
  robots: { index: false },
};

export default async function TechnicalStakeholderPage() {
  const user = await getSessionUser();
  if (!user) {
    redirect("/sign-in?next=/simulations/technical-stakeholder");
  }

  const bridged = await ensureStudent(user);
  const studentId = bridged.state === "ok" ? bridged.data : 0;

  let initialSession: SimulationSession | null = null;
  if (studentId > 0) {
    const listRes = await listStudentSimulations(studentId);
    if (listRes.state === "ok") {
      const latestSummary = listRes.data.find((s) => s.persona_id === "technical-stakeholder");
      if (latestSummary) {
        const detailRes = await getSimulation(latestSummary.id, studentId);
        if (detailRes.state === "ok") {
          initialSession = detailRes.data;
        }
      }
    }
  }

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
          <span className="text-[color:var(--text-muted-on-dark)]">Technical reviewer</span>
        </nav>
        <h1 className="heading-xl mt-7 max-w-[28ch]">Defend it to an engineer</h1>
        <p className="lead mt-5 max-w-[68ch]">
          The capstone needs two defences, and this is the technical one. Bring numbers for
          accuracy, cost, latency, and failure handling. He has read your code and he will check.
        </p>
      </header>

      <div className="shell py-12">
        <SimulationWorkbench
          initialSession={initialSession}
          studentId={studentId}
          personaId="technical-stakeholder"
        />
      </div>
    </div>
  );
}
