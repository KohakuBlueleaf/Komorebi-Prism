<template>
  <div class="card overflow-hidden flex flex-col min-w-0 h-full">
    <div ref="surface" tabindex="0" class="stage relative flex-1 min-h-0 bg-stage outline-none select-none touch-none cursor-grab active:cursor-grabbing focus:ring-2 focus:ring-iolite focus:ring-inset" :style="aspect" aria-label="The frame: click, then W A S D Q E to move, drag to turn, the wheel for the field of view" @pointerdown="input.pointerdown" @pointermove="input.pointermove" @pointerup="input.pointerup" @pointercancel="input.pointerup" @wheel="input.wheel" @focus="focused = true" @blur="focused = false">
      <img ref="image" :src="stream.src.value" alt="the card's frame" draggable="false" class="absolute inset-0 w-full h-full object-contain pointer-events-none" @error="stream.failed" @load="stream.loaded" />
      <div v-if="overlay" class="absolute inset-0 flex items-center justify-center p-4 bg-stage/70">
        <div class="flex items-center gap-2 px-3 py-2 rounded-lg bg-surface border border-solid border-line kt-text-body max-w-full" :class="overlay.tone">
          <span :class="overlay.icon" />
          <span class="break-words min-w-0">{{ overlay.text }}</span>
        </div>
      </div>
    </div>
    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 border-t border-solid border-line kt-text-caption min-w-0">
      <span class="font-mono text-taaffeite-shadow dark:text-taaffeite-light">{{ sizeText }}</span>
      <span v-if="fovText" class="font-mono text-ink-muted" title="the field of view">{{ fovText }}</span>
      <span class="font-mono text-ink-muted">frame {{ viewer.state?.frame ?? 0 }}</span>
      <span class="font-mono text-aquamarine-shadow dark:text-aquamarine">{{ fpsText }}</span>
      <span v-if="focused && poseText" class="font-mono text-ink-faint truncate min-w-0 flex-1 text-right" :title="poseText">{{ poseText }}</span>
      <span v-else class="text-ink-muted truncate min-w-0 flex-1 text-right">click the frame to steer</span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue"

import { usePose } from "@/composables/usePose"
import { useStream } from "@/composables/useStream"
import { useViewerStore } from "@/stores/viewer"

const viewer = useViewerStore()
const surface = ref(null)
const image = ref(null)
const focused = ref(false)
const stream = useStream()

// The width the frame is shown at inside the letterbox.
function shownWidth() {
  const element = image.value
  if (!element) return 1
  const { naturalWidth: w, naturalHeight: h, clientWidth, clientHeight } = element
  return w && h ? Math.min(clientWidth, (clientHeight * w) / h) : clientWidth
}

const input = usePose(viewer, surface, shownWidth, () => focused.value)

const aspect = computed(() => {
  const size = viewer.size
  return size ? { "--frame-aspect": `${size[0]} / ${size[1]}` } : {}
})
const sizeText = computed(() => (viewer.size ? `${viewer.size[0]} x ${viewer.size[1]}` : "no frame yet"))
const fovText = computed(() => {
  const fov = input.pose.value?.fov
  return Number.isFinite(fov) ? `fov ${fov.toFixed(1)}\u00b0` : ""
})
const fpsText = computed(() => `${(viewer.state?.fps ?? 0).toFixed(0)} / s`)
const poseText = computed(() => {
  const pose = input.pose.value
  if (!pose) return ""
  const at = pose.position.map((x) => x.toFixed(2)).join(", ")
  const deg = (r) => ((r * 180) / Math.PI).toFixed(0)
  return `at ${at} · yaw ${deg(pose.yaw)} · pitch ${deg(pose.pitch)}`
})
const overlay = computed(() => {
  if (viewer.status === "unreachable") return { icon: "i-carbon-plug", tone: "text-coral", text: "The server does not answer." }
  if (viewer.status === "error") return { icon: "i-carbon-error", tone: "text-coral", text: `${viewer.state?.error}. Choose and load again.` }
  if (viewer.reloading) return { icon: "i-carbon-renew kohaku-pulse", tone: "text-ink", text: `Loading ${viewer.state?.choice?.filter(Boolean).join(" / ")}` }
  if (stream.broken.value) return { icon: "i-carbon-renew kohaku-pulse", tone: "text-ink-muted", text: "Opening the stream again" }
  return null
})
</script>

<style scoped>
.stage {
  aspect-ratio: var(--frame-aspect, 1 / 1);
}
</style>
