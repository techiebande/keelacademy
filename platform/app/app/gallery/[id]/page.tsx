import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchGalleryProject } from "@/lib/gallery";
import { formatUtc } from "@/lib/grading";
import { humanizeId } from "@/lib/text";

export const dynamic = "force-dynamic";

type Props = {
  params: Promise<{ id: string }>;
};

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { id } = await props.params;
  const numId = parseInt(id, 10);
  if (isNaN(numId)) return { title: "Project not found" };

  const result = await fetchGalleryProject(numId);
  if (result.state !== "ok") return { title: "Project" };

  return {
    title: result.data.title,
    description: result.data.description.slice(0, 160),
  };
}

function getEmbedUrl(url: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.hostname.includes("youtube.com") && parsed.searchParams.get("v")) {
      return `https://www.youtube.com/embed/${parsed.searchParams.get("v")}`;
    }
    if (parsed.hostname === "youtu.be") {
      return `https://www.youtube.com/embed${parsed.pathname}`;
    }
    if (parsed.hostname.includes("loom.com") && parsed.pathname.includes("/share/")) {
      return url.replace("/share/", "/embed/");
    }
    if (parsed.hostname.includes("vimeo.com")) {
      const match = /\/(\d+)/.exec(parsed.pathname);
      if (match) return `https://player.vimeo.com/video/${match[1]}`;
    }
    return url;
  } catch {
    return url;
  }
}

export default async function GalleryProjectDetailPage(props: Props) {
  const { id } = await props.params;
  const numId = parseInt(id, 10);
  if (isNaN(numId)) notFound();

  const result = await fetchGalleryProject(numId);
  if (result.state === "rejected" && result.status === 404) {
    notFound();
  }

  if (result.state !== "ok") {
    return (
      <div className="shell section">
        <div className="card-dark max-w-[62ch]">
          <h1 className="heading-lg">We could not load this project</h1>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            We could not load this project. Refresh.
          </p>
          <Link href="/gallery" className="btn btn-primary btn-sm mt-7">
            Back to the gallery
          </Link>
        </div>
      </div>
    );
  }

  const project = result.data;
  const verdict = project.verdict;
  const verdictJson = (verdict?.json || {}) as {
    judge?: { criteria?: { id: string; verdict: string; evidence: string }[] };
    layer1?: { checks?: { id: string; type: string; status: string; note: string }[] };
  };
  const judge = verdictJson.judge || {};
  const criteria = judge.criteria || [];
  const layer1 = verdictJson.layer1 || {};
  const layer1Checks = layer1.checks || [];

  const embedUrl = getEmbedUrl(project.walkthrough_video_url);

  return (
    <div>
      <header className="shell border-b border-[color:var(--line-on-dark)] pb-10 pt-14">
        <nav
          aria-label="Breadcrumb"
          className="text-[13px] text-[color:var(--text-faint-on-dark)]"
        >
          <Link href="/gallery" className="hover:text-phosphor-white">
            Gallery
          </Link>
          <span className="px-2">/</span>
          <Link href={`/gallery?phase=${project.phase}`} className="hover:text-phosphor-white">
            Phase {project.phase}
          </Link>
          <span className="px-2">/</span>
          <span className="text-[color:var(--text-muted-on-dark)]">Project #{project.id}</span>
        </nav>

        <h1 className="heading-xl mt-7 max-w-[26ch]">{project.title}</h1>
        <p className="mt-4 text-[15px] text-[color:var(--text-muted-on-dark)]">
          {`${project.student_name} · ${project.unit_title} (unit ${project.unit_id}) · ${formatUtc(project.created_at)}`}
        </p>

        {project.repo_url || project.demo_url ? (
          <div className="mt-7 flex flex-wrap gap-3">
            {project.repo_url ? (
              <a
                href={project.repo_url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-primary btn-sm"
              >
                Read the code
              </a>
            ) : null}
            {project.demo_url ? (
              <a
                href={project.demo_url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-ghost btn-sm"
              >
                Try the demo
              </a>
            ) : null}
          </div>
        ) : null}
      </header>

      <div className="shell space-y-8 py-12">
        <section aria-labelledby="overview-title" className="card-dark max-w-[74ch]">
          <h2 id="overview-title" className="heading-md">
            What it does
          </h2>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            {project.description}
          </p>
        </section>

        {embedUrl ? (
          <section aria-labelledby="walkthrough-title" className="card-dark">
            <h2 id="walkthrough-title" className="heading-md">
              The walkthrough
            </h2>
            <div className="mt-6 aspect-video w-full overflow-hidden rounded-lg border border-circuit-border bg-void-black">
              <iframe
                src={embedUrl}
                title="Project walkthrough"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                className="h-full w-full"
              />
            </div>
          </section>
        ) : null}
        <section aria-labelledby="verification-title" className="card-dark">
          <div className="flex flex-wrap items-baseline justify-between gap-4">
            <h2 id="verification-title" className="heading-md">
              How it was graded
            </h2>
            <span className="font-code-mono text-[13px] text-moss-70">
              {`Submission #${project.submission_id} · ${project.commit_sha.slice(0, 7)}`}
            </span>
          </div>
          <p className="mt-3 max-w-[74ch] text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            This is the same verdict the student saw, published with the project.
          </p>

          {criteria.length > 0 ? (
            <div className="mt-8">
              <h3 className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
                Rubric review · {criteria.length} criteria
              </h3>
              <ul className="mt-4">
                {criteria.map((c, i) => (
                  <li
                    key={c.id || i}
                    className="border-t border-[color:var(--line-on-dark-strong)] py-4 first:border-t-0 first:pt-0"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <span className="text-[15px] text-phosphor-white">{humanizeId(c.id)}</span>
                      <span
                        className={c.verdict === "pass" ? "chip chip-live" : "chip chip-alert"}
                      >
                        {c.verdict === "pass" ? "PASSED" : "NOT YET"}
                      </span>
                    </div>
                    {c.evidence ? (
                      <pre className="mt-3 overflow-x-auto rounded-lg border border-circuit-border bg-void-black p-4">
                        <code className="font-code-mono text-[12.5px] leading-relaxed text-moss-80">
                          {c.evidence}
                        </code>
                      </pre>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {layer1Checks.length > 0 ? (
            <div className="mt-8">
              <h3 className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
                Automated checks · {layer1Checks.length}
              </h3>
              <ul className="mt-4">
                {layer1Checks.map((chk, i) => (
                  <li
                    key={chk.id || i}
                    className="flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--line-on-dark-strong)] py-3 first:border-t-0 first:pt-0"
                  >
                    <span className="text-[15px] text-phosphor-white">{humanizeId(chk.id)}</span>
                    <span className={chk.status === "pass" ? "chip chip-live" : "chip chip-alert"}>
                        {chk.status === "pass" ? "PASSED" : "NOT YET"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
