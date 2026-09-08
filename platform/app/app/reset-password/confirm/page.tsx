import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { resetConfirmAction } from "@/app/auth/actions";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Choose a new password",
  robots: { index: false },
};

const ERRORS: Record<string, string> = {
  "weak-password": "Use at least 10 characters.",
  "invalid_or_expired_token": "That reset link was already used or has expired. Request a new one.",
  unreachable: "The sign-in service did not answer. Try again.",
};

type Props = { searchParams: Promise<{ token?: string; error?: string }> };

export default async function ResetConfirmPage({ searchParams }: Props) {
  const { token, error } = await searchParams;
  if (!token) {
    redirect("/reset-password/request");
  }

  return (
    <div className="shell section">
      <div className="mx-auto max-w-[26rem]">
        <p className="eyebrow">Password reset</p>
        <h1 className="heading-xl mt-4">Choose a new password</h1>

        {error ? (
          <p
            role="alert"
            className="mt-6 rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[14.5px] leading-relaxed text-phosphor-white"
          >
            {ERRORS[error] ?? "Something went wrong. Try again."}
          </p>
        ) : null}

        <form action={resetConfirmAction} className="mt-8">
          <input type="hidden" name="token" value={token} />
          <label htmlFor="password" className="field-label">
            New password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            required
            minLength={10}
            autoComplete="new-password"
            className="field-input"
          />
          <p className="mt-2 text-[13px] text-[color:var(--text-muted-on-dark)]">
            At least 10 characters. This signs you out everywhere else.
          </p>
          <button type="submit" className="btn btn-accent mt-6 w-full">
            Save new password
          </button>
        </form>

        <p className="mt-6 text-[14.5px] text-[color:var(--text-muted-on-dark)]">
          <Link
            href="/reset-password/request"
            className="text-fern-link underline underline-offset-4 hover:text-phosphor-white"
          >
            Request a fresh link
          </Link>
        </p>
      </div>
    </div>
  );
}
