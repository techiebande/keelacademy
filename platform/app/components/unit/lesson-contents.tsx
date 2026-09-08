"use client";

import { useEffect, useState } from "react";

export type ContentsEntry = {
  id: string;
  name: string;
  headings: { id: string; text: string }[];
  estMinutes?: number;
};

/**
 * The lesson's own beats, indexed in the page's left margin.
 *
 * Plain anchors that work before and without JavaScript, with a scroll listener
 * that only adds which entry you are reading. That is the whole client cost: an
 * earlier version also drew a bar reporting how far the viewport had travelled
 * through the lesson, which said nothing `aria-current` was not already saying.
 *
 * On a script page this is the only in-page navigation there is, so the entries
 * are numbered: the same ordinals appear beside the headings themselves and in the
 * chapter opener's list, and a reader who is on beat four can see it in three
 * places without any of them announcing a percentage.
 */
export function LessonContents({
  entries,
  readLine = 150,
}: {
  entries: ContentsEntry[];
  /**
   * How far down the viewport counts as "the line you are reading", in px. The
   * default clears the site header plus a unit's sticky section nav. A page with
   * no second bar passes a smaller number.
   */
  readLine?: number;
}) {
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    const ids = entries.flatMap((entry) => [entry.id, ...entry.headings.map((h) => h.id)]);
    const nodes = ids
      .map((id) => document.getElementById(id))
      .filter((node): node is HTMLElement => node !== null);

    const resolve = () => {
      let current: string | null = null;
      for (const node of nodes) {
        if (node.getBoundingClientRect().top - readLine <= 0) current = node.id;
      }
      setActiveId(current);
    };

    let frame = 0;
    const onScroll = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        resolve();
      });
    };

    resolve();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [entries, readLine]);

  return (
    <nav aria-label="Lesson contents" className="lesson-contents">
      <p className="eyebrow lesson-contents-title">In this lesson</p>
      <ol className="lesson-contents-list">
        {entries.map((entry, index) => (
          <li key={entry.id}>
            <a
              href={`#${entry.id}`}
              aria-current={entry.id === activeId ? "true" : undefined}
              className="lesson-contents-link lesson-contents-link-top"
            >
              <span className="lesson-contents-index" aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="lesson-contents-label">{entry.name}</span>
              {entry.estMinutes ? (
                <span className="lesson-contents-time" aria-label={`${entry.estMinutes} minutes`}>
                  {entry.estMinutes}m
                </span>
              ) : null}
            </a>
            {entry.headings.length > 0 ? (
              <ul className="lesson-contents-sublist">
                {entry.headings.map((heading) => (
                  <li key={heading.id}>
                    <a
                      href={`#${heading.id}`}
                      aria-current={heading.id === activeId ? "true" : undefined}
                      className="lesson-contents-link"
                    >
                      {heading.text}
                    </a>
                  </li>
                ))}
              </ul>
            ) : null}
          </li>
        ))}
      </ol>
    </nav>
  );
}
