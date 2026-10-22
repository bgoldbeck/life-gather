import { expect, it } from 'vitest'
import { readChatStream } from './chatStream'

it('decodes split UTF-8 drafts and returns only the completed turn', async () => {
  const turn = {
    id: 'turn',
    state: 'complete',
    result: { text: 'Synthetic 🌿' },
  }
  const wire = [
    { type: 'draft', text: 'Synthetic ' },
    { type: 'draft', text: '🌿' },
    { type: 'complete', turn },
  ]
    .map((e) => 'data: ' + JSON.stringify(e) + '\n\n')
    .join('')
  const bytes = new TextEncoder().encode(wire)
  const response = new Response(
    new ReadableStream({
      start(controller) {
        for (const byte of bytes) controller.enqueue(new Uint8Array([byte]))
        controller.close()
      },
    }),
    { headers: { 'content-type': 'text/event-stream' } },
  )
  const drafts: string[] = []
  expect(await readChatStream(response, (text) => drafts.push(text))).toEqual(
    turn,
  )
  expect(drafts).toEqual(['Synthetic ', 'Synthetic 🌿'])
})

it('rejects a draft-only disconnected stream', async () => {
  const response = new Response(
    'data: {"type":"draft","text":"Unfinished"}\n\n',
    { headers: { 'content-type': 'text/event-stream' } },
  )
  await expect(readChatStream(response, () => {})).rejects.toThrow(
    'interrupted',
  )
})

it('passes host statuses separately and rejects malformed ones', async () => {
  const turn = { id: 'turn', state: 'complete', result: { text: 'Done' } }
  const wire = (...events: unknown[]) =>
    new Response(
      events.map((e) => 'data: ' + JSON.stringify(e) + '\n\n').join(''),
      { headers: { 'content-type': 'text/event-stream' } },
    )
  const statuses: string[] = []
  const drafts: string[] = []
  expect(
    await readChatStream(
      wire(
        { type: 'status', text: 'Checking your request…' },
        { type: 'status', text: 'Searching your assets…' },
        { type: 'complete', turn },
      ),
      (text) => drafts.push(text),
      (text) => statuses.push(text),
    ),
  ).toEqual(turn)
  expect(statuses).toEqual(['Checking your request…', 'Searching your assets…'])
  expect(drafts).toEqual([])
  await expect(
    readChatStream(
      wire(
        { type: 'status', text: 'x'.repeat(201) },
        { type: 'complete', turn },
      ),
      () => {},
      () => {},
    ),
  ).rejects.toThrow('Invalid status event')
  await expect(
    readChatStream(
      wire({ type: 'status', text: 7 }, { type: 'complete', turn }),
      () => {},
    ),
  ).rejects.toThrow('Invalid status event')
})
