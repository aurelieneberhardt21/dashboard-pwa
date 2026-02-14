export type TaskStatus = 'todo' | 'done'
export type TaskPriority = 'high' | 'medium' | 'normal'
export type EnergyLevel = 'low' | 'medium' | 'high' | 'deep' | null

export type TaskRecord = {
  id: string
  user_id: string
  title: string
  status: TaskStatus
  priority: TaskPriority
  tags: string[]
  scheduled_date: string | null
  due_time: string | null
  estimate_minutes: number | null
  energy: EnergyLevel
  created_at: string
  updated_at: string
  completed_at: string | null
  original_scheduled_date: string | null
  timezone: string
  top3_slot: number | null
  last_notified_at: string | null
}

export type TaskInsert = Omit<TaskRecord, 'created_at' | 'updated_at' | 'last_notified_at'> & {
  created_at?: string
  updated_at?: string
  last_notified_at?: string | null
}

export type LegacyTask = {
  id: number | string
  text: string
  completed: boolean
  date?: string
  priority?: 'high' | 'medium' | 'normal'
  migrated?: boolean
}

export type QueueOperation = {
  id: string
  user_id: string
  type: 'upsert_task' | 'delete_task'
  task_id: string
  payload: TaskRecord | { id: string }
  created_at: string
  retries: number
}

export type MetaRecord = {
  key: string
  value: string
}

export type LegacyBackupRecord = {
  id: string
  user_id: string
  payload: Record<string, string | null>
  created_at: string
}

export type PushSubscriptionPayload = {
  endpoint: string
  p256dh: string
  auth: string
  user_agent: string | null
}

export type GymExerciseRecord = {
  id: string
  name: string
  sets: number | null
  reps: number | null
  weight_kg: number | null
}

export type GymSessionRecord = {
  id: string
  user_id: string
  date: string
  session_name: string
  duration_minutes: number | null
  effort_1_to_5: number | null
  notes: string
  exercises: GymExerciseRecord[]
  created_at: string
  updated_at: string
}

export type ThesisLogRecord = {
  id: string
  user_id: string
  date: string
  focus_minutes: number
  words_written: number
  note: string
  created_at: string
  updated_at: string
}
