import Link from "next/link";
import { getSessionUser } from "@/lib/auth";
import { ThemeToggle } from "@/components/theme-toggle";

/** Brand mark: the lime status glyph on a ground tile. */
function LogoMark() {
  return (
    <span
      aria-hidden
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-circuit-border bg-ground-iron"
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path
          d="M1.5 8.5h3l2-5 3 9 2-4h3"
          stroke="var(--color-lime-pulse)"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

type NavLink = { href: string; label: string };

// One list, rendered twice: the row above lg and the disclosure below it. Adding
// a link here adds it to both.
const CURRICULUM: NavLink = { href: "/curriculum", label: "Curriculum" };
const STUDENT_LINKS: NavLink[] = [
  { href: "/map", label: "Progress map" },
  { href: "/community", label: "Your pod" },
  { href: "/gallery", label: "Gallery" },
  { href: "/simulations", label: "Practice" },
];
const TAIL_LINKS: NavLink[] = [
  { href: "/pricing", label: "Pricing" },
  { href: "/faq", label: "FAQ" },
];

export async function SiteHeader() {
  const user = await getSessionUser();
  const links: NavLink[] = user
    ? [CURRICULUM, ...STUDENT_LINKS, ...TAIL_LINKS]
    : [CURRICULUM, ...TAIL_LINKS];

  return (
    <header className="sticky top-0 z-40 bg-carbon-veil/90 backdrop-blur-[10px]">
      <div className="shell flex h-16 items-center justify-between gap-4 border-b border-phosphor-blue-black">
        <Link href="/" className="flex items-center gap-3" aria-label="Keel Academy home">
          <LogoMark />
          <span className="hidden font-goga text-[20px] font-medium tracking-tight text-phosphor-white sm:inline">
            Keel Academy
          </span>
        </Link>

        <nav aria-label="Main navigation" className="hidden lg:block">
          <ul className="flex items-center gap-7">
            {links.map((link) => (
              <li key={link.href}>
                <Link href={link.href} className="nav-link">
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex items-center gap-2">
          <span className="hidden sm:inline-flex">
            <ThemeToggle />
          </span>
          {user ? (
            <>
              <Link href="/me" className="btn btn-quiet max-w-[140px] truncate lg:max-w-[180px]">
                {user.name ?? user.email}
              </Link>
              <Link href="/sign-out" className="btn btn-ghost btn-sm hidden sm:inline-flex">
                Sign out
              </Link>
            </>
          ) : (
            <>
              <Link href="/sign-in" className="btn btn-quiet">
                Sign in
              </Link>
              <Link href="/sign-up" className="btn btn-accent btn-sm hidden sm:inline-flex">
                Start building
              </Link>
            </>
          )}
          <details className="lg:hidden">
            <summary className="btn btn-quiet list-none [&::-webkit-details-marker]:hidden">
              Menu
            </summary>
            <div className="absolute left-0 right-0 top-16 border-b border-circuit-border bg-carbon-veil">
              <nav aria-label="Main navigation" className="shell py-4">
                <ul className="flex flex-col">
                  {links.map((link) => (
                    <li key={link.href}>
                      <Link
                        href={link.href}
                        className="block border-t border-[color:var(--line-on-dark-strong)] py-3 text-[15.5px] text-[color:var(--text-muted-on-dark)] first:border-t-0 hover:text-phosphor-white"
                      >
                        {link.label}
                      </Link>
                    </li>
                  ))}
                  <li className="pt-4 sm:hidden">
                    <Link
                      href={user ? "/sign-out" : "/sign-up"}
                      className={user ? "btn btn-ghost btn-sm" : "btn btn-accent btn-sm"}
                    >
                      {user ? "Sign out" : "Start building"}
                    </Link>
                  </li>
                  <li className="pt-3 sm:hidden">
                    <ThemeToggle />
                  </li>
                </ul>
              </nav>
            </div>
          </details>
        </div>
      </div>
    </header>
  );
}
