import { ContentArriving } from "@/components/content-arriving";
import { PracticeWorkbench } from "@/components/unit/practice-workbench";
import { RetrievalDrill } from "@/components/unit/retrieval-drill";
import { ExplainItBackCard } from "@/components/unit/explain-it-back-card";
import type {
  PracticeAttemptSummary,
  PracticeManifest,
  RetrievalAttemptSummary,
  ReviewQueueItem,
} from "@/lib/practice";

/**
 * The platform's practice apparatus, rendered after the lesson and the
 * assignment. Each card carries a one-word label and no bridging copy: every
 * sentence a student reads about the work is in assignment.md.
 */
export function CompletionWorkbenchCard({
  unitId,
  manifest,
  initialAttempts,
  isEnrolled,
  isSignedIn,
  serviceDown,
}: {
  unitId: string;
  manifest: PracticeManifest | null;
  initialAttempts: PracticeAttemptSummary[];
  isEnrolled: boolean;
  isSignedIn: boolean;
  serviceDown: boolean;
}) {
  return (
    <div id="practice" className="card-dark space-y-6">
      <div className="border-b border-phosphor-blue-black pb-4">
        <h3 className="font-goga text-[17px] font-medium text-phosphor-white">
          Try your program against the checks
        </h3>
      </div>

      <div className="pt-4">
        <PracticeWorkbench
          unitId={unitId}
          manifest={manifest}
          initialAttempts={initialAttempts}
          isEnrolled={isEnrolled}
          isSignedIn={isSignedIn}
          serviceDown={serviceDown}
        />
      </div>

      {initialAttempts.some((a) => a.passed) ? (
        <ExplainItBackCard
          unitId={unitId}
          isSignedIn={isSignedIn}
          isEnrolled={isEnrolled}
        />
      ) : null}
    </div>
  );
}

export function RetrievalDrillCard({
  unitId,
  retrievalSeeds,
  initialRetrievalAttempts = [],
  dueSeedIndices = [],
  isEnrolled,
  isSignedIn,
  serviceDown,
  reviewItems = [],
}: {
  unitId: string;
  retrievalSeeds: string[];
  initialRetrievalAttempts?: RetrievalAttemptSummary[];
  dueSeedIndices?: number[];
  isEnrolled: boolean;
  isSignedIn: boolean;
  serviceDown: boolean;
  reviewItems?: ReviewQueueItem[];
}) {
  return (
    <div id="retrieval-drill" className="card-dark space-y-6">
      <div className="border-b border-phosphor-blue-black pb-4">
        <h3 className="font-goga text-[17px] font-medium text-phosphor-white">
          Retrieval drills
        </h3>
      </div>

      {retrievalSeeds.length > 0 ? (
        <div className="space-y-6">
          <p className="text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            Close the lesson and explain each idea from memory. The lesson grades each answer, and
            wrong ones return for review.
          </p>

          <RetrievalDrill
            unitId={unitId}
            seeds={retrievalSeeds}
            initialAttempts={initialRetrievalAttempts}
            dueSeedIndices={dueSeedIndices}
            isEnrolled={isEnrolled}
            isSignedIn={isSignedIn}
            serviceDown={serviceDown}
            reviewItems={reviewItems}
          />
        </div>
      ) : (
        <ContentArriving what="Retrieval practice seeds" />
      )}
    </div>
  );
}
