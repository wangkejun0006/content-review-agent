export function generateSecurePassword(): string {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
  const values = new Uint32Array(14)
  crypto.getRandomValues(values)
  const random = Array.from(values, (value) => alphabet[value % alphabet.length]).join('')
  return `Paper Orbit-${random}9!`
}
