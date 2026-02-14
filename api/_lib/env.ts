export const requiredEnv = (name: string) => {
  const value = process.env[name]
  if (!value) {
    throw new Error(`Missing env var ${name}`)
  }
  return value
}

export const optionalEnv = (name: string) => process.env[name]
