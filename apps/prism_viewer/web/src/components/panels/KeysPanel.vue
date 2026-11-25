<template>
  <PanelCard id="keys" title="Camera" icon="i-carbon-keyboard">
    <dl class="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-1.5 px-3 py-3">
      <template v-for="row in ROWS" :key="row.what">
        <dt class="flex gap-1">
          <kbd v-for="key in row.keys" :key="key" class="inline-flex items-center justify-center min-w-6 h-6 px-1.5 rounded-md border border-solid border-line bg-surface-alt font-mono kt-text-caption text-ink">{{ key }}</kbd>
        </dt>
        <dd class="kt-text-body text-ink-muted">{{ row.what }}</dd>
      </template>
    </dl>
    <div class="flex flex-col gap-1.5 px-3 py-2.5 border-t border-solid border-line">
      <div class="flex items-center gap-3">
        <div class="min-w-0 flex-1 kt-text-body font-medium text-ink">Field of view</div>
        <span class="num-value shrink-0 text-iolite dark:text-iolite-light">{{ fovText }}</span>
        <button class="px-2 h-6 rounded-md kt-text-caption text-ink-muted hover:text-ink hover:bg-surface-alt transition-colors disabled:opacity-40 disabled:pointer-events-none" :disabled="!canReset" title="the view's own field of view" @click="viewer.setFov(viewer.ownFov)">reset</button>
      </div>
      <p class="kt-text-caption text-ink-faint font-mono">{{ least }} to {{ most }} degrees across the wider side; the view's {{ ownText }}</p>
    </div>
  </PanelCard>
</template>

<script setup>
import { computed } from "vue"

import PanelCard from "@/components/panels/PanelCard.vue"
import { useViewerStore } from "@/stores/viewer"

const ROWS = [
  { keys: ["W", "S"], what: "forward, back along the view (a tenth of the scene a second)" },
  { keys: ["A", "D"], what: "left, right" },
  { keys: ["Q", "E"], what: "down, up" },
  { keys: ["shift"], what: "five times faster" },
  { keys: ["drag"], what: "turn (yaw, pitch)" },
  { keys: ["wheel"], what: "over the frame: narrow, widen the field of view" },
]

const viewer = useViewerStore()
const least = computed(() => viewer.fovLimits[0])
const most = computed(() => viewer.fovLimits[1])
const fov = computed(() => viewer.pose?.fov ?? null)
const degrees = (one) => (Number.isFinite(one) ? `${one.toFixed(1)}°` : "-")
const fovText = computed(() => degrees(fov.value))
const ownText = computed(() => degrees(viewer.ownFov))
const canReset = computed(() => fov.value !== null && viewer.ownFov !== null && fov.value !== viewer.ownFov)
</script>
