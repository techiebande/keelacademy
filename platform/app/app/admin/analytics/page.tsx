import { Metadata } from "next";
import Link from "next/link";
import { getSessionUser, isAdminUser } from "@/lib/auth";
import { fetchAnalyticsSummary, fetchMacroFunnel, fetchDropoffBreakdown } from "@/lib/analytics";
import { AnalyticsDashboard } from "@/components/analytics/analytics-dashboard";

export const metadata: Metadata = {
  title: "Curriculum telemetry",
  description:
    "Operational summary, enrollment funnel, and per-unit friction metrics. Staff view.",
  robots: { index: false },
};

export default async function AdminAnalyticsPage() {
  const user = await getSessionUser();
  const isAdmin = isAdminUser(user);

  // Cohort-wide telemetry is staff data. Nothing is fetched for anyone else.
  if (!isAdmin) {
    return (
      <div className="shell section">
        <div className="card-dark max-w-[62ch]">
          <h1 className="heading-lg">This page is for staff</h1>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            It shows cohort-wide numbers, so student accounts cannot open it. Your progress
            and grading records are on your dashboard.
          </p>
          <Link href="/me" className="btn btn-primary btn-sm mt-7">
            Go to your dashboard
          </Link>
        </div>
      </div>
    );
  }

  const [summaryRes, funnelRes, dropoffRes] = await Promise.all([
    fetchAnalyticsSummary(),
    fetchMacroFunnel(),
    fetchDropoffBreakdown(),
  ]);

  const summary = summaryRes.state === "ok" ? summaryRes.data : null;
  const funnel = funnelRes.state === "ok" ? funnelRes.data : null;
  const dropoff = dropoffRes.state === "ok" ? dropoffRes.data : null;

  return (
    <div>
      <header className="shell border-b border-[color:var(--line-on-dark)] pb-10 pt-14">
        <p className="eyebrow">Staff view</p>
        <h1 className="heading-xl mt-4">Curriculum telemetry</h1>
        <p className="lead mt-5 max-w-[68ch]">
          Where students slow down, where they stop, what they ask about. Read it before
          rewriting a unit, because the numbers usually indict the lesson, not the students.
        </p>
      </header>

      <div className="shell py-12">
        <AnalyticsDashboard
          initialSummary={summary}
          initialFunnel={funnel}
          initialDropoff={dropoff}
        />
      </div>
    </div>
  );
}
