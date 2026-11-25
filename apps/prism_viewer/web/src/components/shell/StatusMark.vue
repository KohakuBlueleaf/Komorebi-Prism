<template>
  <span class="inline-flex items-center gap-1.5 kt-text-caption font-medium" :class="tone.text" :title="title">
    <span class="inline-block w-2 h-2 rounded-full" :class="tone.dot" />
    <span>{{ label }}</span>
  </span>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
  status: { type: String, default: "loading" },
  title: { type: String, default: "" },
  label: { type: String, default: "" },
})

const TONES = {
  running: { dot: "bg-sage", text: "text-sage-shadow dark:text-sage-light" },
  loading: { dot: "bg-ink-faint kohaku-pulse", text: "text-ink-muted" },
  error: { dot: "bg-coral", text: "text-coral-shadow dark:text-coral-light" },
  unreachable: { dot: "bg-coral", text: "text-coral-shadow dark:text-coral-light" },
}

const tone = computed(() => TONES[props.status] ?? TONES.loading)
const label = computed(() => props.label || (props.status === "unreachable" ? "server unreachable" : props.status))
</script>
