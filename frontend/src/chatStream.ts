/** Bounded private stream decoding. Drafts are transient; only a terminal turn is saved. */
export async function readChatStream<T>(
  response: Response,
  onDraft: (text: string) => void,
): Promise<T> {
  if (
    !response.body ||
    !response.headers.get('content-type')?.includes('text/event-stream')
  )
    throw new Error('Invalid chat stream')
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8', { fatal: true })
  let pending = '',
    draft = '',
    total = 0
  let final: T | undefined
  function consume(frame: string) {
    const lines = frame.split('\n').filter((line) => line.startsWith('data:'))
    if (!lines.length) return
    if (final !== undefined)
      throw new Error('Unexpected event after completion')
    const event = JSON.parse(
      lines.map((line) => line.slice(5).trimStart()).join('\n'),
    )
    if (event.type === 'draft') {
      if (
        typeof event.text !== 'string' ||
        draft.length + event.text.length > 12000
      )
        throw new Error('Invalid answer draft')
      draft += event.text
      onDraft(draft)
    } else if (event.type === 'complete') {
      if (
        !event.turn ||
        typeof event.turn.id !== 'string' ||
        typeof event.turn.state !== 'string' ||
        !event.turn.result ||
        typeof event.turn.result !== 'object'
      )
        throw new Error('Invalid completed turn')
      final = event.turn as T
    } else if (event.type !== 'status') throw new Error('Invalid chat event')
  }
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (value) {
        total += value.byteLength
        if (total > 524288) throw new Error('Chat stream exceeded limit')
      }
      pending += decoder.decode(value, { stream: !done })
      pending = pending.replaceAll('\r\n', '\n')
      let end = pending.indexOf('\n\n')
      while (end >= 0) {
        consume(pending.slice(0, end))
        pending = pending.slice(end + 2)
        end = pending.indexOf('\n\n')
      }
      if (pending.length > 131072) throw new Error('Chat event exceeded limit')
      if (done) break
    }
    if (pending.trim() || final === undefined)
      throw new Error('Chat stream was interrupted')
    return final
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
