import type { SubmissionStatus, Verdict } from "@/lib/grading";

function bannerConfig(
  status: SubmissionStatus,
  verdict: Verdict | null,
): {
  title: string;
  body: string;
  badge: string;
  tone: "outline" | "live" | "alert";
} {
  if (status === "queued") {
    return {
      title: "Queued",
      body: "Your push arrived. It waits in line to run.",
      badge: "QUEUED",
      tone: "outline",
    };
  }
  if (status === "grading") {
    return {
      title: "Grading now",
      body: "The automated checks are running against your commit, and rubric review follows them.",
      badge: "GRADING",
      tone: "outline",
    };
  }
  if (status === "error") {
    return {
      title: "Grading stopped early",
      body: "Grading stopped before we wrote a verdict. Your work is safe.",
      badge: "ERROR",
      tone: "alert",
    };
  }
  if (verdict?.overall === "pass") {
    return {
      title: "Passed",
      body: "Every automated check and every rubric criterion passed. Nice.",
      badge: "PASSED",
      tone: "live",
    };
  }
  if (verdict?.overall === "fail") {
    return {
      title: "Not yet",
      body: "At least one automated check or rubric criterion did not pass. The details below name it.",
      badge: "NOT YET",
      tone: "alert",
    };
  }
  return {
    title: "Grading finished",
    body: "The details are below.",
    badge: "GRADED",
    tone: "outline",
  };
}

export function StatusBanner({
  status,
  verdict,
}: {
  status: SubmissionStatus;
  verdict: Verdict | null;
}) {
  const config = bannerConfig(status, verdict);

  return (
    <div
      data-keel-status={status}
      className="rounded-lg border border-circuit-border bg-carbon-veil p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-[62ch]">
          <h2 className="heading-md">{config.title}</h2>
          <p className="mt-3 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            {config.body}
          </p>
        </div>
        <span className={`chip chip-${config.tone}`}>{config.badge}</span>
      </div>
    </div>
  );
}
