"use client";

import { useEffect } from "react";

/**
 * Puts a copy button in the head of every code figure on the page.
 *
 * Why the DOM rather than JSX: a lesson's fenced code is rendered to an HTML
 * string by `marked` and injected with `dangerouslySetInnerHTML`, so a figure is
 * a grandchild of a prose blob and there is no React element to wrap. This
 * mounts once per page and decorates whatever the markdown produced, the same
 * way the diagram runtime does.
 *
 * Why the button is not in the server HTML: without JavaScript it could not copy
 * anything, and a control that does nothing is worse than no control. The same
 * applies when the clipboard API is missing, which is every insecure origin, so
 * the button is not injected there either.
 */

const RESET_MS = 1600;

export function CodeFigureRuntime() {
  useEffect(() => {
    const clipboard = navigator.clipboard;
    if (!clipboard?.writeText) return;

    const heads = Array.from(
      document.querySelectorAll<HTMLElement>("figure.code-fig > .code-fig-head"),
    ).filter((head) => !head.querySelector(".code-fig-copy"));
    if (heads.length === 0) return;

    const timers = new Set<ReturnType<typeof setTimeout>>();

    for (const head of heads) {
      const code = head.parentElement?.querySelector("pre code");
      if (!code) continue;

      const name = head.querySelector(".code-fig-name")?.textContent?.trim();
      const button = document.createElement("button");
      button.type = "button";
      button.className = "code-fig-copy";
      button.textContent = "Copy";
      button.setAttribute("aria-live", "polite");
      button.setAttribute("aria-label", name ? `Copy the code from ${name}` : "Copy this code");

      button.addEventListener("click", () => {
        void clipboard.writeText(code.textContent ?? "").then(
          () => {
            button.textContent = "Copied";
            const timer = setTimeout(() => {
              button.textContent = "Copy";
              timers.delete(timer);
            }, RESET_MS);
            timers.add(timer);
          },
          (error) => {
            // A denied clipboard permission is the reader's own setting, so say
            // what happened on the button and leave the code where it is.
            console.warn("[code-figure] copy refused:", error);
            button.textContent = "Copy blocked";
          },
        );
      });

      // The language label stays at the right edge; the button sits beside it.
      head.append(button);
    }

    return () => {
      for (const timer of timers) clearTimeout(timer);
    };
  }, []);

  return null;
}
