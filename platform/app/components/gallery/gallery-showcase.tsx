"use client";

import React, { useState } from "react";
import Link from "next/link";
import { StudentGalleryProject } from "@/lib/gallery";

type GalleryShowcaseProps = {
  submissionId: number;
  unitId: string;
  isPassed: boolean;
  defaultRepoUrl?: string | null;
  initialProject: StudentGalleryProject | null;
};

export function GalleryShowcase({
  submissionId,
  unitId,
  isPassed,
  defaultRepoUrl,
  initialProject,
}: GalleryShowcaseProps) {
  const [project, setProject] = useState<StudentGalleryProject | null>(initialProject);
  const [isEditing, setIsEditing] = useState(!initialProject || !initialProject.published);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Empty by default. Nothing writes a description on the student's behalf.
  const [title, setTitle] = useState(initialProject?.title || "");
  const [description, setDescription] = useState(initialProject?.description || "");
  const [repoUrl, setRepoUrl] = useState(initialProject?.repo_url || defaultRepoUrl || "");
  const [demoUrl, setDemoUrl] = useState(initialProject?.demo_url || "");
  const [walkthroughVideoUrl, setWalkthroughVideoUrl] = useState(
    initialProject?.walkthrough_video_url || "",
  );

  const handlePublish = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      const res = await fetch("/api/gallery/publish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          submission_id: submissionId,
          title,
          description,
          repo_url: repoUrl || undefined,
          demo_url: demoUrl || undefined,
          walkthrough_video_url: walkthroughVideoUrl || undefined,
        }),
      });

      const data = await res.json();
      if (res.ok) {
        setProject(data);
        setIsEditing(false);
        setSuccessMsg("This is live in the gallery now.");
      } else {
        setErrorMsg(data.message || data.error || "The gallery did not accept that. Try again.");
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Network error");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUnpublish = async () => {
    if (!project) return;
    setIsSubmitting(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      const res = await fetch("/api/gallery/unpublish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: project.id,
          unit_id: unitId,
        }),
      });

      const data = await res.json();
      if (res.ok) {
        setProject((prev) => (prev ? { ...prev, published: false } : null));
        setSuccessMsg("Taken down. It is no longer in the gallery.");
      } else {
        setErrorMsg(data.message || data.error || "That could not be taken down.");
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Network error");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isPassed) {
    return null;
  }

  return (
    <section aria-labelledby="showcase-title" className="card-dark">
      <h2 id="showcase-title" className="heading-md">
        Put this in the gallery
      </h2>
      <p className="mt-4 max-w-[70ch] text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
        Publishing is your choice, and you can take it down again. The public page shows
        your text, your name, and the passing verdict.
      </p>

      {project && project.published && !isEditing ? (
        <div className="mt-7">
          <div className="flex flex-wrap items-center gap-3">
            <span className="chip chip-live">PUBLISHED</span>
            <Link
              href={`/gallery/${project.id}`}
              className="text-[14.5px] text-fern-link underline-offset-4 hover:underline"
            >
              See how it looks in the gallery
            </Link>
          </div>
          <dl className="mt-6">
            <ShowcaseFact label="Title" value={project.title} />
            <ShowcaseFact label="Description" value={project.description} />
            {project.repo_url ? <ShowcaseFact label="Repository" value={project.repo_url} /> : null}
            {project.demo_url ? <ShowcaseFact label="Demo" value={project.demo_url} /> : null}
            {project.walkthrough_video_url ? (
              <ShowcaseFact label="Walkthrough" value={project.walkthrough_video_url} />
            ) : null}
          </dl>
          <div className="mt-7 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => setIsEditing(true)}
              className="btn btn-ghost btn-sm"
            >
              Change what it says
            </button>
            <button
              type="button"
              onClick={handleUnpublish}
              disabled={isSubmitting}
              className="btn btn-ghost btn-sm"
            >
              {isSubmitting ? "Taking it down" : "Take it down"}
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={handlePublish} className="mt-7">
          <h3 className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
            {project?.published ? "Change the listing" : "What the gallery will show"}
          </h3>
          <div className="mt-5 space-y-5">
            <div>
              <label htmlFor="proj-title" className="field-label">
                Title
              </label>
              <input
                id="proj-title"
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                maxLength={120}
                placeholder="Invoice reconciliation with a dispute queue"
                className="field-input"
              />
            </div>
            <div>
              <label htmlFor="proj-desc" className="field-label">
                What it does
              </label>
              <textarea
                id="proj-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={4}
                required
                placeholder="Three sentences: what it takes in, what it puts out, and what you would fix next."
                className="field-input font-inter-variable"
              />
            </div>
            <div>
              <label htmlFor="proj-repo" className="field-label">
                Repository URL
              </label>
              <input
                id="proj-repo"
                type="url"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/you/keel-3.2.1-your-suffix"
                className="field-input"
              />
            </div>
            <div>
              <label htmlFor="proj-demo" className="field-label">
                Demo URL, if it is deployed somewhere
              </label>
              <input
                id="proj-demo"
                type="url"
                value={demoUrl}
                onChange={(e) => setDemoUrl(e.target.value)}
                placeholder="Optional"
                className="field-input"
              />
            </div>
            <div>
              <label htmlFor="proj-video" className="field-label">
                Walkthrough video URL
              </label>
              <input
                id="proj-video"
                type="url"
                value={walkthroughVideoUrl}
                onChange={(e) => setWalkthroughVideoUrl(e.target.value)}
                placeholder="Optional. Links from supported video hosts embed on the project page."
                className="field-input"
              />
            </div>
            <div className="flex flex-wrap gap-3 pt-2">
              <button type="submit" disabled={isSubmitting} className="btn btn-accent btn-sm">
                {isSubmitting
                  ? "Saving"
                  : project?.published
                    ? "Save the changes"
                    : "Publish it"}
              </button>
              {project?.published ? (
                <button
                  type="button"
                  onClick={() => setIsEditing(false)}
                  className="btn btn-ghost btn-sm"
                >
                  Cancel
                </button>
              ) : null}
            </div>

          </div>
        </form>

      )}

      {errorMsg ? (
        <p
          role="alert"
          className="mt-6 rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[14.5px] leading-relaxed text-phosphor-white"
        >
          {errorMsg}
        </p>
      ) : null}
      {successMsg ? (
        <p
          aria-live="polite"
          className="mt-6 font-code-mono text-[13px] text-lime-pulse"
        >
          {successMsg}
        </p>
      ) : null}
    </section>
  );
}

function ShowcaseFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-t border-[color:var(--line-on-dark-strong)] py-3 first:border-t-0 first:pt-0">
      <dt className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
        {label}
      </dt>
      <dd className="mt-2 max-w-[74ch] text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
        {value}
      </dd>
    </div>
  );
}
