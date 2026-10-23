import { Button } from '@/components/ui/button'
import { researchedAt } from './researchFindings'

export type SavedResearchCitation = {
  id: string
  citation: number
  asset_id: string
  asset_name: string
  title: string
  url: string
  published: string | null
  researched_at: string
  recorded_at: number
  excerpt_kind: 'source' | 'answer'
  excerpts: string[]
}

function webLink(value: string) {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:'
  } catch {
    return false
  }
}

export function SavedResearchCitations({
  items,
  limited = false,
  onOpenAsset,
}: {
  items: SavedResearchCitation[]
  limited?: boolean
  onOpenAsset?: (id: string) => void
}) {
  return (
    <section aria-label="Saved research inspected" className="asset-findings">
      <h4>Saved research inspected</h4>
      <p>
        Saved snapshots read for this reply. Researched dates indicate their
        age.
      </p>
      <p>
        Web findings describe a product model and do not establish ownership,
        purchase details or parts compatibility. Check your unit's label and the
        manufacturer before relying on them.
      </p>
      {limited && (
        <p>
          This reply inspected at most five saved findings. Other saved research
          may exist.
        </p>
      )}
      {!items.length && <p>No active saved findings were read.</p>}
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            {webLink(item.url) ? (
              <a href={item.url} target="_blank" rel="noopener noreferrer">
                Research {item.citation}: {item.title}
              </a>
            ) : (
              <span>
                Research {item.citation}: {item.title}
              </span>
            )}
            <p className="asset-findings-meta">
              {item.published
                ? `Page dated ${item.published}`
                : 'Page date not reported'}
              {' · '}Researched {researchedAt(item.researched_at)}
              {' · '}Saved {new Date(item.recorded_at / 1000).toLocaleString()}
            </p>
            <p>
              {item.excerpt_kind === 'answer'
                ? 'Saved generated answer excerpts (not page quotations)'
                : 'Saved source excerpts'}
            </p>
            {item.excerpts.map((text, index) => (
              <p key={index}>{text}</p>
            ))}
            {!item.excerpts.length && (
              <p>No excerpts were saved. Open the source to inspect it.</p>
            )}
            {onOpenAsset && (
              <Button
                variant="outline"
                onClick={() => onOpenAsset(item.asset_id)}
              >
                Open {item.asset_name} saved research
              </Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
