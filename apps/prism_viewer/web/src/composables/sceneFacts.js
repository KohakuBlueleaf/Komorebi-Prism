// A scene's facts as the scene menu shows them, and the preset a scene falls back to.

// A count read at a glance: 1.25 M, 498 k, 893; null when the scene's files lack it.
export function compact(n) {
  if (n === null || n === undefined) return null
  if (n >= 1e6) return `${(n / 1e6).toFixed(n >= 1e7 ? 1 : 2)} M`
  if (n >= 1e4) return `${Math.round(n / 1e3)} k`
  return n.toLocaleString("en-US")
}

export function exact(n) {
  return n === null || n === undefined ? "unknown" : n.toLocaleString("en-US")
}

// A preset's family and its form: "gi_threads" -> ["gi", "_threads"].
function family(name) {
  const at = name.indexOf("_")
  return at < 0 ? [name, ""] : [name.slice(0, at), name.slice(at)]
}

// The presets of a scene grouped by family and by whether they run on it, in the
// catalog's order: { name, runs, members, reason }.
export function presetGroups(scene, pipelines) {
  const groups = []
  for (const one of pipelines) {
    const [base] = family(one.name)
    const reason = scene.refusals?.[one.name] ?? null
    const runs = reason === null
    const found = groups.find(
      (group) => group.name === base && group.runs === runs && group.reason === reason,
    )
    if (found) found.members.push(one.name)
    else groups.push({ name: base, runs, reason, members: [one.name], weight: weight(one) })
  }
  return groups.sort((a, b) => a.weight - b.weight)
}

// What a preset asks of a scene: the more it reads, the more it draws.
function weight(one) {
  return (one.files?.length ?? 0) + (one.inputs?.length ?? 0)
}

// The preset that can run on `scene` drawing the most, of `current`'s form when one is.
export function bestPreset(scene, pipelines, current) {
  const runs = pipelines.filter((one) => (scene.refusals?.[one.name] ?? null) === null)
  if (!runs.length) return null
  const [, form] = family(current ?? "")
  const sameForm = runs.filter((one) => family(one.name)[1] === form)
  const pool = sameForm.length ? sameForm : runs
  return pool.reduce((best, one) => (weight(one) > weight(best) ? one : best)).name
}
