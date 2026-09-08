import type { Metadata } from "next";
import Link from "next/link";
import { authMode, oauthProviders } from "@/lib/auth";
import { keelSignInAction, offlineSignInAction } from "@/app/auth/actions";
import { OfflineAuthNote } from "@/components/auth/offline-note";
import { SocialAuthButtons } from "@/components/auth/social-auth-buttons";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Sign in",
  robots: { index: false },
};

const ERRORS: Record<string, string> = {
  unknown: "No account uses that email address. Create one first.",
  "invalid-email": "That does not look like an email address.",
  mode: "This form only works in offline development mode.",
  "invalid_credentials": "That email and password do not match.",
  "email_linked_to_other_account": "That email belongs to a different sign-in method.",
  "too_many_attempts": "Too many attempts. Wait a few minutes and try again.",
  unreachable: "The sign-in service did not answer. Try again.",
  done: "Password updated. Sign in with your new password.",
};

type Props = {
  searchParams: Promise<{ error?: string; email?: string; next?: string; reset?: string }>;
};

export default async function SignInPage({ searchParams }: Props) {
  const { error, email, next, reset } = await searchParams;
  const mode = authMode();

  if (mode === "clerk") {
    const { SignIn } = await import("@clerk/nextjs");
    return (
      <div className="shell section flex justify-center">
        <SignIn />
      </div>
    );
  }

  const errorBody = reset === "done" ? ERRORS.done : error ? ERRORS[error] : null;
  const providers = oauthProviders();
  const action = mode === "keel" ? keelSignInAction : offlineSignInAction;

  return (
    <div className="shell section">
      <div className="mx-auto max-w-[26rem]">
        <p className="eyebrow">Welcome back</p>
        <h1 className="heading-xl mt-4">Sign in</h1>

        {errorBody ? (
          <p
            role="alert"
            className="mt-6 rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[14.5px] leading-relaxed text-phosphor-white"
          >
            {errorBody}
          </p>
        ) : null}

        <SocialAuthButtons providers={providers} next={next} />

        <form action={action} className="mt-6">
          <input type="hidden" name="next" value={next ?? "/me"} />
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
          {mode === "keel" ? (
            <>
              <label htmlFor="password" className="field-label mt-4">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                required
                minLength={10}
                autoComplete="current-password"
                className="field-input"
              />
            </>
          ) : null}
          <button type="submit" className="btn btn-accent mt-6 w-full">
            Sign in
          </button>
        </form>

        {mode === "keel" ? (
          <p className="mt-4 text-[14.5px] text-[color:var(--text-muted-on-dark)]">
            <Link
              href="/reset-password/request"
              className="text-fern-link underline underline-offset-4 hover:text-phosphor-white"
            >
              Forgot your password?
            </Link>
          </p>
        ) : null}

        <p className="mt-6 text-[14.5px] text-[color:var(--text-muted-on-dark)]">
          No account yet?{" "}
          <Link
            href={next ? `/sign-up?next=${encodeURIComponent(next)}` : "/sign-up"}
            className="text-fern-link underline underline-offset-4 hover:text-phosphor-white"
          >
            Create one
          </Link>
        </p>

        <OfflineAuthNote mode={mode} />
      </div>
    </div>
  );
}
