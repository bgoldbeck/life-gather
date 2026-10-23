export type MaintenanceReceipt = {
  task_id: string
  revision_id: string
  title: string
  state: 'open' | 'completed' | 'canceled'
  due_on: string | null
  completed_on: string | null
  timezone: string
}

export function ChatMaintenance({ task }: { task: MaintenanceReceipt }) {
  return (
    <section aria-label="Saved maintenance task" className="asset-findings">
      <h4>Saved maintenance task</h4>
      <p>{task.title}</p>
      <p>Status: {task.state}</p>
      <p>Due date: {task.due_on ?? 'Unknown'}</p>
      {task.state === 'completed' && (
        <p>Completion date: {task.completed_on ?? 'Unknown'}</p>
      )}
      <p>Calendar timezone: {task.timezone}</p>
      <p>
        Your recorded statement; earlier revisions remain in maintenance
        history.
      </p>
    </section>
  )
}
