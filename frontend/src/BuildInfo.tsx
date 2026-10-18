export type Build = { version: string; revision: string | null }

export function BuildInfo({ build }: { build?: Build }) {
  if (!build) return null
  return (
    <div className="build-info" aria-label="Application version">
      <span>v{build.version}</span>
      <span aria-hidden="true">·</span>
      {build.revision ? (
        <span title={`Git revision ${build.revision}`}>
          {build.revision.slice(0, 7)}
        </span>
      ) : (
        <span>Source build</span>
      )}
    </div>
  )
}
