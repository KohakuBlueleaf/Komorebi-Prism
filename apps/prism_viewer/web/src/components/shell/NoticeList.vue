<template>
  <PanelCard id="notices" title="Notices" icon="i-carbon-notification">
    <template #aside>
      <button v-if="shown.length" class="px-2 h-6 rounded-md normal-case tracking-normal kt-text-caption text-ink-muted hover:text-ink hover:bg-surface-alt transition-colors" @click="viewer.clearNotices()">clear</button>
    </template>
    <div v-if="!shown.length" class="px-3 py-3 kt-text-body text-ink-faint">Nothing yet: loads, reloads, lists grown live, refusals and applied changes appear here.</div>
    <ul v-else class="list-none flex flex-col">
      <li v-for="notice in shown" :key="notice.serial" class="flex items-start gap-2 px-3 py-2 border-b border-solid border-line last:border-b-0">
        <span class="mt-0.5 shrink-0" :class="KINDS[notice.kind]?.icon ?? 'i-carbon-information text-ink-faint'" />
        <div class="min-w-0 flex-1">
          <div class="kt-text-body text-ink break-words">{{ notice.text }}</div>
          <div class="kt-text-caption text-ink-faint font-mono">
            {{ KINDS[notice.kind]?.label ?? notice.kind }}<template v-if="notice.seconds !== null"> · {{ notice.seconds.toFixed(2) }} s</template> · {{ clock(notice.at) }}
          </div>
        </div>
      </li>
    </ul>
  </PanelCard>
</template>

<script setup>
import { computed } from "vue"

import PanelCard from "@/components/panels/PanelCard.vue"
import { useViewerStore } from "@/stores/viewer"

const SHOWN = 5
const KINDS = {
  reload: { label: "load", icon: "i-carbon-renew text-sapphire dark:text-sapphire-light" },
  applied: { label: "applied", icon: "i-carbon-checkmark-outline text-sage" },
  grown: { label: "grown live", icon: "i-carbon-maximize text-sage" },
  switch: { label: "switched", icon: "i-carbon-arrows-horizontal text-iolite dark:text-iolite-light" },
  refusal: { label: "refused", icon: "i-carbon-warning-alt text-coral" },
  error: { label: "failure", icon: "i-carbon-error text-coral" },
}

const viewer = useViewerStore()
const shown = computed(() => [...viewer.notices].reverse().slice(0, SHOWN))

function clock(seconds) {
  return new Date(seconds * 1000).toLocaleTimeString([], { hour12: false })
}
</script>
