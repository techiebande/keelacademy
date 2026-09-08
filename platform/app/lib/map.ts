import {
  loadCurriculumMap,
  listUnits,
  isUnitAuthored,
  type MapPhase,
  type MapModule,
  type CurriculumMap,
} from "@/lib/content";
import {
  loadGateRules,
  type GateRule,
  type StudentGates,
  type PassedGate,
} from "@/lib/gates";
import type { StudentProfile, OwnSubmission, Rebate, Enrollment } from "@/lib/enroll";

export type ResolvedUnitStatus =
  | "not_authored"
  | "not_authored_locked"
  | "not_authored_unlocked"
  | "locked"
  | "available"
  | "enrolled"
  | "queued"
  | "grading"
  | "passed"
  | "failed"
  | "error";

export type ResolvedModuleCard = {
  module: MapModule;
  phaseNum: number;
  phaseId: string;
  isAuthored: boolean;
  isEnrolled: boolean;
  status: ResolvedUnitStatus;
  lockReason: string | null;
  latestSubmission: OwnSubmission | null;
  allSubmissions: OwnSubmission[];
};

export type ResolvedPhase = {
  phase: MapPhase;
  isTrackUnlocked: boolean;
  lockReason: string | null;
  gateRule: GateRule | null;
  gateCleared: PassedGate | null;
  rebate: Rebate | null;
  modules: ResolvedModuleCard[];
  stats: {
    total: number;
    authored: number;
    passed: number;
    inFlight: number;
    enrolled: number;
  };
};

export type ProgressMapState = {
  skeleton: CurriculumMap;
  phases: ResolvedPhase[];
  stats: {
    totalPhases: number;
    unlockedPhases: number;
    totalModules: number;
    authoredUnits: number;
    enrolledUnits: number;
    passedUnits: number;
    inFlightSubmissions: number;
    clearedGates: number;
    totalGates: number;
    earnedRebatesCents: number;
    tokensUsed: number;
    tokensCap: number;
  };
};

