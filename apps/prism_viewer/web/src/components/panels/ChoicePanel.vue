<template>
  <PanelCard id="choice" title="Pipeline and scene" icon="i-carbon-data-share">
    <div class="flex flex-col gap-3 px-3 py-3">
      <label class="flex flex-col gap-1">
        <span class="flex items-center justify-between gap-2">
          <span class="field-label">Pipeline</span>
          <StatusMark v-if="!changed" :status="viewer.reloading ? 'loading' : viewer.status" :label="viewer.status === 'running' ? 'loaded' : ''" />
        </span>
        <el-select v-model="pipeline" :teleported="false">
          <el-option v-for="one in viewer.catalog.pipelines" :key="one.name" :label="one.name" :value="one.name" :disabled="!!refusal(one.name)" :title="refusal(one.name) ?? ''">
            <span class="flex items-center justify-between gap-2 min-w-0">
              <span>{{ one.name }}</span>
              <span v-if="refusal(one.name)" class="kt-text-micro text-ink-faint truncate">{{ refusal(one.name) }}</span>
            </span>
          </el-option>
        </el-select>
      </label>
      <button v-if="described" class="flex items-center gap-1 self-start kt-text-caption text-ink-muted hover:text-ink transition-colors" :aria-expanded="aboutOpen" @click="settings.toggleOpen('about')">
        <span class="i-carbon-chevron-down transition-transform" :class="aboutOpen ? '' : '-rotate-90'" />
        What it does and writes
      </button>
      <div v-if="described && aboutOpen" class="rounded-lg bg-surface-alt px-2.5 py-2 flex flex-col gap-1">
        <p class="kt-text-caption text-ink-muted">{{ described.about }}</p>
        <p v-for="written in described.writes" :key="written.slot" class="kt-text-caption text-ink">
          <span class="font-mono text-iolite dark:text-iolite-light">{{ written.slot }}</span>&nbsp;<span class="text-ink-muted">{{ written.what }}</span>
        </p>
      </div>
      <div class="flex flex-col gap-1 min-w-0">
        <span class="field-label">Scene</span>
        <ScenePicker :model-value="scene" :scenes="viewer.catalog.scenes" :pipelines="viewer.catalog.pipelines" :pipeline="pipeline" @pick="pickScene" />
      </div>
      <label class="flex flex-col gap-1 min-w-0">
        <span class="field-label">View</span>
        <el-select v-model="view" :teleported="false" :disabled="!views.length" :placeholder="views.length ? 'view' : 'its own'">
          <el-option v-for="one in views" :key="one" :label="one" :value="one" />
        </el-select>
      </label>
      <button v-if="changed" class="btn-primary" :disabled="viewer.reloading" @click="load">
        <span class="i-carbon-play-outline" />
        Load
      </button>
    </div>
    <div class="flex flex-col gap-2 px-3 py-3 border-t border-solid border-line">
      <div class="flex items-center justify-between">
        <span class="field-label">Frame size (pixels)</span>
        <span v-if="viewer.state?.capacity" class="kt-text-caption font-mono text-taaffeite-shadow dark:text-taaffeite-light" title="the tiles the loaded tables hold">{{ viewer.state.capacity.tiles }} tiles{{ viewer.state.capacity.wide ? " · wide" : "" }}</span>
      </div>
      <div class="flex items-center gap-2">
        <el-input-number v-model="width" :min="1" :step="32" :controls="false" class="!w-0 flex-1" aria-label="width" @keyup.enter="resize" />
        <span class="text-ink-faint">x</span>
        <el-input-number v-model="height" :min="1" :step="32" :controls="false" class="!w-0 flex-1" aria-label="height" @keyup.enter="resize" />
        <button v-if="sized" class="btn-primary !px-3" @click="resize">Apply</button>
      </div>
      <div class="flex flex-wrap gap-1.5">
        <button v-for="one in SIZES" :key="one.join('x')" class="chip-warm hover:text-ink hover:border-iolite/40 transition-colors font-mono" @click="pick(one)">{{ one[0] }} x {{ one[1] }}</button>
      </div>
    </div>
  </PanelCard>
</template>

<script setup>
import { computed, ref, watch } from "vue"

import PanelCard from "@/components/panels/PanelCard.vue"
import ScenePicker from "@/components/panels/ScenePicker.vue"
import StatusMark from "@/components/shell/StatusMark.vue"
import { bestPreset } from "@/composables/sceneFacts"
import { useSettingsStore } from "@/stores/settings"
import { useViewerStore } from "@/stores/viewer"

const SIZES = [
  [1280, 720],
  [1024, 1024],
  [1920, 1080],
  [720, 1280],
]

const viewer = useViewerStore()
const settings = useSettingsStore()
const aboutOpen = computed(() => !!settings.opened.about)
const pipeline = ref(null)
const scene = ref(null)
const view = ref(null)
const width = ref(null)
const height = ref(null)

const choice = computed(() => viewer.state?.choice ?? [null, null, null])
watch(
  choice,
  (now, before) => {
    if (before && now.join() === before.join()) return
    ;[pipeline.value, scene.value, view.value] = now
  },
  { immediate: true },
)
const size = computed(() => viewer.state?.size ?? viewer.state?.size_asked ?? null)
watch(
  () => size.value?.join("x"),
  () => {
    if (size.value) [width.value, height.value] = size.value
  },
  { immediate: true },
)

const described = computed(() => viewer.catalog.pipelines.find((one) => one.name === pipeline.value))
const chosenScene = computed(() => viewer.catalog.scenes.find((one) => one.name === scene.value) ?? null)
const views = computed(() => chosenScene.value?.views ?? [])
const changed = computed(() => [pipeline.value, scene.value, view.value].join() !== choice.value.join())
const sized = computed(() => width.value > 0 && height.value > 0 && size.value && (width.value !== size.value[0] || height.value !== size.value[1]))

// why a preset cannot run on the chosen scene (the catalog's), null when it can
function refusal(name) {
  return chosenScene.value?.refusals?.[name] ?? null
}
// a scene the chosen preset cannot run on switches to the best preset that can, and says so
function pickScene(name) {
  scene.value = name
  pickView()
  const reason = refusal(pipeline.value)
  if (reason === null) return
  const best = bestPreset(chosenScene.value, viewer.catalog.pipelines, pipeline.value)
  viewer.noted("switch", `${pipeline.value} cannot run on ${name} (${reason}): ${best ? `switched to ${best}` : "no preset can"}`)
  if (best) pipeline.value = best
}
function pickView() {
  view.value = views.value[0] ?? null
}
function load() {
  viewer.select(pipeline.value, scene.value, view.value)
}
function resize() {
  if (sized.value) viewer.resize(width.value, height.value)
}
function pick(one) {
  ;[width.value, height.value] = one
  resize()
}
</script>
