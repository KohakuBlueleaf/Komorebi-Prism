<template>
  <header class="sticky top-0 z-10 flex items-center gap-3 px-3 sm:px-4 h-12 border-b border-solid border-line bg-surface shrink-0 min-w-0">
    <div class="w-7 h-7 rounded-full shrink-0 bg-gradient-to-br from-amber via-iolite-light to-iolite" aria-hidden="true" />
    <div class="flex items-baseline gap-2 min-w-0">
      <span class="kt-text-emphasis font-semibold text-ink whitespace-nowrap">Prism viewer</span>
      <span v-if="loaded" class="hidden sm:inline kt-text-body text-ink-muted truncate">{{ where }}</span>
    </div>
    <span v-if="loaded" class="chip-iolite font-mono shrink-0" :title="loaded.about">{{ loaded.name }}</span>
    <div class="flex-1" />
    <StatusMark :status="viewer.status" :title="viewer.state?.error || ''" />
    <ThemeSwitch />
  </header>
</template>

<script setup>
import { computed } from "vue"

import StatusMark from "@/components/shell/StatusMark.vue"
import ThemeSwitch from "@/components/shell/ThemeSwitch.vue"
import { useViewerStore } from "@/stores/viewer"

const viewer = useViewerStore()
const loaded = computed(() => viewer.loaded)
const where = computed(() => {
  const one = loaded.value
  return one ? [one.scene, one.view].filter(Boolean).join(" / ") : ""
})
</script>
