import { todayLocalDate } from './date'
import {
  getAllUserTasks,
  getMetaValue,
  nowIso,
  putLegacyBackup,
  putTaskLocal,
  setMetaValue,
} from './db'
import type { LegacyTask, TaskPriority, TaskRecord } from '../types'

const LEGACY_KEYS = [
  'fg_tasks',
  'fg_gym_history',
  'fg_meals',
  'fg_meal_history',
  'fg_thesis_logs',
  'fg_workout_templates',
  'fg_resources',
] as const

const migrationMetaKey = (userId: string) => `legacy_migration_done_${userId}`

const safeJsonParse = <T>(raw: string | null, fallback: T): T => {
  if (!raw) {
    return fallback
  }
  try {
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

const normalizePriority = (value: string | undefined): TaskPriority => {
  if (value === 'high' || value === 'medium' || value === 'normal') {
    return value
  }
  return 'normal'
}

const toLegacyTaskRecord = (legacy: LegacyTask, userId: string, tz: string): TaskRecord => {
  const now = nowIso()
  const timestampFromId =
    typeof legacy.id === 'number' && legacy.id > 1000000000000 ? new Date(legacy.id).toISOString() : now

  return {
    id: crypto.randomUUID(),
    user_id: userId,
    title: legacy.text?.trim() || 'Tâche importée',
    status: legacy.completed ? 'done' : 'todo',
    priority: normalizePriority(legacy.priority),
    tags: legacy.migrated ? ['legacy-migrated'] : [],
    scheduled_date: legacy.date || todayLocalDate(),
    due_time: null,
    estimate_minutes: null,
    energy: null,
    created_at: timestampFromId,
    updated_at: now,
    completed_at: legacy.completed ? now : null,
    original_scheduled_date: legacy.migrated ? legacy.date || null : null,
    timezone: tz,
    top3_slot: null,
    last_notified_at: null,
  }
}

export const getLegacyLocalStorageSnapshot = () =>
  LEGACY_KEYS.reduce<Record<string, string | null>>((acc, key) => {
    acc[key] = window.localStorage.getItem(key)
    return acc
  }, {})

export const migrateLegacyDataIfNeeded = async (userId: string, timezone: string) => {
  const alreadyDone = await getMetaValue(migrationMetaKey(userId))
  if (alreadyDone === 'yes') {
    return { migratedTasks: 0, hadLegacyData: false }
  }

  const snapshot = getLegacyLocalStorageSnapshot()
  const hasLegacyData = Object.values(snapshot).some((value) => value !== null)

  if (hasLegacyData) {
    await putLegacyBackup({
      id: crypto.randomUUID(),
      user_id: userId,
      payload: snapshot,
      created_at: nowIso(),
    })
  }

  const existingTasks = await getAllUserTasks(userId)
  const legacyTasks = safeJsonParse<LegacyTask[]>(snapshot.fg_tasks ?? null, [])

  let migratedTasks = 0
  if (existingTasks.length === 0 && legacyTasks.length > 0) {
    for (const legacy of legacyTasks) {
      const record = toLegacyTaskRecord(legacy, userId, timezone)
      await putTaskLocal(record, true)
      migratedTasks += 1
    }
  }

  await setMetaValue(migrationMetaKey(userId), 'yes')
  return { migratedTasks, hadLegacyData: hasLegacyData }
}
