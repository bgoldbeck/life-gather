export type MaintenanceRevision = {
  id: string
  title: string
  due_on: string | null
  timezone: string
  state: 'open' | 'completed' | 'canceled'
  completed_on: string | null
  source_id: string
  previous_id: string | null
  recorded_at: number
  superseded_at: number | null
  origin?: { interface: string; method: string } | null
}
export type MaintenanceTask = {
  id: string
  entity_id: string
  target: { id: string; name: string; kind: string }
  revision: MaintenanceRevision
  state_token: string
  due_status: string
  local_today: string
}
export type MaintenanceRequest = (
  path: string,
  init?: RequestInit,
) => Promise<unknown>
export class MaintenanceError extends Error {
  readonly status: number
  constructor(status: number) {
    super('Maintenance request failed')
    this.status = status
  }
}
export const maintenanceState = (state: string) =>
  ({
    open: 'Open',
    completed: 'Completed',
    canceled: 'Canceled',
    overdue: 'Past due',
    today: 'Due today',
    upcoming: 'Upcoming',
    unscheduled: 'Due date unknown',
  })[state] ?? state

export function maintenanceTask(
  value: unknown,
  expected?: string,
): MaintenanceTask {
  const row = value as Partial<MaintenanceTask> | null
  if (
    !row ||
    typeof row.id !== 'string' ||
    !row.id ||
    (expected && row.id !== expected) ||
    typeof row.entity_id !== 'string' ||
    !row.target ||
    typeof row.target.id !== 'string' ||
    typeof row.target.name !== 'string' ||
    typeof row.state_token !== 'string' ||
    !/^[a-f0-9]{64}$/.test(row.state_token) ||
    typeof row.due_status !== 'string'
  )
    throw new Error('Invalid maintenance task')
  return {
    ...row,
    revision: maintenanceRevision(row.revision),
  } as MaintenanceTask
}

export function maintenanceRevision(value: unknown): MaintenanceRevision {
  const row = value as Partial<MaintenanceRevision> | null
  const calendar = (date: unknown) =>
    date === null ||
    (typeof date === 'string' && /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(date))
  if (
    !row ||
    typeof row.id !== 'string' ||
    !row.id ||
    typeof row.title !== 'string' ||
    typeof row.timezone !== 'string' ||
    typeof row.source_id !== 'string' ||
    !row.source_id ||
    !['open', 'completed', 'canceled'].includes(row.state ?? '') ||
    !calendar(row.due_on) ||
    !calendar(row.completed_on) ||
    !Number.isSafeInteger(row.recorded_at) ||
    (row.superseded_at !== null && !Number.isSafeInteger(row.superseded_at)) ||
    (row.previous_id !== null && typeof row.previous_id !== 'string') ||
    (row.origin != null &&
      (typeof row.origin !== 'object' ||
        typeof row.origin.interface !== 'string' ||
        typeof row.origin.method !== 'string'))
  )
    throw new Error('Invalid maintenance revision')
  return row as MaintenanceRevision
}