export function buildProgressMap(
  profile: StudentProfile | null,
  submissions: OwnSubmission[],
  gates: StudentGates | null,
): ProgressMapState {
  const skeleton = loadCurriculumMap();
  const gateRules = loadGateRules();
  const authoredUnitsList = listUnits();
  const authoredSet = new Set(authoredUnitsList.map((u) => u.id));

  const enrolledUnitsMap = new Map<string, Enrollment>(
    (profile?.enrollments ?? []).map((e) => [e.unit_id, e]),
  );

  const rebatesByGate = new Map<string, Rebate>(
    (profile?.rebates ?? []).map((r) => [r.gate_id, r]),
  );

  const passedGatesMap = new Map<string, PassedGate>(
    (gates?.gates_passed ?? []).map((g) => [g.gate_id, g]),
  );

  const unlockedUnitsSet = new Set<string>(
    (gates?.unlocked_units ?? []).map((u) => u.unit_id),
  );

  // Submissions grouped by unit_id
  const subsByUnit = new Map<string, OwnSubmission[]>();
  for (const s of submissions) {
    const list = subsByUnit.get(s.unit_id) ?? [];
    list.push(s);
    subsByUnit.set(s.unit_id, list);
  }

  // Gates indexed by gate_id
  const gateByGateId = new Map<string, GateRule>(gateRules.map((g) => [g.gate_id, g]));

  const phase5GateCleared = passedGatesMap.has("phase-5-integration");

  const resolvedPhases: ResolvedPhase[] = skeleton.phases.map((phase) => {
    // Determine track unlock state
    let isTrackUnlocked = true;
    let phaseLockReason: string | null = null;

    if (phase.phase >= 6 && phase.phase <= 10) {
      if (!phase5GateCleared) {
        isTrackUnlocked = false;
        phaseLockReason =
          "Locked behind the Phase 5 integration gate. A passing verdict on unit 5.1 unlocks Phase 6 through Phase 10.";
      }
    } else if (phase.phase === 12) {
      if (!phase5GateCleared) {
        isTrackUnlocked = false;
        phaseLockReason =
          "Locked behind the Phase 5 integration gate. Complete the technical track to unlock the capstone.";
      }
    }

    const gateRule = phase.gate_id ? gateByGateId.get(phase.gate_id) ?? null : null;
    const gateCleared = phase.gate_id ? passedGatesMap.get(phase.gate_id) ?? null : null;
    const rebate = phase.gate_id ? rebatesByGate.get(phase.gate_id) ?? null : null;

    const moduleCards: ResolvedModuleCard[] = phase.modules.map((m) => {
      const isAuthored = authoredSet.has(m.id) || isUnitAuthored(m.id);
      const isEnrolled = enrolledUnitsMap.has(m.id);
      const unitSubs = subsByUnit.get(m.id) ?? [];
      const latestSub = unitSubs[0] ?? null;

      // Check if this specific unit is explicitly locked by a gate rule
      let unitLocked = false;
      let unitLockReason: string | null = null;

      // Check if unit is in gate rule unlocks and gate is not passed
      for (const rule of gateRules) {
        if (rule.unlocks.includes(m.id)) {
          const ruleCleared = passedGatesMap.has(rule.gate_id) || unlockedUnitsSet.has(m.id);
          if (!ruleCleared) {
            unitLocked = true;
            unitLockReason = `Locked behind ${rule.title}. ${rule.summary}`;
            break;
          }
        }
      }

      // If whole phase is locked and not overridden by unit unlock
      if (!isTrackUnlocked && !unlockedUnitsSet.has(m.id)) {
        unitLocked = true;
        if (!unitLockReason) {
          unitLockReason = phaseLockReason;
        }
      }

      let status: ResolvedUnitStatus = "not_authored";

      if (latestSub) {
        if (latestSub.overall === "pass") {
          status = "passed";
        } else if (latestSub.overall === "fail") {
          status = "failed";
        } else if (latestSub.status === "grading") {
          status = "grading";
        } else if (latestSub.status === "queued") {
          status = "queued";
        } else if (latestSub.status === "error") {
          status = "error";
        } else {
          status = "grading";
        }
      } else if (!isAuthored) {
        if (unitLocked) {
          status = "not_authored_locked";
        } else if (unlockedUnitsSet.has(m.id) || (phase.phase >= 6 && phase5GateCleared)) {
          status = "not_authored_unlocked";
        } else {
          status = "not_authored";
        }
      } else {
        // Unit is authored and has no submissions
        if (unitLocked) {
          status = "locked";
        } else if (isEnrolled) {
          status = "enrolled";
        } else {
          status = "available";
        }
      }

      return {
        module: m,
        phaseNum: phase.phase,
        phaseId: phase.id,
        isAuthored,
        isEnrolled,
        status,
        lockReason: unitLockReason,
        latestSubmission: latestSub,
        allSubmissions: unitSubs,
      };
    });

    const stats = {
      total: moduleCards.length,
      authored: moduleCards.filter((m) => m.isAuthored).length,
      passed: moduleCards.filter((m) => m.status === "passed").length,
      inFlight: moduleCards.filter((m) => m.status === "queued" || m.status === "grading").length,
      enrolled: moduleCards.filter((m) => m.isEnrolled).length,
    };

    return {
      phase,
      isTrackUnlocked,
      lockReason: phaseLockReason,
      gateRule,
      gateCleared,
      rebate,
      modules: moduleCards,
      stats,
    };
  });

  const totalPhases = resolvedPhases.length;
  const unlockedPhases = resolvedPhases.filter((p) => p.isTrackUnlocked).length;
  let totalModules = 0;
  let authoredUnits = 0;
  let enrolledUnits = 0;
  let passedUnits = 0;
  let inFlightSubmissions = 0;

  for (const p of resolvedPhases) {
    totalModules += p.stats.total;
    authoredUnits += p.stats.authored;
    enrolledUnits += p.stats.enrolled;
    passedUnits += p.stats.passed;
    inFlightSubmissions += p.stats.inFlight;
  }

  const clearedGates = passedGatesMap.size;
  const totalGates = gateRules.length;

  let earnedRebatesCents = 0;
  for (const r of profile?.rebates ?? []) {
    if (r.status === "earned" || r.status === "paid") {
      earnedRebatesCents += r.amount_cents;
    }
  }

  const tokensUsed = profile?.budget?.tokens_used ?? 0;
  const tokensCap = profile?.budget?.tokens_cap ?? 0;

  return {
    skeleton,
    phases: resolvedPhases,
    stats: {
      totalPhases,
      unlockedPhases,
      totalModules,
      authoredUnits,
      enrolledUnits,
      passedUnits,
      inFlightSubmissions,
      clearedGates,
      totalGates,
      earnedRebatesCents,
      tokensUsed,
      tokensCap,
    },
  };
}
