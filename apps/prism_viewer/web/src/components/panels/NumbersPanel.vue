<template>
  <PanelCard id="numbers" title="Numbers" icon="i-carbon-chart-stacked">
    <div class="grid grid-cols-3 divide-x divide-solid divide-line border-b border-solid border-line">
      <div class="flex flex-col gap-0.5 px-3 py-2.5 min-w-0">
        <span class="field-label truncate" title="pictures served in the last second">pictures / s</span>
        <span class="kt-text-figure font-mono text-aquamarine-shadow dark:text-aquamarine">{{ fps }}</span>
      </div>
      <div class="flex flex-col gap-0.5 px-3 py-2.5 min-w-0">
        <span class="field-label truncate" title="the FRAME command on the card, as the host waits for it">frame ms</span>
        <span class="kt-text-figure font-mono text-sapphire dark:text-sapphire-light">{{ frameMs }}</span>
      </div>
      <div class="flex flex-col gap-0.5 px-3 py-2.5 min-w-0">
        <span class="field-label truncate" title="seconds since the last picture">age s</span>
        <span class="kt-text-figure font-mono" :class="stale ? 'text-coral' : 'text-taaffeite-shadow dark:text-taaffeite-light'">{{ age }}</span>
      </div>
    </div>
    <p v-if="hasTimes" class="mx-3 mt-3 rounded-lg px-2.5 py-2 kt-text-caption" :class="behind ? 'bg-amber/10 text-amber-shadow dark:text-amber-light' : 'bg-surface-alt text-ink-muted'">The loop made {{ madeFps }} frames in the last second, {{ fps }} pictures were served and {{ replacedFps }} replaced before encoding. The render loop takes each picture from the host ({{ pictureMs }} ms) and goes on to the next frame; {{ encoders }} encoder{{ encoders === 1 ? "" : "s" }} beside it take{{ encoders === 1 ? "s" : "" }} {{ encodeMs }} ms a picture.</p>
    <div class="flex flex-col gap-3 px-3 py-3">
      <TimesBar v-if="hasTimes" :times="state.times" />
      <div v-for="given in viewer.readings" :key="given.name" class="pt-2 border-t border-solid border-line">
        <div class="field-label mb-1.5 uppercase tracking-wider truncate" :title="given.name">{{ given.title }}</div>
        <dl class="grid grid-cols-3 gap-x-3 gap-y-0.5">
          <div v-for="one in given.values" :key="one.name" class="flex flex-col min-w-0">
            <dt class="field-label truncate" :title="one.name">{{ one.name }}</dt>
            <dd class="num-value" :class="one.unit === 'ms' ? 'text-amber-shadow dark:text-amber-light' : 'text-ink'">{{ reading(one.value) }}</dd>
          </div>
        </dl>
        <p v-if="given.missing" class="mt-1 kt-text-caption text-ink-faint">{{ given.missing }}</p>
      </div>
      <div class="pt-2 border-t border-solid border-line">
        <div class="field-label mb-1.5 uppercase tracking-wider">The card's parts</div>
        <CardTable :card="state?.card" />
      </div>
    </div>
  </PanelCard>
</template>

<script setup>
import { computed } from "vue"

import CardTable from "@/components/panels/CardTable.vue"
import PanelCard from "@/components/panels/PanelCard.vue"
import TimesBar from "@/components/panels/TimesBar.vue"
import { useViewerStore } from "@/stores/viewer"

const STALE_S = 2

const viewer = useViewerStore()
const state = computed(() => viewer.state)
const times = computed(() => state.value?.times ?? {})
const hasTimes = computed(() => Object.keys(times.value).length > 0)
const first = computed(() => Object.values(times.value)[0])

const fps = computed(() => (state.value ? state.value.fps.toFixed(0) : "-"))
const frameMs = computed(() => (first.value === undefined ? "-" : first.value.toFixed(2)))
const age = computed(() => (state.value?.picture_age_s == null ? "-" : state.value.picture_age_s.toFixed(1)))
const stale = computed(() => (state.value?.picture_age_s ?? 0) > STALE_S)
const rate = (name) => (state.value?.[name] ?? 0).toFixed(0)
const madeFps = computed(() => rate("made_fps"))
const replacedFps = computed(() => rate("replaced_fps"))
const encoders = computed(() => state.value?.encoders ?? 0)
const ms = (name) => (times.value[name] === undefined ? "-" : times.value[name].toFixed(1))
const pictureMs = computed(() => ms("picture"))
const encodeMs = computed(() => ms("encode"))
const behind = computed(() => (state.value?.replaced_fps ?? 0) > 0)
const reading = (value) => (value === null || value === undefined ? "-" : typeof value !== "number" || Number.isInteger(value) ? String(value) : value.toFixed(2))
</script>
