import { formatUtc, type TimelineEvent } from "@/lib/grading";
import { humanizeId } from "@/lib/text";

const EVENT_LABELS: Record<string, string> = {
  "submission.created": "Submission received",
  "verdict.issued": "Verdict issued",
  "grade.budget_blocked": "Budget blocked",
};

function eventLabel(event: TimelineEvent): string {
  return EVENT_LABELS[event.type] ?? humanizeId(event.type);
}

export function Timeline({ events }: { events: TimelineEvent[] }) {
  return (
    <section id="timeline" aria-labelledby="timeline-title" className="card-dark scroll-mt-24">
      <h2 id="timeline-title" className="heading-md">
        What happened, in order
      </h2>
      <p className="mt-3 max-w-[74ch] text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
        Every step the grading run took for this commit, in order.
      </p>

      {events.length > 0 ? (
        <ol className="mt-7">
          {events.map((event) => {
            const detail = typeof event.payload.detail === "string" ? event.payload.detail : null;
            return (
              <li
                key={event.seq}
                className="flex flex-wrap items-baseline justify-between gap-3 border-t border-[color:var(--line-on-dark-strong)] py-4 first:border-t-0 first:pt-0"
              >
                <div className="flex items-baseline gap-3">
                  <span className="font-code-mono text-[13px] text-[color:var(--text-faint-on-dark)]">
                    #{event.seq}
                  </span>
                  <span className="text-[15px] text-phosphor-white">{eventLabel(event)}</span>
                </div>
                <div className="flex flex-wrap items-baseline gap-4">
                  {detail ? (
                    <code className="font-code-mono text-[13px] text-moss-70">{detail}</code>
                  ) : null}
                  <span className="font-code-mono text-[13px] text-[color:var(--text-faint-on-dark)]">
                    {formatUtc(event.occurred_at)}
                  </span>
                </div>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="mt-6 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          No events yet.
        </p>
      )}
    </section>
  );
}
