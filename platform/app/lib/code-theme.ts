import type { ThemeRegistrationRaw } from "shiki/core";

/**
 * The code theme, written in Keel's own palette rather than borrowed from a
 * bundled one.
 *
 * Two reasons it is ours. First, Shiki writes `background-color` and `color`
 * inline on the `<pre>` it emits, so a borrowed theme would put a foreign
 * near-black behind every code block and then have to be fought in CSS. Here
 * `bg` and `fg` are `--color-ground-iron` and `--color-moss-80`, so the frame
 * lands on the surface ladder by itself. Second, the accent stays rationed:
 * `--color-lime-pulse` is deliberately absent, because on this page lime means
 * a primary action, an active rail entry, or a live status, and a keyword is
 * none of those.
 *
 * Measured on ground-iron (#0f1211), which is what `bg` sets:
 *
 *   foreground, punctuation   #d5dad2  moss-80        13.26:1
 *   keyword, key, self        #8fd4ff                 11.69:1
 *   string                    #a9d79b  fern-link      11.55:1
 *   number, boolean, None     #e7c68a                 11.52:1
 *   class, type, exception    #7fd6a8                 10.84:1
 *   function, command         #c9b6ff                 10.42:1
 *   diagnostic                #ff9b8a                  9.25:1
 *   operator, variable        #b0b8ac  moss-70         9.24:1
 *   comment                   #7f8b7c                  5.28:1
 *
 * The floor is the comment at 5.28:1, which clears AA for body text with room
 * to spare; everything a reader has to parse closely is above 9:1. The scope
 * lists below are not guesses: they were read off the installed grammars for
 * python, bash, json, yaml and dockerfile, which are the only five the content
 * tree uses.
 */

const FOREGROUND = "#d5dad2";
const KEYWORD = "#8fd4ff";
const STRING = "#a9d79b";
const NUMBER = "#e7c68a";
const TYPE = "#7fd6a8";
const FUNCTION = "#c9b6ff";
const DIAGNOSTIC = "#ff9b8a";
const OPERATOR = "#b0b8ac";
const COMMENT = "#7f8b7c";

export const KEEL_CODE_THEME_NAME = "keel";

export const keelCodeTheme: ThemeRegistrationRaw = {
  name: KEEL_CODE_THEME_NAME,
  type: "dark",
  bg: "#0f1211",
  fg: FOREGROUND,
  settings: [
    {
      scope: ["comment", "punctuation.definition.comment", "meta.shebang"],
      settings: { foreground: COMMENT },
    },
    {
      scope: [
        "keyword",
        "keyword.control",
        "keyword.control.import",
        "keyword.control.flow",
        "keyword.operator.logical",
        "keyword.other",
        "storage",
        "storage.type.class",
        "storage.type.function",
        "storage.modifier",
        "variable.language",
        "variable.parameter.function.language",
        "entity.name.tag.yaml",
        "support.type.property-name.json",
      ],
      settings: { foreground: KEYWORD },
    },
    {
      scope: [
        "string",
        "string.quoted",
        "string.unquoted",
        "string.interpolated",
        "string.template",
        "storage.type.string",
        "punctuation.definition.string",
      ],
      settings: { foreground: STRING },
    },
    {
      scope: [
        "constant.numeric",
        "constant.language",
        "constant.character",
        "constant.other.option",
        "constant.character.format.placeholder",
      ],
      settings: { foreground: NUMBER },
    },
    {
      scope: [
        "entity.name.type",
        "entity.name.class",
        "entity.other.inherited-class",
        "support.type",
        "support.class",
        "support.type.exception",
      ],
      settings: { foreground: TYPE },
    },
    {
      scope: [
        "entity.name.function",
        "meta.function-call.generic",
        "support.function",
        "support.function.builtin",
        "entity.name.command",
        "entity.name.function.call",
      ],
      settings: { foreground: FUNCTION },
    },
    {
      scope: [
        "keyword.operator",
        "punctuation",
        "meta.brace",
        "variable",
        "variable.other",
        "variable.parameter",
      ],
      settings: { foreground: OPERATOR },
    },
    {
      scope: ["invalid", "invalid.illegal", "message.error"],
      settings: { foreground: DIAGNOSTIC },
    },
  ],
};
