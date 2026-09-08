/**
 * Server-side client for the Business Simulation Engine (S4.5)
 * (platform/grading/simulation/engine.py via practice/server.py).
 *
 * Exposes:
 * - Simulation session initiation (/simulation/start)
 * - Turn-by-turn dialogue execution (/simulation/turn)
 * - Final transcript grading & verdict retrieval (/simulation/conclude)
 * - Session transcript inspection (/simulation/[id])
 * - Student simulation history (/students/[id]/simulations)
 *
 * Security: Uses KEEL_PRACTICE_URL and KEEL_ENROLL_SECRET from server environment only.
 */

export type SimulationTurn = {
  role: "student" | "persona";
  content: string;
  created_at: string;
};

export type RubricCriterionResult = {
  id: string;
  weight: number;
  score_pct: number;
  passed: boolean;
  feedback: string;
  evidence: string;
};

export type SimulationVerdict = {
  score_pct: number;
  passed: boolean;
  passing_threshold_pct?: number;
  summary: string;
  criteria: RubricCriterionResult[];
};

export type SimulationSession = {
  id: number;
  student_id: number;
  persona_id: string;
  status: "in_progress" | "concluded" | "graded" | "abandoned";
  turns: SimulationTurn[];
  score_pct: number | null;
  passed: boolean | null;
  verdict: SimulationVerdict | null;
  created_at: string;
  completed_at: string | null;
};

export type SimulationSummary = {
  id: number;
  student_id: number;
  persona_id: string;
  status: string;
  score_pct: number | null;
  passed: boolean | null;
  verdict: SimulationVerdict | null;
  created_at: string;
  completed_at: string | null;
  turn_count: number;
};

export type ClientResult<T> =
  | { state: "ok"; data: T }
  | { state: "unreachable"; detail: string }
  | { state: "rejected"; status: number; code: string; message?: string };

function practiceServerUrl(): string {
  const envUrl = process.env.KEEL_PRACTICE_URL;
  if (envUrl && envUrl.trim().length > 0) {
    return envUrl.trim().replace(/\/+$/, "");
  }
  return "http://127.0.0.1:8792";
}

function practiceSecret(): string {
  return process.env.KEEL_ENROLL_SECRET || "";
}

export async function startSimulation(input: {
  studentId: number;
  personaId?: string;
}): Promise<ClientResult<SimulationSession>> {
  const url = `${practiceServerUrl()}/simulation/start`;
  const token = practiceSecret();

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Keel-App-Token": token,
      },
      body: JSON.stringify({
        student_id: input.studentId,
        persona_id: input.personaId || "discovery-call",
      }),
      cache: "no-store",
    });

    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      return {
        state: "rejected",
        status: res.status,
        code: body.error || "simulation_start_rejected",
        message: body.message || body.detail,
      };
    }

    return {
      state: "ok",
      data: {
        id: body.id,
        student_id: body.student_id,
        persona_id: body.persona_id,
        status: body.status,
        turns: body.turns || [],
        score_pct: null,
        passed: null,
        verdict: null,
        created_at: body.created_at,
        completed_at: null,
      },
    };
  } catch (err: unknown) {
    return {
      state: "unreachable",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

export async function sendSimulationTurn(input: {
  simulationId: number;
  studentId: number;
  message: string;
}): Promise<ClientResult<{ persona_reply: string; turns: SimulationTurn[] }>> {
  const url = `${practiceServerUrl()}/simulation/turn`;
  const token = practiceSecret();

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Keel-App-Token": token,
      },
      body: JSON.stringify({
        simulation_id: input.simulationId,
        student_id: input.studentId,
        message: input.message,
      }),
      cache: "no-store",
    });

    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      return {
        state: "rejected",
        status: res.status,
        code: body.error || "simulation_turn_rejected",
        message: body.message || body.detail,
      };
    }

    return {
      state: "ok",
      data: {
        persona_reply: body.persona_reply,
        turns: body.turns || [],
      },
    };
  } catch (err: unknown) {
    return {
      state: "unreachable",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

export async function concludeSimulation(input: {
  simulationId: number;
  studentId: number;
}): Promise<ClientResult<SimulationSession>> {
  const url = `${practiceServerUrl()}/simulation/conclude`;
  const token = practiceSecret();

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Keel-App-Token": token,
      },
      body: JSON.stringify({
        simulation_id: input.simulationId,
        student_id: input.studentId,
      }),
      cache: "no-store",
    });

    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      return {
        state: "rejected",
        status: res.status,
        code: body.error || "simulation_conclude_rejected",
        message: body.message || body.detail,
      };
    }

    return {
      state: "ok",
      data: {
        id: body.id,
        student_id: body.student_id,
        persona_id: body.persona_id,
        status: body.status,
        turns: body.turns || [],
        score_pct: body.score_pct,
        passed: body.passed,
        verdict: body.verdict,
        created_at: body.created_at,
        completed_at: body.completed_at,
      },
    };
  } catch (err: unknown) {
    return {
      state: "unreachable",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

export async function getSimulation(
  simulationId: number,
  studentId?: number,
): Promise<ClientResult<SimulationSession>> {
  const query = studentId ? `?student_id=${studentId}` : "";
  const url = `${practiceServerUrl()}/simulation/${simulationId}${query}`;
  const token = practiceSecret();

  try {
    const res = await fetch(url, {
      method: "GET",
      headers: {
        "X-Keel-App-Token": token,
      },
      cache: "no-store",
    });

    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      return {
        state: "rejected",
        status: res.status,
        code: body.error || "get_simulation_rejected",
        message: body.message || body.detail,
      };
    }

    return {
      state: "ok",
      data: body,
    };
  } catch (err: unknown) {
    return {
      state: "unreachable",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

export async function listStudentSimulations(
  studentId: number,
): Promise<ClientResult<SimulationSummary[]>> {
  const url = `${practiceServerUrl()}/students/${studentId}/simulations`;
  const token = practiceSecret();

  try {
    const res = await fetch(url, {
      method: "GET",
      headers: {
        "X-Keel-App-Token": token,
      },
      cache: "no-store",
    });

    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      return {
        state: "rejected",
        status: res.status,
        code: body.error || "list_simulations_rejected",
        message: body.message || body.detail,
      };
    }

    return {
      state: "ok",
      data: body.simulations || [],
    };
  } catch (err: unknown) {
    return {
      state: "unreachable",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

export type PersonaDefenseSummary = {
  passed: boolean;
  latest_simulation_id: number | null;
  score_pct: number | null;
  completed_at: string | null;
};


export type StudentDefenses = {
  student_id: number;
  technical_stakeholder: PersonaDefenseSummary;
  business_owner: PersonaDefenseSummary;
  defense_cleared: boolean;
};

export async function fetchStudentDefenses(
  studentId: number,
): Promise<ClientResult<StudentDefenses>> {
  const url = `${practiceServerUrl()}/students/${studentId}/simulations/defenses`;
  const token = practiceSecret();

  try {
    const res = await fetch(url, {
      method: "GET",
      headers: {
        "X-Keel-App-Token": token,
      },
      cache: "no-store",
    });

    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      return {
        state: "rejected",
        status: res.status,
        code: body.error || "fetch_defenses_rejected",
        message: body.message || body.detail,
      };
    }

    return {
      state: "ok",
      data: body,
    };
  } catch (err: unknown) {
    return {
      state: "unreachable",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

