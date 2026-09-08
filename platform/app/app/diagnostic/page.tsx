import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/auth";
import { ensureStudent } from "@/lib/enroll";
import { loadPlacementDiagnostic } from "@/lib/content";
import { fetchDiagnosticAttempts, type DiagnosticAttempt } from "@/lib/practice";
import { DiagnosticWorkbench } from "@/components/diagnostic-workbench";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Placement check",
  robots: { index: false },
};

export default async function DiagnosticPage() {
  const user = await getSessionUser();
  if (!user) {
    redirect("/sign-in?next=/diagnostic");
  }

  const bridged = await ensureStudent(user);
  const studentId = bridged.state === "ok" ? bridged.data : 0;

  const diagnostic = loadPlacementDiagnostic("placement-phase-1");
  if (!diagnostic) {
    return (
      <div className="shell section">
        <div className="card-dark max-w-[62ch]">
          <h1 className="heading-lg">We could not load the placement check</h1>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            Nothing is wrong with your account. Refresh, or start at the beginning
            and skip this.
          </p>
          <Link href="/map" className="btn btn-primary btn-sm mt-7">
            Open your map
          </Link>
        </div>
      </div>
    );
  }

  let initialAttempts: DiagnosticAttempt[] = [];
  if (studentId > 0) {
    const attemptsResult = await fetchDiagnosticAttempts(studentId);
    if (attemptsResult.state === "ok") {
      initialAttempts = attemptsResult.data.attempts;
    }
  }

  return (
    <div>
      <header className="shell border-b border-[color:var(--line-on-dark)] pb-10 pt-14">
        <p className="eyebrow">Placement check</p>
        <h1 className="heading-xl mt-4 max-w-[28ch]">
          Already know Python? Prove it and skip ahead.
        </h1>
        <p className="lead mt-5 max-w-[68ch]">
          {`${diagnostic.questions.length} multiple-choice questions, ${diagnostic.est_minutes} minutes. Score ${diagnostic.passing_threshold_pct}% or better and units ${diagnostic.pass_skip_units.join(", ")} open for you. Score under that and you start at ${diagnostic.fail_baseline_units.join(", ")}, where everyone else starts.`}
        </p>
        <p className="mt-5 max-w-[68ch] text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          This check carries no grade and costs nothing. Skip it if you want, because nobody will know, and nothing breaks.
        </p>
      </header>

      <div className="shell py-12">
        <DiagnosticWorkbench
          diagnostic={diagnostic}
          studentId={studentId}
          initialAttempts={initialAttempts}
        />
      </div>
    </div>
  );
}
