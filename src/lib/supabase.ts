import { createClient } from '@supabase/supabase-js'
import { env, hasSupabaseClientConfig, missingClientEnv } from './env'

const supabaseUrl = env.supabaseUrl || 'https://example.supabase.co'
const supabaseAnonKey = env.supabaseAnonKey || 'public-anon-key-placeholder'

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
})

export { hasSupabaseClientConfig, missingClientEnv }

export const authRedirectTo = () => {
  const base = window.location.origin
  return `${base}/`
}
