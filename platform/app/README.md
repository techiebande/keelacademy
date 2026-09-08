# Keel Academy learner app

## UI/UX & Design System: DECIDED 2026-08-31

The learner app uses the dark engineering-console design language documented in `platform/app/AGENTS.md` and the 2026-08-31 `build-state.md` decisions log:

- **Visuals**: Dark engineering-console palette: obsidian canvas (`#000` void, `#0f1211` ground, `#151918` carbon). Depth is achieved via 1px circuit borders (`--color-circuit-border`) and luminance stepping, never drop shadows (aside from the sticky header). Single rationed green accent (`--color-lime-pulse`, `#7fee64` in dark mode, `#166534` high-contrast forest green in light mode) reserved for primary CTAs and active states.
- **Typography**: Space Grotesk / Goga for display headings, Inter for UI text, and Fira Mono for code and data. Measure adheres to `--lesson-measure: 35em` for long-form lesson prose.
- **Components & Layout**: Tailwind CSS v4 `@theme` tokens and semantic component utility classes in `app/globals.css` (`.btn`, `.card-dark`, `.chip`, `.data-table`, `.field-input`, `.lesson-prose`, `.shell`, `.section`).
- **Copy Direction**: Precise engineer-to-engineer voice, plain declarative sentences, active voice. Zero em/en-dashes and zero exclamation marks across student-facing UI copy. Automated grading is honestly described as automated checks and rubric review (never human reviewers or fake AI hype).
- **Anchor Domain**: OmniCart Operations (multi-brand e-commerce retailer return reconciliation and dispute triage).
- **Accessibility**: Strict WCAG 2.2 AA compliance across all surfaces. Automated static accessibility checks run via `scripts/a11y-static.mjs`.

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.


## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

## Keel Academy learner app

Server-rendered Next.js app. Content (units, lessons, checks) is read as
data from the content tree; grading state comes over HTTP from the grading
core (read-only reader), never from a direct database connection.

S2.5 surfaces: offline-or-Clerk auth (see `lib/auth.ts`), `/me` (enrollments
plus your own submissions), `/sign-in` `/sign-up` `/sign-out`, Stripe
checkout via the grading core's enroll service, and account-gated verdict
pages. Server env (never committed; `NEXT_PUBLIC_` carries only the public
Clerk publishable key):

    KEEL_READER_URL     read-only grading endpoint (S2.4)
    KEEL_ENROLL_URL     enrollment service base URL
    KEEL_ENROLL_SECRET  shared app token for that service
    KEEL_OFFLINE_AUTH_SECRET  signs offline-fake session cookies (dev only)
    KEEL_OFFLINE_AUTH_STORE  offline identity store path (default /tmp)
    CLERK_SECRET_KEY / NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY  real wiring

Without Clerk keys the app runs in offline mode: the deterministic auth fake
(pages say so) plus, when the enroll service points at the fake Stripe, the
whole sign-up -> checkout -> enrollment loop with no credentials and no
network. Production wiring: `platform/FOUNDER-WIRING.md`.
