import Dexie, { type Table } from 'dexie'
import type {
  GymSessionRecord,
  LegacyBackupRecord,
  MetaRecord,
  QueueOperation,
  TaskRecord,
  ThesisLogRecord,
} from '../types'

export const SYNC_BATCH_SIZE = 100

class DashboardDB extends Dexie {
  tasks!: Table<TaskRecord, string>
  queue!: Table<QueueOperation, string>
  meta!: Table<MetaRecord, string>
  legacyBackups!: Table<LegacyBackupRecord, string>
  gymSessions!: Table<GymSessionRecord, string>
  thesisLogs!: Table<ThesisLogRecord, string>

  constructor() {
    super('focus_grid_dashboard')
    this.version(1).stores({
      tasks:
        'id, user_id, status, scheduled_date, updated_at, completed_at, [user_id+scheduled_date], [user_id+updated_at], [user_id+status]',
      queue: 'id, user_id, created_at, type, task_id, retries',
      meta: '&key',
      legacyBackups: '&id, user_id, created_at',
    })
    this.version(2).stores({
      tasks:
        'id, user_id, status, scheduled_date, updated_at, completed_at, [user_id+scheduled_date], [user_id+updated_at], [user_id+status]',
      queue: 'id, user_id, created_at, type, task_id, retries',
      meta: '&key',
      legacyBackups: '&id, user_id, created_at',
      gymSessions: 'id, user_id, date, updated_at, [user_id+date], [user_id+updated_at]',
      thesisLogs: 'id, user_id, date, updated_at, [user_id+date], [user_id+updated_at]',
    })
  }
}

export const db = new DashboardDB()

export const nowIso = () => new Date().toISOString()

const toMs = (iso: string | null | undefined) => (iso ? new Date(iso).getTime() : 0)

export const isIncomingNewer = (incoming: TaskRecord, current: TaskRecord | undefined) => {
  if (!current) {
    return true
  }
  return toMs(incoming.updated_at) > toMs(current.updated_at)
}

export const enqueueTaskUpsert = async (task: TaskRecord) => {
  await db.queue.put({
    id: crypto.randomUUID(),
    user_id: task.user_id,
    type: 'upsert_task',
    task_id: task.id,
    payload: task,
    created_at: nowIso(),
    retries: 0,
  })
}

export const enqueueTaskDelete = async (userId: string, taskId: string) => {
  await db.queue.put({
    id: crypto.randomUUID(),
    user_id: userId,
    type: 'delete_task',
    task_id: taskId,
    payload: { id: taskId },
    created_at: nowIso(),
    retries: 0,
  })
}

export const putTaskLocal = async (task: TaskRecord, shouldQueue = true) => {
  await db.tasks.put(task)
  if (shouldQueue) {
    await enqueueTaskUpsert(task)
  }
}

export const deleteTaskLocal = async (userId: string, taskId: string, shouldQueue = true) => {
  await db.tasks.delete(taskId)
  if (shouldQueue) {
    await enqueueTaskDelete(userId, taskId)
  }
}

export const upsertTasksFromRemote = async (tasks: TaskRecord[]) => {
  await db.transaction('rw', db.tasks, async () => {
    for (const incoming of tasks) {
      const current = await db.tasks.get(incoming.id)
      if (isIncomingNewer(incoming, current)) {
        await db.tasks.put(incoming)
      }
    }
  })
}

export const getPendingQueue = (userId: string) =>
  db.queue.where('user_id').equals(userId).sortBy('created_at').then((rows) => rows.slice(0, SYNC_BATCH_SIZE))

export const markQueueProcessed = async (queueId: string) => {
  await db.queue.delete(queueId)
}

export const bumpQueueRetry = async (queueId: string) => {
  const item = await db.queue.get(queueId)
  if (!item) {
    return
  }
  await db.queue.put({ ...item, retries: item.retries + 1 })
}

export const setMetaValue = async (key: string, value: string) => {
  await db.meta.put({ key, value })
}

export const getMetaValue = async (key: string) => {
  const record = await db.meta.get(key)
  return record?.value ?? null
}

export const putLegacyBackup = async (record: LegacyBackupRecord) => {
  await db.legacyBackups.put(record)
}

export const getLegacyBackupForUser = async (userId: string) =>
  db.legacyBackups.where('user_id').equals(userId).reverse().sortBy('created_at')

export const getAllUserTasks = (userId: string) =>
  db.tasks.where('user_id').equals(userId).toArray()

export const getAllUserGymSessions = (userId: string) =>
  db.gymSessions.where('user_id').equals(userId).toArray()

export const getAllUserThesisLogs = (userId: string) =>
  db.thesisLogs.where('user_id').equals(userId).toArray()
