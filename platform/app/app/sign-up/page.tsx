import type { Metadata } from "next";
import Link from "next/link";
import { authMode, oauthProviders } from "@/lib/auth";
import { keelSignUpAction, offlineSignUpAction } from "@/app/auth/actions";
import { OfflineAuthNote } from "@/components/auth/offline-note";
import { SocialAuthButtons } from "@/components/auth/social-auth-buttons";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Create an account",
  robots: { index: false },
};

const ERRORS: Record<string, string> = {
  exists: "An account already uses that email. Sign in instead.",
  "invalid-email": "That does not look like an email address.",
  invalid: "That name or email is longer than we can store.",
  mode: "This form only works in offline development mode.",
  "weak-password": "Use at least 10 characters for your password.",
  "email_linked_to_other_account": "That email belongs to a different sign-in method.",
  unreachable: "The sign-in service did not answer. Try again.",
};

type Props = {
  searchParams: Promise<{ error?: string; email?: string; next?: string }>;
};

export default async function SignUpPage({ searchParams }: Props) {
  const { error, email, next } = await searchParams;
  const mode = authMode();

  if (mode === "clerk") {
    const { SignUp } = await import("@clerk/nextjs");
    return (
      <div className="shell section flex justify-center">
        <SignUp />
      </div>
    );
  }

  const errorBody = error ? ERRORS[error] : null;
  const providers = oauthProviders();

  return (
    <div className="shell section">
      <div className="mx-auto max-w-[26rem]">
        <p className="eyebrow">Start here</p>
        <h1 className="heading-xl mt-4">Create an account</h1>
        <p className="mt-4 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          An account is free. You pay per unit, when you decide to start one.
        </p>

        {errorBody ? (
          <p
            role="alert"
            className="mt-6 rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[14.5px] leading-relaxed text-phosphor-white"
          >
            {errorBody}
          </p>
        ) : null}

        <SocialAuthButtons providers={providers} next={next} />

        <form action={mode === "keel" ? keelSignUpAction : offlineSignUpAction} className="mt-6 space-y-5">
          <input type="hidden" name="next" value={next ?? "/me"} />
          <div>
            <label htmlFor="name" className="field-label">
              Name
            </label>
            <input
              id="name"
              name="name"
              type="text"
              autoComplete="name"
              maxLength={100}
              placeholder="Ada Lovelace"
              className="field-input"
            />
          </div>
          <div>
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
          </div>
          {mode === "keel" ? (
            <div>
              <label htmlFor="password" className="field-label">
                Password
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
                At least 10 characters.
              </p>
            </div>
          ) : null}
          <button type="submit" className="btn btn-accent w-full">
            Create account
          </button>
        </form>

        <p className="mt-6 text-[14.5px] text-[color:var(--text-muted-on-dark)]">
          Already have one?{" "}
          <Link
            href={next ? `/sign-in?next=${encodeURIComponent(next)}` : "/sign-in"}
            className="text-fern-link underline underline-offset-4 hover:text-phosphor-white"
          >
            Sign in
          </Link>
        </p>

        <OfflineAuthNote mode={mode} />
      </div>
    </div>
  );
}
