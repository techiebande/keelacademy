import type { AuthMode } from "@/lib/auth";

export function OfflineAuthNote({ mode }: { mode: AuthMode }) {
  if (mode !== "offline") return null;
  return (
    <div className="mt-9 rounded-lg border border-circuit-border bg-carbon-veil p-4">
      <p className="chip chip-outline">LOCAL MODE</p>
      <p className="mt-3 text-[14px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
        This is the local development sign-in. Your email is stored on this machine only, and
        no password is required.
      </p>
    </div>
  );
}
