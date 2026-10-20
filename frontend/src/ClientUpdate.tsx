import { Button } from '@/components/ui/button'
import type { Build } from './BuildInfo'
import { buildChanged } from './clientBuild'
import './client-update.css'

export function ClientUpdateNotice({
  loaded,
  current,
  onReload = () => window.location.reload(),
}: {
  loaded?: Build
  current?: Build
  onReload?: () => void
}) {
  if (!buildChanged(loaded, current)) return null
  return (
    <aside
      className="client-update-notice"
      role="status"
      aria-label="Application update"
    >
      <p>
        LifeGather has been updated. Reload to use the current version. Unsaved
        drafts will be lost.
      </p>
      <Button variant="outline" onClick={onReload}>
        Reload LifeGather
      </Button>
    </aside>
  )
}
