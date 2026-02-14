import {
  db,
  getAllUserGymSessions,
  getAllUserTasks,
  getAllUserThesisLogs,
  getLegacyBackupForUser,
  nowIso,
  putLegacyBackup,
  putTaskLocal,
} from './db'
import type { GymSessionRecord, TaskRecord, ThesisLogRecord } from '../types'

export const serializeBackup = async (userId: string) => {
  const tasks = await getAllUserTasks(userId)
  const gymSessions = await getAllUserGymSessions(userId)
  const thesisLogs = await getAllUserThesisLogs(userId)
  const legacyBackups = await getLegacyBackupForUser(userId)
  const currentLocalStorage = Object.keys(window.localStorage)
    .filter((key) => key.startsWith('fg_'))
    .reduce<Record<string, string | null>>((acc, key) => {
      acc[key] = window.localStorage.getItem(key)
      return acc
    }, {})

  return {
    version: 1,
    exported_at: nowIso(),
    user_id: userId,
    tasks,
    gym_sessions: gymSessions,
    thesis_logs: thesisLogs,
    legacy_local_storage: currentLocalStorage,
    legacy_backups: legacyBackups,
  }
}

export const downloadJson = (filename: string, payload: unknown) => {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

const isTaskArray = (value: unknown): value is TaskRecord[] =>
  Array.isArray(value) &&
  value.every((item) => {
    if (!item || typeof item !== 'object') {
      return false
    }
    const row = item as Partial<TaskRecord>
    return typeof row.id === 'string' && typeof row.title === 'string'
  })

const isGymSessionArray = (value: unknown): value is GymSessionRecord[] =>
  Array.isArray(value) &&
  value.every((item) => {
    if (!item || typeof item !== 'object') {
      return false
    }
    const row = item as Partial<GymSessionRecord>
    return typeof row.id === 'string' && typeof row.session_name === 'string'
  })

const isThesisLogArray = (value: unknown): value is ThesisLogRecord[] =>
  Array.isArray(value) &&
  value.every((item) => {
    if (!item || typeof item !== 'object') {
      return false
    }
    const row = item as Partial<ThesisLogRecord>
    return typeof row.id === 'string' && typeof row.date === 'string'
  })

export const importBackupPayload = async (userId: string, payload: unknown) => {
  if (!payload || typeof payload !== 'object') {
    throw new Error('Le fichier JSON est invalide.')
  }

  const parsed = payload as {
    tasks?: unknown
    gym_sessions?: unknown
    thesis_logs?: unknown
    legacy_local_storage?: Record<string, string | null>
    legacy_backups?: Array<{ payload?: Record<string, string | null> }>
  }

  let importedTasks = 0
  if (isTaskArray(parsed.tasks)) {
    for (const task of parsed.tasks) {
      const normalized: TaskRecord = {
        ...task,
        user_id: userId,
        tags: Array.isArray(task.tags) ? task.tags : [],
        timezone: task.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
        updated_at: task.updated_at || nowIso(),
        created_at: task.created_at || nowIso(),
        top3_slot: task.top3_slot ?? null,
        original_scheduled_date: task.original_scheduled_date ?? null,
        last_notified_at: task.last_notified_at ?? null,
        completed_at: task.completed_at ?? null,
        status: task.status === 'done' ? 'done' : 'todo',
        priority:
          task.priority === 'high' || task.priority === 'medium' || task.priority === 'normal'
            ? task.priority
            : 'normal',
      }
      await putTaskLocal(normalized, true)
      importedTasks += 1
    }
  }

  if (isGymSessionArray(parsed.gym_sessions)) {
    for (const session of parsed.gym_sessions) {
      await db.gymSessions.put({
        ...session,
        user_id: userId,
        date: session.date || nowIso().slice(0, 10),
        created_at: session.created_at || nowIso(),
        updated_at: session.updated_at || nowIso(),
        exercises: Array.isArray(session.exercises) ? session.exercises : [],
      })
    }
  }

  if (isThesisLogArray(parsed.thesis_logs)) {
    for (const log of parsed.thesis_logs) {
      await db.thesisLogs.put({
        ...log,
        user_id: userId,
        date: log.date || nowIso().slice(0, 10),
        focus_minutes: Number.isFinite(log.focus_minutes) ? log.focus_minutes : 0,
        words_written: Number.isFinite(log.words_written) ? log.words_written : 0,
        note: log.note || '',
        created_at: log.created_at || nowIso(),
        updated_at: log.updated_at || nowIso(),
      })
    }
  }

  if (parsed.legacy_local_storage) {
    for (const [key, value] of Object.entries(parsed.legacy_local_storage)) {
      if (!key.startsWith('fg_')) {
        continue
      }
      if (value === null) {
        window.localStorage.removeItem(key)
      } else {
        window.localStorage.setItem(key, value)
      }
    }
  }

  if (Array.isArray(parsed.legacy_backups)) {
    for (const backup of parsed.legacy_backups) {
      if (!backup.payload) {
        continue
      }
      await putLegacyBackup({
        id: crypto.randomUUID(),
        user_id: userId,
        payload: backup.payload,
        created_at: nowIso(),
      })
    }
  }

  return { importedTasks }
}
