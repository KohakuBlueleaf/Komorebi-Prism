<template>
  <div class="min-w-0">
    <button ref="trigger" type="button" class="picker-trigger w-full flex items-center gap-2 px-2.5 h-8 rounded-lg bg-surface border border-solid border-line hover:border-ink-faint transition-colors text-left" :class="open ? '!border-iolite' : ''" aria-haspopup="dialog" :aria-expanded="open" @click="toggle">
      <span class="flex-1 min-w-0 truncate kt-text-body text-ink" :title="chosen?.name">{{ chosen?.name ?? "scene" }}</span>
      <span class="i-carbon-chevron-down text-ink-faint shrink-0 transition-transform" :class="open ? 'rotate-180' : ''" />
    </button>
    <p v-if="chosen" class="mt-1 kt-text-caption text-ink-faint font-mono truncate" :title="summary">{{ summary }}</p>

    <Teleport to="body">
      <div v-if="open" class="fixed inset-0 z-[2000]" @mousedown.self="close" @keydown="onKey">
        <div ref="panel" role="dialog" aria-label="Scenes" class="picker-panel card absolute flex flex-col shadow-2xl overflow-hidden" :style="placed">
          <div class="flex items-center gap-2 px-3 py-2 border-b border-solid border-line">
            <span class="i-carbon-search text-ink-faint shrink-0" />
            <input ref="filterBox" v-model="filter" type="text" class="flex-1 min-w-0 h-7 bg-transparent kt-text-body text-ink outline-none placeholder:text-ink-faint" placeholder="Filter by name, format, source file or layer" aria-label="Filter the scenes" />
            <span class="kt-text-caption text-ink-faint font-mono whitespace-nowrap">{{ rows.length }} of {{ scenes.length }}</span>
            <button class="btn-icon !w-7 !h-7 shrink-0" aria-label="Close the scenes" @click="close"><span class="i-carbon-close" /></button>
          </div>
          <div class="flex-1 min-h-0 overflow-auto">
            <table class="picker-table w-full border-collapse">
              <thead>
                <tr>
                  <th v-for="column in columns" :key="column.key" scope="col" class="sticky top-0 z-[1] bg-surface-alt px-2 py-1.5 border-b border-solid border-line kt-text-micro font-medium uppercase tracking-wider text-ink-muted whitespace-nowrap select-none" :class="[column.numeric ? 'text-right' : 'text-left', column.key === 'name' ? 'name-cell left-0 z-[2]' : '', column.sort ? 'cursor-pointer hover:text-ink' : '']" :title="column.help" :aria-sort="sortKey === column.key ? (descending ? 'descending' : 'ascending') : 'none'" @click="sortBy(column)">
                    {{ column.label }}
                    <span v-if="sortKey === column.key" class="i-carbon-arrow-down !inline-block align-[-2px] text-iolite dark:text-iolite-light transition-transform" :class="descending ? '' : 'rotate-180'" />
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(scene, index) in rows" :key="scene.name" class="picker-row cursor-pointer border-b border-solid border-line last:border-b-0" :class="[scene.name === modelValue ? 'is-chosen' : '', index === active ? 'is-active' : '']" @mouseenter="active = index" @click="pick(scene)">
                  <td class="name-cell left-0 px-2 py-1.5 align-middle">
                    <div class="flex items-center gap-1.5 min-w-0">
                      <span class="w-1 self-stretch rounded-full shrink-0" :class="scene.name === modelValue ? 'bg-iolite dark:bg-iolite-light' : 'bg-transparent'" />
                      <div class="min-w-0">
                        <div class="kt-text-body font-medium text-ink truncate" :title="scene.name">{{ scene.name }}</div>
                        <div class="kt-text-micro text-ink-faint font-mono truncate" :title="scene.source?.file">{{ sourceLine(scene) }}</div>
                      </div>
                    </div>
                  </td>
                  <td class="px-2 py-1.5 align-middle whitespace-nowrap">
                    <span class="chip-warm kt-text-micro !h-5">{{ scene.format }}</span>
                  </td>
                  <td v-for="key in COUNTS" :key="key" class="px-2 py-1.5 align-middle text-right whitespace-nowrap" :title="exact(scene[key])">
                    <span v-if="scene[key] !== null && scene[key] !== undefined" class="kt-text-caption font-mono text-ink">{{ compact(scene[key]) }}</span>
                    <span v-else class="kt-text-micro text-ink-faint">unknown</span>
                  </td>
                  <td class="px-2 py-1.5 align-middle text-right whitespace-nowrap" :title="`${exact(scene.textures)} textures, ${scene.texel_mib ?? 'unknown'} MiB of texels`">
                    <template v-if="scene.textures !== null && scene.textures !== undefined">
                      <span class="kt-text-caption font-mono text-ink">{{ compact(scene.textures) }}</span>
                      <span class="kt-text-micro font-mono text-ink-faint"> · {{ mib(scene.texel_mib) }}</span>
                    </template>
                    <span v-else class="kt-text-micro text-ink-faint">unknown</span>
                  </td>
                  <td class="px-2 py-1.5 align-middle">
                    <div v-if="scene.layers" class="flex gap-1">
                      <span v-for="layer in scene.layers" :key="layer" class="chip-warm kt-text-micro !h-5 !px-1.5">{{ layer }}</span>
                    </div>
                    <span v-else class="kt-text-micro text-ink-faint">unknown</span>
                  </td>
                  <td class="px-2 py-1.5 align-middle whitespace-nowrap kt-text-caption" :class="scene.lighting ? 'text-ink' : 'text-ink-faint'" :title="LIGHTING[scene.lighting ?? 'none']">{{ scene.generated ? "-" : (scene.lighting ?? "none") }}</td>
                  <td class="px-2 py-1.5 align-middle whitespace-nowrap kt-text-caption" :class="scene.far_field === 'present' ? 'text-ink' : 'text-ink-faint'" :title="FAR_FIELD[scene.far_field ?? 'none']">{{ scene.generated ? "-" : (scene.far_field ?? "none") }}</td>
                  <td class="px-2 py-1.5 align-middle kt-text-caption text-ink whitespace-nowrap">{{ scene.views.length ? scene.views.join(", ") : "its own" }}</td>
                  <td v-if="presetsSay" class="px-2 py-1.5 align-middle">
                    <div class="flex gap-1">
                      <span v-for="group in presetGroups(scene, pipelines)" :key="`${group.name}-${group.runs}`" class="chip-warm kt-text-micro !h-5 !px-1.5 whitespace-nowrap" :class="group.runs ? (group.members.includes(pipeline) ? '!border-iolite/40 !text-iolite dark:!text-iolite-light' : '!text-ink') : 'line-through opacity-60'" :title="group.runs ? `runs: ${group.members.join(', ')}` : `unavailable (${group.members.join(', ')}): ${group.reason}`">{{ group.name }}</span>
                    </div>
                  </td>
                </tr>
                <tr v-if="!rows.length">
                  <td :colspan="columns.length" class="px-3 py-4 kt-text-body text-ink-faint">No scene matches "{{ filter }}".</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="px-3 py-1.5 border-t border-solid border-line kt-text-micro text-ink-faint">Click a column to sort, a row to choose<template v-if="presetsSay">; a struck preset cannot run on the scene (its reason on hover)</template>. Unknown: the scene's files do not record it.</div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from "vue"

