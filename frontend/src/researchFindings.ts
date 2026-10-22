// Lets an open asset's findings list reload after a save from Chat.
export const FINDING_SAVED = 'lifegather:research-finding-saved'

export function researchedAt(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}
