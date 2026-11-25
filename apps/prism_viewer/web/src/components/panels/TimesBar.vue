<template>
  <div class="flex flex-col gap-2">
    <div class="flex h-3 rounded-full overflow-hidden bg-surface-alt" role="img" :aria-label="label">
      <div v-for="part in parts" :key="part.name" class="h-full transition-all duration-300" :class="part.tone.bar" :style="{ width: `${part.share}%` }" :title="`${part.name} ${part.ms.toFixed(2)} ms`" />
    </div>
    <ul class="list-none grid grid-cols-[auto_1fr_auto] gap-x-2 gap-y-1 items-center">
      <template v-for="part in parts" :key="part.name">
        <li class="w-2.5 h-2.5 rounded-sm" :class="part.tone.bar" />
        <li class="kt-text-body text-ink-muted truncate">
          {{ part.name }} <span class="kt-text-caption text-ink-faint">{{ part.tone.where }}</span>
        </li>
        <li class="num-value text-right" :class="part.tone.text">{{ part.ms.toFixed(2) }} ms</li>
      </template>
    </ul>
  </div>
</template>

<script setup>
import { computed } from "vue"

// The last frame's parts by name as a stacked bar and its legend; the first part is the
// card's command (sapphire), the others the host's work (amber).
const props = defineProps({
  times: { type: Object, default: () => ({}) },
})

const CARD = { bar: "bg-sapphire dark:bg-sapphire-light", text: "text-sapphire dark:text-sapphire-light", where: "card, as the host waits" }
const HOST = [
  { bar: "bg-amber", text: "text-amber-shadow dark:text-amber", where: "host" },
  { bar: "bg-amber-light dark:bg-amber-shadow", text: "text-amber-shadow dark:text-amber", where: "host" },
]

const parts = computed(() => {
  const entries = Object.entries(props.times)
  const total = entries.reduce((sum, [, ms]) => sum + ms, 0) || 1
  return entries.map(([name, ms], index) => ({
    name,
    ms,
    share: (100 * ms) / total,
    tone: index === 0 ? CARD : HOST[(index - 1) % HOST.length],
  }))
})
const label = computed(() => parts.value.map((p) => `${p.name} ${p.ms.toFixed(1)} ms`).join(", "))
</script>
