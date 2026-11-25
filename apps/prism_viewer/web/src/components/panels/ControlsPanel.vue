<template>
  <PanelCard id="controls" title="Controls" icon="i-carbon-settings-adjust">
    <div v-if="!viewer.controls.length" class="px-3 py-3 kt-text-body text-ink-faint">The loaded pipeline's hosts give no controls.</div>
    <div v-else class="flex flex-col divide-y divide-solid divide-line">
      <ControlField v-for="control in viewer.controls" :key="control.name" :control="control" />
    </div>
  </PanelCard>
</template>

<script setup>
import ControlField from "@/components/panels/ControlField.vue"
import PanelCard from "@/components/panels/PanelCard.vue"
import { useViewerStore } from "@/stores/viewer"

const viewer = useViewerStore()
</script>
