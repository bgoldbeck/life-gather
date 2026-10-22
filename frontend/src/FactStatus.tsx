const hints: Record<string, string> = {
  stated: 'Stated in saved evidence',
  verified: 'Stated and checked against evidence',
  inferred: 'Inferred; not confirmed by you',
  unknown: 'Not known',
}

// A statement's status as a small badge, so stated facts read differently from
// inferences and unknowns. The text stays the raw status word.
export function FactStatus({ status }: { status: string }) {
  return (
    <span className="fact-status" data-status={status} title={hints[status]}>
      {status}
    </span>
  )
}
