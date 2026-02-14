const read = (name: string) => {
  const value = import.meta.env[name] as string | undefined
  return value?.trim() ?? ''
}

export const env = {
  supabaseUrl: read('VITE_SUPABASE_URL'),
  supabaseAnonKey: read('VITE_SUPABASE_ANON_KEY'),
  vapidPublicKey: read('VITE_VAPID_PUBLIC_KEY'),
}

export const missingClientEnv = (['VITE_SUPABASE_URL', 'VITE_SUPABASE_ANON_KEY'] as const).filter(
  (name) => !read(name),
)

export const hasSupabaseClientConfig = missingClientEnv.length === 0
