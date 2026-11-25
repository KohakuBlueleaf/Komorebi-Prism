<template>
  <div v-if="card" class="flex flex-col gap-1.5">
    <span class="kt-text-caption text-ink-muted">Median of the last {{ card.frames }} frames of the run before ({{ card.why }})</span>
    <table class="w-full border-collapse">
      <tbody>
        <tr v-for="row in shown" :key="row.name" class="border-b border-line last:border-b-0">
          <td class="py-1 pr-2 kt-text-caption font-mono whitespace-nowrap" :class="row.whole ? 'text-ink font-medium' : 'text-ink-muted'">{{ row.name }}</td>
          <td class="py-1 w-full">
            <div class="h-1.5 rounded-full bg-sapphire/80 dark:bg-sapphire-light/80" :style="{ width: `${row.share}%` }" />
          </td>
          <td class="py-1 pl-2 kt-text-caption font-mono text-right whitespace-nowrap" :class="row.whole ? 'text-sapphire dark:text-sapphire-light font-medium' : 'text-ink'">{{ row.ms.toFixed(3) }}</td>
        </tr>
      </tbody>
    </table>
    <button v-if="small.length" class="self-start kt-text-caption text-ink-muted hover:text-iolite transition-colors" @click="all = !all">
      {{ all ? "Fewer parts" : `${small.length} more parts, each under ${SMALL_SHARE}% of the frame` }}
    </button>
  </div>
  <p v-else class="kt-text-caption text-ink-faint">The card's own times are read when a run stops: they appear after the first reload or a new load.</p>
</template>

<script setup>
import { computed, ref } from "vue"

// The card's times by name (ms, medians of a stopped run); the largest is the whole frame,
// the parts under SMALL_SHARE of it folded until asked for.
const props = defineProps({
  card: { type: Object, default: null },
})

const SMALL_SHARE = 5
const all = ref(false)

const rows = computed(() => {
  const entries = Object.entries(props.card?.ms ?? {}).filter(([, ms]) => ms > 0)
  const most = Math.max(...entries.map(([, ms]) => ms), 1e-9)
  return entries.map(([name, ms]) => ({ name, ms, share: (100 * ms) / most, whole: ms === most }))
})
const small = computed(() => rows.value.filter((row) => row.share < SMALL_SHARE))
const shown = computed(() => (all.value ? rows.value : rows.value.filter((row) => row.share >= SMALL_SHARE)))
</script>
