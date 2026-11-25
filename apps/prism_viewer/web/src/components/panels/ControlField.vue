<template>
  <div class="flex flex-col gap-1.5 px-3 py-2.5">
    <div class="flex items-center gap-3">
      <div class="min-w-0 flex-1">
        <div class="kt-text-body font-medium text-ink">{{ control.label }}</div>
        <div class="kt-text-caption text-ink-faint font-mono truncate" :title="control.name">{{ control.name }}</div>
      </div>
      <el-switch v-if="control.kind === 'toggle'" :model-value="value" :aria-label="control.label" :loading="waiting" @change="send" />
      <el-select v-else-if="control.kind === 'choice'" :model-value="value" size="small" class="!w-32 shrink-0" :aria-label="control.label" :loading="waiting" @change="send">
        <el-option v-for="[choice, label] in control.choices" :key="String(choice)" :label="label" :value="choice" />
      </el-select>
      <el-input-number v-else-if="control.kind === 'count'" :model-value="value" size="small" class="!w-28 shrink-0" :min="control.limits[0]" :max="control.limits[1] ?? Infinity" :step="1" step-strictly :disabled="waiting" :aria-label="control.label" @change="send" />
      <span v-else class="num-value shrink-0 text-iolite dark:text-iolite-light">{{ shown }}</span>
    </div>
    <el-slider v-if="control.kind === 'range'" :model-value="toSlider(value)" :min="toSlider(control.limits[0])" :max="toSlider(control.limits[1])" :step="step(control.limits)" :show-tooltip="false" :aria-label="control.label" @input="(one) => (draft = fromSlider(one))" @change="(one) => send(fromSlider(one))" />
    <template v-if="control.kind === 'direction'">
      <div v-for="(angle, index) in ANGLES" :key="angle" class="flex items-center gap-3">
        <span class="field-label w-16 shrink-0">{{ angle }}</span>
        <el-slider class="flex-1 min-w-0" :model-value="value[index]" :min="control.limits[index][0]" :max="control.limits[index][1]" :step="step(control.limits[index])" :show-tooltip="false" :aria-label="`${control.label} ${angle}`" @input="(one) => (draft = withAngle(index, one))" @change="(one) => send(withAngle(index, one))" />
        <span class="kt-text-micro text-ink-faint font-mono w-12 shrink-0 text-right whitespace-nowrap">{{ control.limits[index][0] }}-{{ control.limits[index][1] }}</span>
      </div>
    </template>
    <p v-if="control.kind === 'count'" class="kt-text-caption text-ink-faint font-mono">{{ control.limits[1] == null ? `${control.limits[0]} or more` : `${control.limits[0]} to ${control.limits[1]}` }}</p>
    <p v-if="control.help" class="kt-text-caption text-ink-muted">{{ control.help }}</p>
  </div>
</template>

<script setup>
import { computed, ref } from "vue"

import { useViewerStore } from "@/stores/viewer"

// One control of a host, drawn by its kind: toggle, range, count, choice (by its labels) or
// direction (two angles, each its own limits); a count's most may be null (no most). While a value is sent the control shows it;
// once the server answers it shows the server's value again (a refusal: the one before).
const props = defineProps({
  control: { type: Object, required: true },
})

const ANGLES = ["azimuth", "elevation"]
const LOG_SPAN = 100 // a positive range whose most is this many times its least slides by the logarithm
const STEPS = 200 // a slider's steps over its limits

const viewer = useViewerStore()
const draft = ref(null)
const waiting = ref(false)
const value = computed(() => draft.value ?? props.control.value)

const logScale = computed(() => {
  const [least, most] = props.control.limits ?? [0, 1]
  return props.control.kind === "range" && least > 0 && most / least >= LOG_SPAN
})
const toSlider = (one) => (logScale.value ? Math.log10(one) : one)
const fromSlider = (one) => (logScale.value ? Number((10 ** one).toPrecision(4)) : one)
const step = ([least, most]) => (toSlider(most) - toSlider(least)) / STEPS
const shown = computed(() => {
  const { kind, unit } = props.control
  const text = kind === "direction" ? value.value.map((one) => one.toFixed(1)).join(", ") : Number(value.value).toFixed(2)
  return unit ? `${text} ${unit}` : text
})

function withAngle(index, one) {
  const next = [...value.value]
  next[index] = one
  return next
}

async function send(one) {
  draft.value = one
  waiting.value = true
  try {
    await viewer.setControl(props.control.name, one)
  } finally {
    waiting.value = false
    draft.value = null
  }
}
</script>