import { compact, exact, presetGroups } from "@/composables/sceneFacts"

// The scene menu: a button with the chosen scene, and a table of every scene the catalog
// lists (its format and source, triangles, objects, materials, textures, layers, lighting,
// far field, views, the presets that run on it), filtered and sorted by a column.
const props = defineProps({
  modelValue: { type: String, default: null },
  scenes: { type: Array, default: () => [] },
  pipelines: { type: Array, default: () => [] },
  pipeline: { type: String, default: null },
})
const emit = defineEmits(["pick"])

const COUNTS = ["triangles", "stored", "objects", "instances", "materials"]
const COLUMNS = [
  { key: "name", label: "Scene", sort: (s) => s.name, help: "the scene's name; under it the file it was made from" },
  { key: "format", label: "Format", sort: (s) => s.format, help: "glTF opened, glTF converted, the test scenes' own format (OBJ, Tungsten), or generated" },
  { key: "triangles", label: "Drawn", numeric: true, sort: (s) => s.triangles, help: "triangles drawn: the scene's mesh file" },
  { key: "stored", label: "Stored", numeric: true, sort: (s) => s.stored, help: "triangles stored in the source file, each mesh once" },
  { key: "objects", label: "Objects", numeric: true, sort: (s) => s.objects, help: "the source file's nodes that draw a mesh" },
  { key: "instances", label: "Instances", numeric: true, sort: (s) => s.instances, help: "the copies those nodes draw" },
  { key: "materials", label: "Materials", numeric: true, sort: (s) => s.materials, help: "materials of the materials file" },
  { key: "textures", label: "Textures", numeric: true, sort: (s) => s.texel_mib, help: "textures and the MiB of their texels (sorted by the MiB)" },
  { key: "layers", label: "Layers", sort: (s) => s.layers?.length, help: "the layers its triangles make: opaque, masked, glass" },
  { key: "lighting", label: "Lighting", sort: (s) => s.lighting, help: "the lighting file: sky visibility baked, open (1 everywhere), or none" },
  { key: "far_field", label: "Far field", sort: (s) => s.far_field, help: "the far field's files (indirect data and transport set): present, or none (gi then draws without its indirect term)" },
  { key: "views", label: "Views", sort: (s) => s.views.length, help: "the scene's views" },
  { key: "presets", label: "Presets", sort: (s) => runs(s), help: "the presets that run on it; a struck one cannot, its reason on hover" },
]
const LIGHTING = {
  baked: "the lighting file with the sky's visibility baked",
  open: "the lighting file with the sky's visibility 1 everywhere (not baked)",
  none: "no lighting file: the lit presets cannot run",
}
const FAR_FIELD = {
  present: "the indirect data and the transport set: gi draws its indirect term",
  none: "no indirect data or no transport set: gi draws without its indirect term",
}
const FORMAT_ORDER = ["glTF opened", "glTF converted", "", "generated"]
const GUTTER = 16
const WIDEST = 1480

