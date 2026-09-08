import type { Metadata } from "next";
import Link from "next/link";
import { getSessionUser } from "@/lib/auth";
import { ensureStudent } from "@/lib/enroll";
import { fetchPodMembers, fetchPodPosts, PodDetails, PodPost } from "@/lib/practice";
import { PodWorkspace } from "@/components/community/pod-workspace";

export const metadata: Metadata = {
  title: "Your pod",
  description:
    "Weekly check-ins with students moving through the same units as you.",
};

export default async function CommunityPage() {
  const user = await getSessionUser();
  if (!user) {
    return (
      <div className="shell section">
        <div className="card-dark max-w-[52ch]">
          <h1 className="heading-lg">Your pod</h1>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            Sign in to see the people in your pod and file your weekly check-in.
          </p>
          <Link href="/sign-in?next=/community" className="btn btn-primary btn-sm mt-7">
            Sign in
          </Link>
        </div>
      </div>
    );
  }

  const bridged = await ensureStudent(user);
  if (bridged.state !== "ok") {
    return (
      <div className="shell section">
        <div className="card-dark max-w-[52ch]">
          <h1 className="heading-lg">Your pod</h1>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            We could not load your account. Nothing is lost. Refresh.
          </p>
        </div>
      </div>
    );
  }

  const studentId = bridged.data;
  const podRes = await fetchPodMembers(studentId);
  let initialPod: PodDetails | null = null;
  let initialPosts: PodPost[] = [];
  if (podRes.state === "ok" && podRes.data.has_pod && podRes.data.pod) {
    initialPod = podRes.data.pod;
    const postsRes = await fetchPodPosts(initialPod.pod_id);
    if (postsRes.state === "ok") initialPosts = postsRes.data.posts;
  }

  return (
    <div>
      <header className="shell border-b border-[color:var(--line-on-dark)] pb-10 pt-14">
        <p className="eyebrow">Your pod</p>
        <h1 className="heading-xl mt-4">Show your work, every week</h1>
        <p className="lead mt-5 max-w-[68ch]">
          A pod is a small crew of students in the same phase as you. Once a week, each of
          you posts three short answers: what shipped, what broke, what is next. That is
          the whole thing: shipping in public, with witnesses.
        </p>
      </header>

      <div className="shell py-12">
        <PodWorkspace initialPod={initialPod} initialPosts={initialPosts} studentId={studentId} />
      </div>
    </div>
  );
}
