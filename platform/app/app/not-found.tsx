import Link from "next/link";

export default function NotFound() {
  return (
    <div className="shell section">
      <div className="max-w-[62ch]">
        <p className="eyebrow">404</p>
        <h1 className="heading-xl mt-4">That page does not exist</h1>
        <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          The link is wrong, or the page moved. Here is where most people are headed.
        </p>
        <ul className="mt-8 space-y-3">
          <li>
            <Link
              href="/"
              className="text-[15.5px] text-fern-link underline underline-offset-4 hover:text-phosphor-white"
            >
              Home
            </Link>
          </li>
          <li>
            <Link
              href="/curriculum"
              className="text-[15.5px] text-fern-link underline underline-offset-4 hover:text-phosphor-white"
            >
              The curriculum
            </Link>
          </li>
          <li>
            <Link
              href="/me"
              className="text-[15.5px] text-fern-link underline underline-offset-4 hover:text-phosphor-white"
            >
              Your dashboard
            </Link>
          </li>
        </ul>
      </div>
    </div>
  );
}
