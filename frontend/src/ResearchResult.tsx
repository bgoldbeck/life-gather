export type ResearchSource = {
  url: string
  title: string
  published: string | null
  excerpt_kind: 'source' | 'answer'
  excerpts: string[]
}
export type WebResearch = {
  researched_at: string
  queries: string[]
  searches: number
  shared_record: { id: string; name: string } | null
  sources: ResearchSource[]
  identity_note: string
}

function researchedAt(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export function ResearchResult({ research }: { research: WebResearch }) {
  return (
    <section className="chat-research" aria-label="Web research sources">
      <p className="chat-label">
        Researched {researchedAt(research.researched_at)} ·{' '}
        {research.shared_record
          ? `Shared saved details of ${research.shared_record.name}`
          : 'No saved record details shared'}
      </p>
      {!!research.queries.length && (
        <p>Searches run: {research.queries.join('; ')}</p>
      )}
      {!!research.sources.length && (
        <ol>
          {research.sources.map((source) => (
            <li key={source.url}>
              <a href={source.url} target="_blank" rel="noopener noreferrer">
                {source.title}
              </a>{' '}
              <span className="chat-research-date">
                {source.published
                  ? `Page dated ${source.published}`
                  : 'Page date not reported'}
              </span>
              {source.excerpts.map((excerpt) => (
                <blockquote key={excerpt}>
                  {source.excerpt_kind === 'answer' ? 'Cited for: ' : ''}
                  {excerpt}
                </blockquote>
              ))}
            </li>
          ))}
        </ol>
      )}
      <p role="note">{research.identity_note}</p>
    </section>
  )
}
