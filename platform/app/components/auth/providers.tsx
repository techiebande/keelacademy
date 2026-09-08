"use client";

import { ClerkProvider } from "@clerk/nextjs";
import type { ReactNode } from "react";

/**
 * Clerk wiring for production. NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is inlined
 * at BUILD time (that is what NEXT_PUBLIC_ means), so:
 *
 * - credential-free build -> the key is undefined -> this wrapper renders
 *   nothing and Clerk never initializes (the offline auth fake is active);
 * - founder build with the key set -> every page renders inside
 *   ClerkProvider and the sign-in/up pages render Clerk's hosted UI.
 *
 * The publishable key is public by design (it only identifies the instance).
 * The matching secret, CLERK_SECRET_KEY, is server-env only and never
 * appears in any client bundle.
 */
const PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

export function AuthProviders({ children }: { children: ReactNode }) {
  if (!PUBLISHABLE_KEY) return <>{children}</>;
  return <ClerkProvider>{children}</ClerkProvider>;
}
