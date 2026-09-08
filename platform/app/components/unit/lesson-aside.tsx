/**
 * An aside: a digression the reader can take or skip, authored as
 * `::: aside <title>` up to a closing `:::`.
 *
 * It exists because a lesson keeps collecting things that are true and useful but
 * would break the sentence they interrupt: the shortcut a reader is about to
 * reach for, the simplification being made on purpose, the depth that only some
 * readers want. Printing all of it inline makes the main line hard to follow;
 * cutting it makes the lesson thinner. Behind a disclosure, the authored title
 * says what the digression is for, so skipping it is an informed choice.
 *
 * Native `details`, so it works with no client JavaScript, and `.reveal` already
 * carries the focus ring and the plus/minus affordance.
 */
export function LessonAside({
  id,
  title,
  html,
}: {
  id: string;
  title: string;
  html: string;
}) {
  return (
    <details id={id} className="callout callout-aside reveal reveal-flush">
      <summary>{title}</summary>
      <div className="lesson-prose reveal-body" dangerouslySetInnerHTML={{ __html: html }} />
    </details>
  );
}
