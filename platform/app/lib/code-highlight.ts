import { createHighlighterCoreSync, type HighlighterCore } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";
import { transformerMetaHighlight, transformerNotationHighlight } from "@shikijs/transformers";
import bash from "@shikijs/langs/bash";
import dockerfile from "@shikijs/langs/dockerfile";
import json from "@shikijs/langs/json";
import python from "@shikijs/langs/python";
import yaml from "@shikijs/langs/yaml";
import { keelCodeTheme, KEEL_CODE_THEME_NAME } from "./code-theme";

/**
 * Server-side syntax highlighting for fenced code in lesson markdown.
 *
 * The hard constraint here is that `renderMarkdown` is synchronous, and it is
 * called from `parseUnitScript` inside `loadUnit`, which is synchronous all the
 * way up to the page. So this uses Shiki's sync core: `createHighlighterCoreSync`
 * with the JavaScript RegExp engine and grammar objects imported statically,
 * rather than the default builder, which awaits both the Oniguruma WASM and a
 * dynamic import per language.
 *
 * Five grammars are loaded, which is every language the content tree actually
 * fences: python (12 blocks), json (9), bash (6), dockerfile (1), plus yaml for
 * the check and rubric files a lesson may quote. `text` needs no grammar, so an
 * unlabelled fence and a log excerpt both cost nothing.
 */

let highlighter: HighlighterCore | null = null;

function getHighlighter(): HighlighterCore {
  highlighter ??= createHighlighterCoreSync({
    themes: [keelCodeTheme],
    langs: [python, json, bash, dockerfile, yaml],
    engine: createJavaScriptRegexEngine(),
  });
  return highlighter;
}

/**
 * `loadUnit` re-reads and re-parses every `learn.md` on every request, because
 * the unit page is `force-dynamic` and nothing in the loader caches. Tokenising
 * 11 blocks per request is the one part of that which is genuinely expensive, so
 * the rendered HTML is memoised on the module. The key includes the meta string
 * because `{3,7-9}` changes the output.
 */
const cache = new Map<string, string>();

const ALIASES: Record<string, string> = {
  py: "python",
  sh: "bash",
  shell: "bash",
  zsh: "bash",
  console: "bash",
  yml: "yaml",
  docker: "dockerfile",
  txt: "text",
  plaintext: "text",
  "": "text",
};

/** Languages this highlighter can render, after alias resolution. */
const SUPPORTED = new Set(["python", "json", "bash", "dockerfile", "yaml", "text"]);

export function resolveLang(lang: string): string {
  const lower = lang.toLowerCase();
  const resolved = ALIASES[lower] ?? lower;
  return SUPPORTED.has(resolved) ? resolved : "text";
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * The `<pre class="shiki">` for one block, tokenised and themed.
 *
 * Shiki puts `tabindex="0"` on the `<pre>` itself, which closes a real gap: the
 * code blocks on the unit page scroll horizontally today and a keyboard user
 * cannot reach them.
 *
 * A grammar the JavaScript engine cannot handle, or a language that slipped
 * past `resolveLang`, must not take the page down with it. On any throw this
 * returns the same escaped plain block the old renderer produced, so the reader
 * loses colour and nothing else.
 */
export function highlightCode(code: string, lang: string, meta = ""): string {
  const resolved = resolveLang(lang);
  const key = `${resolved}\0${meta}\0${code}`;
  const hit = cache.get(key);
  if (hit !== undefined) return hit;

  let html: string;
  try {
    html = getHighlighter().codeToHtml(code, {
      lang: resolved,
      theme: KEEL_CODE_THEME_NAME,
      meta: { __raw: meta },
      transformers: [transformerMetaHighlight(), transformerNotationHighlight()],
    });
  } catch (error) {
    console.warn(`[code-highlight] falling back to plain text for "${lang}":`, error);
    html = `<pre class="shiki shiki-plain" tabindex="0"><code>${escapeHtml(code)}</code></pre>`;
  }

  const hasRange = /\{[\d,\-\s]+\}/.test(meta);
  if (hasRange) {
    html = html.replace('<pre class="shiki', '<pre class="shiki has-line-numbers');
  }

  cache.set(key, html);
  return html;
}
