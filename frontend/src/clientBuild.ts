import type { Build } from './BuildInfo'

declare const __LIFEGATHER_FRONTEND_BUILD__: Build | null
export const clientBuild = __LIFEGATHER_FRONTEND_BUILD__

export function buildChanged(
  loaded: Build | undefined,
  current: Build | undefined,
) {
  return (
    !!loaded &&
    !!current &&
    (loaded.version !== current.version ||
      (!!loaded.revision &&
        !!current.revision &&
        loaded.revision !== current.revision))
  )
}
