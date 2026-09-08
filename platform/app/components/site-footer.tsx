import Link from "next/link";
import { getSessionUser } from "@/lib/auth";

const PROGRAM_LINKS = [
  { href: "/curriculum", label: "Curriculum" },
  { href: "/pricing", label: "Pricing" },
  { href: "/refunds", label: "Refunds and rebates" },
  { href: "/faq", label: "FAQ" },
];

// Pages that work without an account.
const OPEN_LINKS = [
  { href: "/submit", label: "How to submit" },
  { href: "/gallery", label: "What students built" },
];

// Pages that send you to sign-in first, so they are only offered once you are in.
const SIGNED_IN_LINKS = [
  { href: "/map", label: "Progress map" },
  { href: "/diagnostic", label: "Placement check" },
  { href: "/community", label: "Your pod" },
  { href: "/simulations", label: "Practice conversations" },
];

export async function SiteFooter() {
  const user = await getSessionUser();
  const learnerLinks = user ? [...SIGNED_IN_LINKS, ...OPEN_LINKS] : OPEN_LINKS;

  return (
    <footer className="mt-24 border-t border-[color:var(--line-on-dark)]">
      <div className="shell grid gap-12 py-16 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <p className="font-goga text-[17px] font-medium text-phosphor-white">Keel Academy</p>
          <p className="mt-3 max-w-[36ch] text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            Learn AI engineering by building one production system end to end,
            graded for real, by automated checks and rubric review, on every
            submission.
          </p>
          <p className="mt-4 text-[14px] text-[color:var(--text-muted-on-dark)]">
            Questions? Contact us at{" "}
            <a
              href="mailto:support@keelacademy.com"
              className="text-phosphor-white underline underline-offset-4 hover:text-lime-pulse"
            >
              support@keelacademy.com
            </a>
          </p>
        </div>

        <nav aria-label="Program">
          <p className="eyebrow mb-4 !text-[color:var(--text-faint-on-dark)]">Program</p>
          <ul className="space-y-2.5">
            {PROGRAM_LINKS.map((link) => (
              <li key={link.href}>
                <Link href={link.href} className="nav-link !text-[15px]">
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <nav aria-label={user ? "For students" : "Before you enroll"}>
          <p className="eyebrow mb-4 !text-[color:var(--text-faint-on-dark)]">
            {user ? "For students" : "Before you enroll"}
          </p>
          <ul className="space-y-2.5">
            {learnerLinks.map((link) => (
              <li key={link.href}>
                <Link href={link.href} className="nav-link !text-[15px]">
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>

      <div className="border-t border-[color:var(--line-on-dark)]">
        <div className="shell flex flex-wrap items-center justify-between gap-4 py-6 text-[13.5px] text-[color:var(--text-faint-on-dark)]">
          <div className="flex flex-wrap items-center gap-5">
            <p>© {new Date().getFullYear()} Keel Academy</p>
            <Link href="/terms" className="hover:text-phosphor-white">
              Terms
            </Link>
            <Link href="/privacy" className="hover:text-phosphor-white">
              Privacy
            </Link>
            <Link href="/refunds" className="hover:text-phosphor-white">
              Refunds
            </Link>
            <a
              href="mailto:support@keelacademy.com"
              className="hover:text-phosphor-white"
            >
              Contact
            </a>
          </div>
          <p>Every unit page shows what gets graded and how, before you pay.</p>
        </div>
      </div>
    </footer>
  );
}
