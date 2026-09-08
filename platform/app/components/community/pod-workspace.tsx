"use client";

import { useState } from "react";
import type { PodDetails, PodPost } from "@/lib/practice";
import { formatUtc } from "@/lib/grading";

type PodWorkspaceProps = {
  studentId: number;
  initialPod: PodDetails | null;
  initialPosts: PodPost[];
};

export function PodWorkspace({
  studentId,
  initialPod,
  initialPosts,
}: PodWorkspaceProps) {
  const [pod, setPod] = useState<PodDetails | null>(initialPod);
  const [posts, setPosts] = useState<PodPost[]>(initialPosts);
  const [isAssigning, setIsAssigning] = useState(false);
  const [isPosting, setIsPosting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Form state for weekly check-in
  const [weekNumber, setWeekNumber] = useState<number>(1);
  const [shippedText, setShippedText] = useState("");
  const [brokeText, setBrokeText] = useState("");
  const [nextText, setNextText] = useState("");

  const handleJoinPod = async () => {
    setIsAssigning(true);
    setErrorMsg(null);
    try {
      const res = await fetch("/api/community/join", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ student_id: studentId }),
      });
      if (res.ok) {
        const data = await res.json();
        // Refresh members
        const membersRes = await fetch(`/api/community/members?student_id=${studentId}`);
        if (membersRes.ok) {
          const membersData = await membersRes.json();
          setPod(membersData.pod);
        } else {
          setPod({
            pod_id: data.pod_id,
            name: data.name,
            cohort_week: data.cohort_week,
            discord_channel_id: data.discord_channel_id,
            discord_role_id: data.discord_role_id,
            discord_channel_url: null,
            joined_at: data.joined_at,
            peers: [],
          });
        }
      } else {
        const err = await res.json().catch(() => ({}));
        setErrorMsg(err.message || err.error || "We could not assign a pod. Try again.");
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Network error.");
    } finally {
      setIsAssigning(false);
    }
  };

  const handleSubmitPost = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pod) return;
    setIsPosting(true);
    setErrorMsg(null);

    try {
      const res = await fetch("/api/community/posts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          student_id: studentId,
          pod_id: pod.pod_id,
          week_number: weekNumber,
          shipped_text: shippedText,
          broke_text: brokeText,
          next_text: nextText,
        }),
      });

      if (res.ok) {
        const newPost = await res.json();
        setPosts((prev) => [newPost, ...prev]);
        setShippedText("");
        setBrokeText("");
        setNextText("");
      } else {
        const err = await res.json().catch(() => ({}));
        setErrorMsg(err.message || err.error || "We could not post the check-in. Try again.");
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Network error.");
    } finally {
      setIsPosting(false);
    }
  };

  if (!pod) {
    return (
      <div className="card-dark max-w-[56ch]">
        <h2 className="heading-md">You are not in a pod yet</h2>
        <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          Joining puts you with students at the same point in the curriculum. Come as you
          are, lurkers welcome, posters celebrated.
        </p>
        <button
          type="button"
          onClick={handleJoinPod}
          disabled={isAssigning}
          className="btn btn-accent btn-sm mt-7"
        >
          {isAssigning ? "Joining" : "Join a pod"}
        </button>
        {errorMsg ? (
          <p
            role="alert"
            className="mt-6 rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[14.5px] leading-relaxed text-phosphor-white"
          >
            {errorMsg}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <section aria-labelledby="pod-title" className="card-dark">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <h2 id="pod-title" className="heading-md">
            {pod.name}
          </h2>
          <span className="chip chip-outline">WEEK {pod.cohort_week}</span>
        </div>

        {pod.discord_channel_url ? (
          <p className="mt-4 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            Your pod also has a chat channel.{" "}
            <a
              href={pod.discord_channel_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-fern-link underline underline-offset-4 hover:text-phosphor-white"
            >
              Open it
            </a>
            .
          </p>
        ) : null}

        <h3 className="mt-8 text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
          {pod.peers.length === 1 ? "1 member" : `${pod.peers.length} members`}
        </h3>
        <ul className="mt-4 flex flex-wrap gap-2">
          {pod.peers.map((peer) => (
            <li
              key={peer.student_id}
              className="rounded-lg border border-circuit-border bg-carbon-veil px-3 py-1.5 text-[14px] text-phosphor-white"
            >
              {peer.display_name}
              {peer.is_self ? (
                <span className="ml-2 text-[12px] text-[color:var(--text-faint-on-dark)]">
                  you
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
      <section aria-labelledby="checkin-title" className="card-dark">
        <h2 id="checkin-title" className="heading-md">
          File this week&rsquo;s check-in
        </h2>
        <form onSubmit={handleSubmitPost} className="mt-7 space-y-6">
          <div className="max-w-[8rem]">
            <label htmlFor="week-number" className="field-label">
              Week
            </label>
            <input
              id="week-number"
              type="number"
              min={1}
              max={52}
              value={weekNumber}
              onChange={(e) => setWeekNumber(parseInt(e.target.value, 10))}
              required
              className="field-input"
            />
          </div>
          <div>
            <label htmlFor="shipped-text" className="field-label">
              What did you ship?
            </label>
            <textarea
              id="shipped-text"
              value={shippedText}
              onChange={(e) => setShippedText(e.target.value)}
              rows={3}
              required
              placeholder="Units you finished, code you pushed, anything that is now done."
              className="field-input"
            />
          </div>
          <div>
            <label htmlFor="broke-text" className="field-label">
              What broke or blocked you?
            </label>
            <textarea
              id="broke-text"
              value={brokeText}
              onChange={(e) => setBrokeText(e.target.value)}
              rows={3}
              required
              placeholder="Checks that did not pass, concepts that did not land, time you lost. Be honest, everyone else is."
              className="field-input"
            />
          </div>
          <div>
            <label htmlFor="next-text" className="field-label">
              What are you doing next?
            </label>
            <textarea
              id="next-text"
              value={nextText}
              onChange={(e) => setNextText(e.target.value)}
              rows={3}
              required
              placeholder="The next unit and the gate you are aiming at."
              className="field-input"
            />
          </div>
          <button type="submit" disabled={isPosting} className="btn btn-accent btn-sm">
            {isPosting ? "Posting" : "Post check-in"}
          </button>
        </form>

        {errorMsg ? (
          <p
            role="alert"
            className="mt-6 rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[14.5px] leading-relaxed text-phosphor-white"
          >
            {errorMsg}
          </p>
        ) : null}
      </section>
      <section aria-labelledby="stream-title" className="card-dark">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <h2 id="stream-title" className="heading-md">
            What your pod posted
          </h2>
          <span className="font-code-mono text-[13px] text-moss-70">
            {posts.length === 1 ? "1 check-in" : `${posts.length} check-ins`}
          </span>
        </div>

        {posts.length === 0 ? (
          <p className="mt-6 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            Nobody has posted yet. You get to go first, a genuine honor.
          </p>
        ) : (
          <ul className="mt-7">
            {posts.map((post) => (
              <li
                key={post.id}
                className="border-t border-[color:var(--line-on-dark-strong)] py-6 first:border-t-0 first:pt-0"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <h3 className="font-goga text-[16px] font-medium text-phosphor-white">
                    {post.author_name}
                  </h3>
                  <span className="font-code-mono text-[12.5px] text-[color:var(--text-faint-on-dark)]">
                    {`Week ${post.week_number} · ${formatUtc(post.created_at)}`}
                  </span>
                </div>
                <dl className="mt-4 space-y-3 text-[14.5px] leading-relaxed">
                  <div>
                    <dt className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
                      Shipped
                    </dt>
                    <dd className="mt-1 text-[color:var(--text-muted-on-dark)]">
                      {post.shipped_text}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
                      Broke or blocked
                    </dt>
                    <dd className="mt-1 text-[color:var(--text-muted-on-dark)]">
                      {post.broke_text}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
                      Next
                    </dt>
                    <dd className="mt-1 text-[color:var(--text-muted-on-dark)]">
                      {post.next_text}
                    </dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
