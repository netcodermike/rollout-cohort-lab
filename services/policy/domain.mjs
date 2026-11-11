export async function operation({ flag, percent, subjects, overrides = {} }, cohorts) {
  if (!Number.isFinite(percent) || percent < 0 || percent > 100) throw new TypeError('Invalid rollout percent')
  if (!overrides || typeof overrides !== 'object' || Array.isArray(overrides) ||
      Object.values(overrides).some(value => typeof value !== 'boolean')) throw new TypeError('Invalid overrides')
  const { buckets } = await cohorts({ flag, subjects })
  const threshold = Math.round(percent * 100)
  const enabled = []
  const disabled = []
  for (const subject of Object.keys(buckets).sort()) {
    const active = Object.hasOwn(overrides, subject) ? overrides[subject] : buckets[subject] < threshold
    ;(active ? enabled : disabled).push(subject)
  }
  return { threshold, enabled, disabled, buckets }
}
