import Link from "next/link";

export type ChapterBeat = { id: string; name: string; estMinutes?: number };

/**
 * The head of a lesson: where you are, what it is called, what it is measured on,
 * and the beats it runs through.
 *
 * It replaces a header plus a three-cell bordered spec panel. The panel made three
 * facts look like an instrument you could operate; they are metadata, so they are
 * set as one mono line separated by hairlines.
 *
 * The beat list is the same eight entries the margin rail carries, printed at every
 * width. That is what lets the rail be an enhancement rather than the only way
 * through the page: below the rail's breakpoint the reader still gets the whole
 * shape of the lesson before starting it.
 */
export function ChapterOpener({
  unitId,
  phase,
  title,
  specs,
}: {
  unitId: string;
  phase: number;
  title: string;
  /** Short mono facts, already phrased: "PHASE 3", "6 CHECKS, 5 CRITERIA". */
  specs: string[];
  beats?: ChapterBeat[];
}) {
  return (
    <header className="lesson-canvas flow chapter-opener">
      <nav aria-label="Breadcrumb" className="chapter-crumbs">
        <Link href="/curriculum">CURRICULUM</Link>
        <span aria-hidden="true">/</span>
        <Link href={`/curriculum#phase-${phase}`}>PHASE-{phase}</Link>
        <span aria-hidden="true">/</span>
        <span className="chapter-crumb-here">UNIT-{unitId}</span>
      </nav>

      <h1 className="chapter-title">{title}</h1>

      <p className="chapter-specs">
        {specs.map((spec) => (
          <span key={spec}>{spec}</span>
        ))}
      </p>
    </header>
  );
}