const open = ref(false)
const filter = ref("")
const sortKey = ref(null)
const descending = ref(false)
const active = ref(-1)
const trigger = ref(null)
const filterBox = ref(null)
const placed = ref({})

const chosen = computed(() => props.scenes.find((one) => one.name === props.modelValue) ?? null)
const summary = computed(() => {
  const one = chosen.value
  if (!one) return ""
  const parts = [one.format, `${compact(one.triangles) ?? "unknown"} triangles`]
  if (one.textures !== null && one.textures !== undefined) parts.push(`${one.textures} textures`)
  if (one.source?.file) parts.push(one.source.file)
  return parts.join(" · ")
})

// unsorted, the artists' scenes first: opened, converted, the test scenes, generated
function formatRank(scene) {
  const at = FORMAT_ORDER.indexOf(scene.format)
  return at < 0 ? FORMAT_ORDER.indexOf("") : at
}

// the Presets column says something when some scene has a preset that cannot run or several families
const presetsSay = computed(() =>
  props.scenes.some((scene) => {
    const groups = presetGroups(scene, props.pipelines)
    return groups.length > 1 || !groups[0]?.runs
  }),
)
const columns = computed(() => (presetsSay.value ? COLUMNS : COLUMNS.filter((one) => one.key !== "presets")))

function runs(scene) {
  return props.pipelines.filter((one) => (scene.refusals?.[one.name] ?? null) === null).length
}

const rows = computed(() => {
  const words = filter.value.trim().toLowerCase()
  const kept = props.scenes.filter((one) => {
    if (!words) return true
    const text = [one.name, one.format, one.source?.file ?? "", ...(one.layers ?? [])].join(" ").toLowerCase()
    return words.split(/\s+/).every((word) => text.includes(word))
  })
  const column = columns.value.find((one) => one.key === sortKey.value)
  if (!column) return [...kept].sort((a, b) => formatRank(a) - formatRank(b))
  const sign = descending.value ? -1 : 1
  return [...kept].sort((a, b) => {
    const [x, y] = [column.sort(a), column.sort(b)]
    const [xu, yu] = [x === null || x === undefined, y === null || y === undefined]
    if (xu || yu) return xu === yu ? 0 : xu ? 1 : -1 // unknown last either way
    return sign * (typeof x === "string" ? x.localeCompare(y) : x - y)
  })
})

function sourceLine(scene) {
  if (!scene.source) return scene.generated ? "made by the reference" : "source not recorded"
  const size = scene.source.mib !== undefined ? ` · ${mib(scene.source.mib)}` : ""
  return `${scene.source.file}${size}`
}

function mib(value) {
  if (value === null || value === undefined) return "unknown"
  return value >= 1024 ? `${(value / 1024).toFixed(2)} GiB` : `${value.toFixed(value >= 10 ? 0 : 1)} MiB`
}

function sortBy(column) {
  if (!column.sort) return
  if (sortKey.value === column.key) descending.value = !descending.value
  else {
    sortKey.value = column.key
    descending.value = !!column.numeric
  }
}

function place() {
  const box = trigger.value?.getBoundingClientRect()
  if (!box) return
  const width = Math.min(WIDEST, window.innerWidth - 2 * GUTTER)
  const left = Math.max(GUTTER, Math.min(box.left, window.innerWidth - width - GUTTER))
  const below = window.innerHeight - box.bottom - GUTTER
  const top = below >= 320 ? box.bottom + 4 : GUTTER
  placed.value = { left: `${left}px`, top: `${top}px`, width: `${width}px`, maxHeight: `${window.innerHeight - top - GUTTER}px` }
}

async function toggle() {
  if (open.value) return close()
  place()
  open.value = true
  active.value = rows.value.findIndex((one) => one.name === props.modelValue)
  window.addEventListener("resize", place)
  await nextTick()
  filterBox.value?.focus()
}

function close() {
  open.value = false
  window.removeEventListener("resize", place)
}

function pick(scene) {
  emit("pick", scene.name)
  close()
}

function onKey(event) {
  if (event.key === "Escape") close()
  else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault()
    const step = event.key === "ArrowDown" ? 1 : -1
    active.value = Math.max(0, Math.min(rows.value.length - 1, active.value + step))
  } else if (event.key === "Enter" && rows.value[active.value]) pick(rows.value[active.value])
}

onBeforeUnmount(() => window.removeEventListener("resize", place))
</script>

<style scoped>
.picker-panel {
  min-height: 12rem;
}
.picker-table .name-cell {
  position: sticky;
  background: var(--color-surface);
  max-width: 16rem;
  min-width: 11rem;
}
.picker-table thead .name-cell {
  background: var(--color-surface-alt);
}
.picker-row.is-active td,
.picker-row.is-active .name-cell {
  background: var(--color-surface-alt);
}
.picker-row.is-chosen td,
.picker-row.is-chosen .name-cell {
  background: color-mix(in srgb, var(--kt-color-iolite) 8%, var(--color-surface));
}
</style>
