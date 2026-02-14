import { supabase } from './supabase'
import {
  bumpQueueRetry,
  db,
  getMetaValue,
  getPendingQueue,
  markQueueProcessed,
  setMetaValue,
  upsertTasksFromRemote,
} from './db'
import type { RealtimeChannel } from '@supabase/supabase-js'
import type { TaskRecord } from '../types'

const lastPullKey = (userId: string) => `tasks_last_pull_${userId}`

const normalizeTaskRecord = (raw: Partial<TaskRecord>): TaskRecord => ({
  id: raw.id ?? crypto.randomUUID(),
  user_id: raw.user_id ?? '',
  title: raw.title ?? '',
  status: raw.status === 'done' ? 'done' : 'todo',
  priority:
    raw.priority === 'high' || raw.priority === 'medium' || raw.priority === 'normal'
      ? raw.priority
      : 'normal',
  tags: Array.isArray(raw.tags) ? raw.tags : [],
  scheduled_date: raw.scheduled_date ?? null,
  due_time: raw.due_time ?? null,
  estimate_minutes: raw.estimate_minutes ?? null,
  energy: raw.energy ?? null,
  created_at: raw.created_at ?? new Date().toISOString(),
  updated_at: raw.updated_at ?? new Date().toISOString(),
  completed_at: raw.completed_at ?? null,
  original_scheduled_date: raw.original_scheduled_date ?? null,
  timezone: raw.timezone ?? 'UTC',
  top3_slot: raw.top3_slot ?? null,
  last_notified_at: raw.last_notified_at ?? null,
})

const flushQueue = async (userId: string) => {
  const pending = await getPendingQueue(userId)

  for (const operation of pending) {
    try {
      if (operation.type === 'upsert_task') {
        const task = normalizeTaskRecord(operation.payload as TaskRecord)
        const { error } = await supabase.from('tasks').upsert(task, { onConflict: 'id' })
        if (error) {
          throw error
        }
      }

      if (operation.type === 'delete_task') {
        const { error } = await supabase
          .from('tasks')
          .delete()
          .eq('id', operation.task_id)
          .eq('user_id', operation.user_id)

        if (error) {
          throw error
        }
      }

      await markQueueProcessed(operation.id)
    } catch {
      await bumpQueueRetry(operation.id)
      break
    }
  }
}

const pullUpdates = async (userId: string) => {
  const since = (await getMetaValue(lastPullKey(userId))) ?? '1970-01-01T00:00:00.000Z'
  const { data, error } = await supabase
    .from('tasks')
    .select('*')
    .eq('user_id', userId)
    .gt('updated_at', since)
    .order('updated_at', { ascending: true })
    .limit(1000)

  if (error) {
    throw error
  }

  const normalized = (data ?? []).map((row) => normalizeTaskRecord(row as TaskRecord))
  await upsertTasksFromRemote(normalized)

  const latest = normalized.at(-1)?.updated_at
  if (latest) {
    await setMetaValue(lastPullKey(userId), latest)
  }
}

export const syncNow = async (userId: string) => {
  await flushQueue(userId)
  await pullUpdates(userId)
}

export const subscribeTaskChanges = (
  userId: string,
  onTaskChanged?: (taskId: string | null) => void,
): (() => void) => {
  const channel: RealtimeChannel = supabase
    .channel(`tasks-realtime-${userId}`)
    .on(
      'postgres_changes',
      {
        event: '*',
        schema: 'public',
        table: 'tasks',
        filter: `user_id=eq.${userId}`,
      },
      async (payload) => {
        if (payload.eventType === 'DELETE') {
          const oldRow = payload.old as Partial<TaskRecord>
          if (oldRow.id) {
            await db.tasks.delete(oldRow.id)
            onTaskChanged?.(oldRow.id)
          }
          return
        }

        if (payload.new) {
          const task = normalizeTaskRecord(payload.new as TaskRecord)
          await upsertTasksFromRemote([task])
          onTaskChanged?.(task.id)
        }
      },
    )
    .subscribe()

  return () => {
    void supabase.removeChannel(channel)
  }
}
