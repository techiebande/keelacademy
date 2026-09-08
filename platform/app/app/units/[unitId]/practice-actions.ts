"use server";

import { getSessionUser } from "@/lib/auth";
import { ensureStudent } from "@/lib/enroll";
import {
  evaluateExplainItBack,
  submitPracticeAttempt,
  submitRetrievalAttempt,
  type ExplainItBackResult,
  type PracticeAttemptResult,
  type PracticeResult,
  type RetrievalAttemptResult,
} from "@/lib/practice";

export async function runPracticeAttemptAction(
  unitId: string,
  files: Record<string, string>,
  answer?: string,
): Promise<PracticeResult<PracticeAttemptResult>> {
  const user = await getSessionUser();
  if (!user) {
    return {
      state: "rejected",
      status: 401,
      code: "not_signed_in",
      message: "Sign in required to run practice checks.",
    };
  }

  const studentRes = await ensureStudent(user);
  if (studentRes.state !== "ok") {
    return {
      state: "rejected",
      status: 500,
      code: "student_bridge_failed",
      message: "Unable to load student profile.",
    };
  }

  const studentId = studentRes.data;
  return submitPracticeAttempt({ studentId, unitId, files, answer });
}

export async function runRetrievalAttemptAction(
  unitId: string,
  seedIndex: number,
  seedPrompt: string,
  answer: string,
): Promise<PracticeResult<RetrievalAttemptResult>> {
  const user = await getSessionUser();
  if (!user) {
    return {
      state: "rejected",
      status: 401,
      code: "not_signed_in",
      message: "Sign in required to run retrieval drills.",
    };
  }

  const studentRes = await ensureStudent(user);
  if (studentRes.state !== "ok") {
    return {
      state: "rejected",
      status: 500,
      code: "student_bridge_failed",
      message: "Unable to load student profile.",
    };
  }

  const studentId = studentRes.data;
  return submitRetrievalAttempt({
    studentId,
    unitId,
    seedIndex,
    seedPrompt,
    answer,
  });
}

export async function runExplainItBackAction(
  unitId: string,
  explanation: string,
): Promise<PracticeResult<ExplainItBackResult>> {
  const user = await getSessionUser();
  if (!user) {
    return {
      state: "rejected",
      status: 401,
      code: "not_signed_in",
      message: "Sign in required to submit explanation.",
    };
  }

  const studentRes = await ensureStudent(user);
  if (studentRes.state !== "ok") {
    return {
      state: "rejected",
      status: 500,
      code: "student_bridge_failed",
      message: "Unable to load student profile.",
    };
  }

  const studentId = studentRes.data;
  return evaluateExplainItBack({
    studentId,
    unitId,
    explanation,
  });
}
