import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { getSessionUser } from "@/lib/auth";
import { ensureStudent } from "@/lib/enroll";
import { lookupSubmission } from "@/lib/grading";
import { fetchSubmissionGalleryProject, type StudentGalleryProject } from "@/lib/gallery";
import { StatusBanner } from "@/components/submission/status-banner";
import { SubmissionFacts } from "@/components/submission/submission-facts";
import { Layer1Section } from "@/components/submission/layer1-section";
import { JudgeSection } from "@/components/submission/judge-section";
import { VerdictFacts } from "@/components/submission/verdict-facts";
import { Timeline } from "@/components/submission/timeline";
import { GalleryShowcase } from "@/components/gallery/gallery-showcase";

export const dynamic = "force-dynamic";

type Props = {
  params: Promise<{ submissionId: string }>;
};

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { submissionId } = await props.params;
  const lookup = await lookupSubmission(submissionId);
  const title =
    lookup.state === "ok" ? `Submission #${lookup.view.submission.id}` : "Submission not found";
  return { title, robots: { index: false } };
}

export default async function SubmissionPage(props: Props) {
  const { submissionId } = await props.params;

  const user = await getSessionUser();
  if (!user) {
    redirect(`/sign-in?next=${encodeURIComponent(`/submissions/${submissionId}`)}`);
  }
  const bridged = await ensureStudent(user);
  const lookup = await lookupSubmission(submissionId);

  if (lookup.state === "not-found") notFound();

  if (lookup.state === "unreachable") {
    return (
      <div className="shell section">
        <div className="card-dark max-w-[62ch]">
          <h1 className="heading-lg">We could not load this verdict</h1>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            Verdicts would not load. Your submission and its result are
            untouched. Refresh.
          </p>
          <Link href="/me" className="btn btn-primary btn-sm mt-7">
            Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  const { submission, verdict, events } = lookup.view;

  if (bridged.state !== "ok") {
    return (
      <div className="shell section">
        <div className="card-dark max-w-[62ch]">
          <h1 className="heading-lg">One moment. Checking this is yours</h1>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            A verdict page opens only for the account that pushed the commit. We could not
            confirm yours. Refresh.
          </p>
        </div>
      </div>
    );
  }

  if (submission.student_id !== bridged.data) {
    notFound();
  }

  // Publishing is offered only on a passed submission, and only to its owner.
  const isPassed = verdict?.overall === "pass";
  let galleryProject: StudentGalleryProject | null = null;
  if (isPassed) {
    const galleryRes = await fetchSubmissionGalleryProject(submission.id);
    if (galleryRes.state === "ok") {
      galleryProject = galleryRes.data.project;
    }
  }

  return (
    <article>
      <header className="shell border-b border-[color:var(--line-on-dark)] pb-10 pt-14">
        <nav aria-label="Breadcrumb" className="text-[13px] text-[color:var(--text-faint-on-dark)]">
          <Link href="/me" className="hover:text-phosphor-white">
            Dashboard
          </Link>
          <span className="px-2">/</span>
          <Link href={`/units/${submission.unit_id}`} className="hover:text-phosphor-white">
            Unit {submission.unit_id}
          </Link>
          <span className="px-2">/</span>
          <span className="text-[color:var(--text-muted-on-dark)]">
            Submission #{submission.id}
          </span>
        </nav>

        <div className="mt-7 flex flex-wrap items-start justify-between gap-6">
          <div className="max-w-[62ch]">
            <p className="eyebrow">Submission #{submission.id}</p>
            <h1 className="heading-xl mt-4">Unit {submission.unit_id} result</h1>
            <p className="mt-4 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              This link is private. Only the account that pushed the commit can open it.
            </p>
          </div>

          <Link href={`/units/${submission.unit_id}`} className="btn btn-ghost btn-sm">
            Back to the unit
          </Link>
        </div>

        <div className="mt-9">
          <StatusBanner status={submission.status} verdict={verdict} />
        </div>
        <div className="mt-6">
          <SubmissionFacts view={lookup.view} studentEmail={user.email} />
        </div>
      </header>

      <div className="shell space-y-8 py-12">
        {verdict ? (
          <>
            <Layer1Section layer1={verdict.json?.layer1} />
            <JudgeSection judge={verdict.json?.judge} />
            <VerdictFacts view={lookup.view} />
            <GalleryShowcase
              submissionId={submission.id}
              unitId={submission.unit_id}
              isPassed={isPassed}
              defaultRepoUrl={submission.repo_url}
              initialProject={galleryProject}
            />
          </>
        ) : submission.status === "error" ? (
          <section className="card-dark max-w-[74ch]">
            <h2 className="heading-md">What an error means</h2>
            <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              We wrote no verdict. The run broke before it finished, or you had spent
              your grading budget. An error is never a failed attempt: the timeline
              below names which of the two it was.
            </p>
            <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              If the run broke, push again. If the budget is the problem, the budget on your
              dashboard will show it.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link href="/me" className="btn btn-primary btn-sm">
                Check your budget
              </Link>
              <Link href="/submit" className="btn btn-ghost btn-sm">
                How to push again
              </Link>
            </div>
          </section>
        ) : (
          <section className="card-dark max-w-[74ch]">
            <h2 className="heading-md">While you wait</h2>
            <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              Automated checks run first, then rubric review reads your commit. This page
              fills in as each finishes: reload to see the current state.
            </p>
            <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              Go make coffee. The result will be here whenever you come back.
            </p>
          </section>
        )}

        <Timeline events={events} />
      </div>
    </article>
  );
}
