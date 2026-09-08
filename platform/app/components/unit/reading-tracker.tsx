"use client";

import { useEffect } from "react";
import { saveReadingPosition, getSessionStartTime } from "@/lib/reading-position";
import type { ScriptPhase } from "@/lib/content";

/**
 * Client component that monitors reading scroll position in a unit script and
 * updates `keel-reading-position` in localStorage (lesson-flow spec U3).
 *
 * Progress is word-based (M6.2): the saved ratio is words scrolled past over
 * words total, computed from each beat's authored wordCount, not pixels (a
 * long code block and a short paragraph count as what they are: text to
 * read). Falls back to the pixel ratio only when a unit carries no word
 * counts. Recording pauses while the tab is hidden: hidden time is not
 * reading time, so no position is saved from a background tab.
 *
 * Debounced to save at most once every 3 seconds. Silent on failures.
 */
export function ReadingTracker({
  unitId,
  phases,
}: {
  unitId: string;
  phases: ScriptPhase[];
}) {
  useEffect(() => {
    getSessionStartTime();

    const beats: { id: string; name: string; phaseId: string; phaseName: string; words: number }[] = [];
    for (const phase of phases) {
      const phaseName = phase.id.charAt(0).toUpperCase() + phase.id.slice(1);
      for (const entry of phase.contents) {
        beats.push({
          id: entry.id,
          name: entry.name,
          phaseId: phase.id,
          phaseName,
          words: entry.wordCount ?? 0,
        });
      }
    }

    const nodes = beats
      .map((b) => ({ beat: b, node: document.getElementById(b.id) }))
      .filter((item): item is { beat: typeof item.beat; node: HTMLElement } => item.node !== null);
    const totalWords = nodes.reduce((sum, item) => sum + item.beat.words, 0);

    let lastSaved = 0;
    const SAVE_INTERVAL_MS = 3000;

    const record = () => {
      const now = Date.now();
      if (now - lastSaved < SAVE_INTERVAL_MS) return;
      // Paused while hidden: no saves from a background tab.
      if (document.hidden) return;

      const docHeight = document.documentElement.scrollHeight - window.innerHeight;
      const pixelRatio = docHeight > 0 ? Math.max(0, Math.min(1, window.scrollY / docHeight)) : 0;

      let active = nodes[0]?.beat ?? null;
      let scrolledPastWords = 0;
      for (const item of nodes) {
        if (item.node.getBoundingClientRect().top <= 140) {
          active = item.beat;
          scrolledPastWords += item.beat.words;
        }
      }

      const scrollRatio =
        totalWords > 0
          ? Math.max(0, Math.min(1, scrolledPastWords / totalWords))
          : pixelRatio;

      if (active) {
        saveReadingPosition({
          unitId,
          phaseId: active.phaseId,
          phaseName: active.phaseName,
          headingId: active.id,
          headingTitle: active.name,
          scrollRatio,
          savedAt: now,
        });
        lastSaved = now;
      }
    };

    let frame = 0;
    const onScroll = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        record();
      });
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
    };
  }, [unitId, phases]);

  return null;
}
