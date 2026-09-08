import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/auth";
import { ensureStudent } from "@/lib/enroll";
import { listStudentSimulations, getSimulation, type SimulationSession } from "@/lib/simulation";
import { SimulationWorkbench } from "@/components/simulation/simulation-workbench";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Run a discovery call",
  robots: { index: false },
};

export default async function DiscoverySimulationPage() {
  const user = await getSessionUser();
  if (!user) {
    redirect("/sign-in?next=/simulations/discovery");
  }

  const bridged = await ensureStudent(user);
  const studentId = bridged.state === "ok" ? bridged.data : 0;

  let initialSession: SimulationSession | null = null;
  if (studentId > 0) {
    const listRes = await listStudentSimulations(studentId);
    if (listRes.state === "ok") {
      const latestSummary = listRes.data.find((s) => s.persona_id === "discovery-call");
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
          <span className="text-[color:var(--text-muted-on-dark)]">Discovery call</span>
        </nav>
        <h1 className="heading-xl mt-7 max-w-[28ch]">Run a discovery call</h1>
        <p className="lead mt-5 max-w-[68ch]">
          You have thirty minutes with an operations lead who has a problem and no brief.
          Find the problem first: pitching comes later, and only if she asks.
        </p>
      </header>

      <div className="shell py-12">
        <SimulationWorkbench
          initialSession={initialSession}
          studentId={studentId}
          personaId="discovery-call"
        />
      </div>
    </div>
  );
}
