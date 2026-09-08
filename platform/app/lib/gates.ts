/**
 * Gate rules (content-as-data) and per-student gate state (S2.7).
 *
 * Rules live in content/gates/<gate-id>.yaml and are validated by
 * content/tools/validate-gates.py. The gate engine
 * (platform/grading/gates/engine.py) is the only writer of gate state, so
 * this module renders exactly two honest sources: the rule files for what a
 * gate is and what it unlocks, and the read-only reader endpoint for what
 * this student has cleared.
 *
 * Server-side only: rule loading reads the filesystem and the reader fetch
 * carries no credential but stays off client bundles (import from server
 * components only, same discipline as lib/enroll.ts and lib/grading.ts).
 */

import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { parse as parseYaml } from "yaml";
import { findContentRoot } from "@/lib/content";
import { readerBaseUrl } from "@/lib/grading";

export type GateRule = {
  gate_id: string;
  title: string;
  unit_id: string;
  unlocks: string[];
  rebate: boolean;
  summary: string;
};

export type UnlockedUnit = { unit_id: string; gate_id: string; unlocked_at: string };

export type PassedGate = { gate_id: string; unit_id: string; passed_at: string };

export type StudentGates = {
  student_id: number;
  unlocked_units: UnlockedUnit[];
  gates_passed: PassedGate[];
};

export type GatesLookup =
  | { state: "ok"; data: StudentGates }
  | { state: "unreachable"; detail: string };

/** All gate rules, sorted by gate id. Missing directory renders no gates. */
export function loadGateRules(): GateRule[] {
  const dir = path.join(/* turbopackIgnore: true */ findContentRoot(), "gates");
  if (!existsSync(dir)) return [];
  const rules: GateRule[] = [];
  for (const entry of readdirSync(dir)) {
    if (!entry.endsWith(".yaml")) continue;
    rules.push(parseYaml(readFileSync(path.join(/* turbopackIgnore: true */ dir, entry), "utf8")) as GateRule);
  }
  return rules.sort((a, b) => a.gate_id.localeCompare(b.gate_id));
}

export async function fetchStudentGates(studentId: number): Promise<GatesLookup> {
  try {
    const res = await fetch(`${readerBaseUrl()}/students/${studentId}/gates`, {
      cache: "no-store",
    });
    if (!res.ok) {
      return { state: "unreachable", detail: `reader answered HTTP ${res.status}` };
    }
    return { state: "ok", data: (await res.json()) as StudentGates };
  } catch (err) {
    return {
      state: "unreachable",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}
