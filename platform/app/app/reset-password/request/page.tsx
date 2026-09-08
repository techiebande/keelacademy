import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/auth";
import { resetRequestAction } from "@/app/auth/actions";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Reset your password",
  robots: { index: false },
};

const ERRORS: Record<string, string> = {
  "invalid-email": "That does not look like an email address.",
};

type Props = { searchParams: Promise<{ error?: string; email?: string; sent?: string }> };

export default async function ResetRequestPage({ searchParams }: Props) {
  const { error, email, sent } = await searchParams;
  const user = await getSessionUser();
  if (user) {
    redirect("/me");
  }

  return (
    <div className="shell section">
      <div className="mx-auto max-w-[26rem]">
        <p className="eyebrow">Password reset</p>
        <h1 className="heading-xl mt-4">Reset your password</h1>

        {sent ? (
          <p className="mt-6 rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[14.5px] leading-relaxed text-phosphor-white">
            If that address has an account, a reset link is on its way. The
            link works once and expires in 30 minutes.
          </p>
        ) : (
          <>
            {error ? (
              <p
                role="alert"
                className="mt-6 rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[14.5px] leading-relaxed text-phosphor-white"
              >
                {ERRORS[error] ?? "Something went wrong. Try again."}
              </p>
            ) : null}
            <form action={resetRequestAction} className="mt-8">
              <label htmlFor="email" className="field-label">
                Email
              </label>
              <input
                id="email"
                name="email"
                type="email"
                required
                autoComplete="email"
                defaultValue={email ?? ""}
                placeholder="you@example.com"
                className="field-input"
              />
              <button type="submit" className="btn btn-accent mt-6 w-full">
                Send reset link
              </button>
            </form>
          </>
        )}

        <p className="mt-6 text-[14.5px] text-[color:var(--text-muted-on-dark)]">
          <Link
            href="/sign-in"
            className="text-fern-link underline underline-offset-4 hover:text-phosphor-white"
          >
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
