import { LessonContents } from "@/components/unit/lesson-contents";
import type { Lesson, MarkdownDoc } from "@/lib/content";

/**
 * The lesson, rendered in the order it was written, followed by the assignment.
 *
 * There is no grammar to interpret here. A chapter is plain Markdown and it is
 * rendered whole; the only thing this component adds is the contents rail in
 * the left margin, built from the chapters' `##` headings, and a second chapter
 * heading when a unit is taught over more than one file.
 *
 * One grid wraps everything, so the reading column holds one left edge from the
 * title to the last line of the assignment. The grid is `.flow`, repeated on
 * every level that holds content, which is what lets a `<pre>` inside rendered
 * HTML break out of the reading column without subgrid.
 */
export function LessonBody({ lesson, assignment }: { lesson: Lesson; assignment: MarkdownDoc | null }) {
  const contents = lesson.chapters.flatMap((chapter) =>
    chapter.headings
      .filter((h) => h.level === 2)
      .map((h) => ({ id: h.id, name: h.text, headings: [] as { id: string; text: string }[] })),
  );
  if (assignment) {
    contents.push({ id: "assignment", name: assignment.title ?? "Your turn", headings: [] });
  }

  return (
    <div className="lesson-canvas flow unit-script-layout">
      <LessonContents entries={contents} readLine={READ_LINE} />

      <div id={BODY_ID} className="flow unit-script-body">
        <section id="lesson" data-keel-section="lesson" className="scroll-mt-28 flow unit-script-phase">
          {lesson.chapters.map((chapter, index) => (
            <div key={chapter.id} id={chapter.id} className="flow">
              {lesson.chapters.length > 1 ? (
                <h2 className="chapter-heading">
                  <span className="chapter-heading-number">Chapter {index + 1}</span>
                  {chapter.title}
                </h2>
              ) : null}
              <div className="lesson-prose flow" dangerouslySetInnerHTML={{ __html: chapter.html }} />
            </div>
          ))}
        </section>

        {assignment ? (
          <section id="assignment" data-keel-section="assignment" className="scroll-mt-28 flow unit-script-phase">
            <h2 className="chapter-heading">{assignment.title ?? "Your turn"}</h2>
            <div className="lesson-prose flow" dangerouslySetInnerHTML={{ __html: assignment.html }} />
          </section>
        ) : null}
      </div>
    </div>
  );
}

/** The element the rail measures its scroll position against. */
const BODY_ID = "unit-script-body";

/** The page has no second sticky bar, so the read line clears the 64px header. */
const READ_LINE = 88;
