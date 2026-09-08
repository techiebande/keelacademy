import type { Metadata } from "next";
import Link from "next/link";
import { authMode, getSessionUser } from "@/lib/auth";
import { signOutAction } from "@/app/auth/actions";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Sign out",
  robots: { index: false },
};

export default async function SignOutPage() {
  const mode = authMode();
  const user = await getSessionUser();

  if (mode === "clerk") {
    const { SignOutButton } = await import("@clerk/nextjs");
    return (
      <div className="shell section flex justify-center">
        <SignOutButton />
      </div>
    );
  }

  return (
    <div className="shell section">
      <div className="card-dark mx-auto max-w-[30rem]">
        <h1 className="heading-lg">Sign out</h1>
        <p className="mt-4 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          {user
            ? `Signed in as ${user.name ?? user.email}. Your progress stays on your account.`
            : "You are not signed in right now."}
        </p>
        {user ? (
          <form action={signOutAction} className="mt-7">
            <button type="submit" className="btn btn-primary btn-sm">
              Sign out
            </button>
          </form>
        ) : (
          <Link href="/sign-in" className="btn btn-primary btn-sm mt-7">
            Sign in
          </Link>
        )}
        <p className="mt-6">
          <Link
            href="/me"
            className="text-[14.5px] text-fern-link underline underline-offset-4 hover:text-phosphor-white"
          >
            Back to dashboard
          </Link>
        </p>
      </div>
    </div>
  );
}
