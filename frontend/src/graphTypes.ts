export type GraphEntity = {
  id: string
  name: string
  kind: string
  source_id: string
}
export type GraphFact = {
  id: string
  subject_id: string
  object_id: string | null
  predicate: string
  value: string | boolean | number | null
  status: string
  evidence: { source_id: string; quote?: string | null }[]
  valid_from: string | null
  valid_to: string | null
  recorded_at: number
}
export type GraphData = {
  entity: GraphEntity
  nodes: GraphEntity[]
  edges: GraphFact[]
  facts: GraphFact[]
  truncated: boolean
  next_fact_cursor: string | null
}
