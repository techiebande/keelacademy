import { ContentArriving } from "@/components/content-arriving";
import type { FaqEntry, UnitYaml } from "@/lib/content";

function anchorOf(fixRef: string): string | null {
  const hashIndex = fixRef.indexOf("#");
  return hashIndex >= 0 ? fixRef.slice(hashIndex + 1) : null;
}

/**
 * The unit's own failure modes, each with the fix behind a disclosure. A script
 * places this where its prose has just said what tends to go wrong.
 */
export function UnstuckList({ unit, faq }: { unit: UnitYaml; faq: FaqEntry[] | null }) {
  return (
    <div className="apparatus">
        <div className="apparatus-head">
          <p className="apparatus-label">What usually breaks</p>
          {unit.unstuck.length > 0 ? (
            <span className="chip chip-outline font-code-mono text-[11px]">
              {unit.unstuck.length} {unit.unstuck.length === 1 ? "SYMPTOM" : "SYMPTOMS"}
            </span>
          ) : null}
        </div>
        {unit.unstuck.length > 0 ? (
          <div className="space-y-4">
            {unit.unstuck.map((entry) => {
              const anchor = anchorOf(entry.fix_ref);
              const answer = anchor
                ? (faq ?? []).find((item) => item.anchor === anchor)
                : undefined;
              return (
                <details
                  key={entry.fix_ref}
                  className="card-dark p-0 overflow-hidden border border-circuit-border group"
                >
                  <summary className="flex items-center justify-between gap-4 p-5 cursor-pointer bg-carbon-veil select-none hover:bg-carbon-veil/80 transition-colors list-none">
                    <div className="flex items-center gap-3">
                      <span className="h-2 w-2 shrink-0 rounded-full bg-lime-pulse" aria-hidden />
                      <span className="font-goga text-[16px] font-medium text-phosphor-white">{entry.symptom}</span>
                    </div>
                    <span className="flex shrink-0 items-center gap-2">
                      <span className="chip chip-outline text-[11px]">FIX</span>
                      <svg
                        aria-hidden
                        viewBox="0 0 12 12"
                        width="12"
                        height="12"
                        className="text-[color:var(--text-faint-on-dark)] transition-transform group-open:rotate-180"
                      >
                        <path
                          d="M2.5 4.5 6 8 9.5 4.5"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </span>
                  </summary>
                  {answer ? (
                    <div
                      className="lesson-prose p-6 border-t border-phosphor-blue-black bg-ground-iron/40"
                      dangerouslySetInnerHTML={{ __html: answer.html }}
                    />
                  ) : (
                    <div className="p-6 border-t border-phosphor-blue-black bg-ground-iron/40">
                      <ContentArriving what="The fix for this symptom" />
                    </div>
                  )}
                </details>
              );
            })}
          </div>
        ) : (
          <ContentArriving what="Unstuck entries for this unit" />
        )}
    </div>
  );
}
