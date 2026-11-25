<template>
  <section class="card overflow-hidden min-w-0 shrink-0">
    <div class="card-head">
      <button class="flex items-center gap-2 flex-1 min-w-0 h-full text-left uppercase tracking-wider" :aria-expanded="!folded" @click="settings.toggleFold(id)">
        <span :class="icon" class="text-ink-faint shrink-0" />
        <span class="flex-1 truncate">{{ title }}</span>
      </button>
      <slot name="aside" />
      <button class="flex items-center h-full" :aria-label="folded ? `Show ${title}` : `Fold ${title}`" @click="settings.toggleFold(id)">
        <span class="i-carbon-chevron-down text-ink-faint transition-transform" :class="folded ? '-rotate-90' : ''" />
      </button>
    </div>
    <div v-show="!folded" :class="bodyClass">
      <slot />
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue"

import { useSettingsStore } from "@/stores/settings"

const props = defineProps({
  id: { type: String, required: true },
  title: { type: String, required: true },
  icon: { type: String, default: "i-carbon-panel-expansion" },
  bodyClass: { type: String, default: "" },
})

const settings = useSettingsStore()
const folded = computed(() => !!settings.folded[props.id])
</script>
