export function ContentArriving({ what }: { what: string }) {
  return (
    <div className="rounded-lg border border-circuit-border bg-carbon-veil p-5">
      <p className="chip chip-outline">PLANNED</p>
      <p className="mt-3 text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
        {what} is planned. We have not written it yet. It opens here once the unit and
        its checks are ready.
      </p>
    </div>
  );
}
