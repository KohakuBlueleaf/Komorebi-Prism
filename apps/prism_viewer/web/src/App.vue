<template>
  <div class="viewer min-h-screen flex flex-col bg-page text-ink">
    <AppHeader />
    <main class="layout flex-1 min-h-0 grid gap-3 p-3 sm:p-4">
      <FrameStage class="stage-area min-h-0" />
      <aside class="side side-left flex flex-col gap-3 min-w-0 min-h-0" aria-label="What is chosen and how to steer">
        <ChoicePanel />
        <KeysPanel />
        <NoticeList />
      </aside>
      <aside class="side side-right flex flex-col gap-3 min-w-0 min-h-0" aria-label="What is tuned and measured">
        <ControlsPanel />
        <NumbersPanel />
      </aside>
    </main>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted } from "vue"

import ChoicePanel from "@/components/panels/ChoicePanel.vue"
import ControlsPanel from "@/components/panels/ControlsPanel.vue"
import KeysPanel from "@/components/panels/KeysPanel.vue"
import NumbersPanel from "@/components/panels/NumbersPanel.vue"
import AppHeader from "@/components/shell/AppHeader.vue"
import NoticeList from "@/components/shell/NoticeList.vue"
import FrameStage from "@/components/stage/FrameStage.vue"
import { useSettingsStore } from "@/stores/settings"
import { useViewerStore } from "@/stores/viewer"

const settings = useSettingsStore()
const viewer = useViewerStore()

settings.apply()
onMounted(() => viewer.start())
onBeforeUnmount(() => viewer.stop())
</script>

<style scoped>
/* Below 1280 px one column: the frame, then the left column's panels, then the right's.
   From 1280 px the page is the window's height: a left column (choosing, keys, notices),
   the frame, a right column (controls, numbers); each column scrolls inside itself. */
.layout {
  grid-template-columns: minmax(0, 1fr);
  grid-template-areas:
    "stage"
    "left"
    "right";
  align-items: start;
}
.stage-area {
  grid-area: stage;
}
.stage-area :deep(.stage) {
  max-height: 72vh;
}
.side-left {
  grid-area: left;
}
.side-right {
  grid-area: right;
}
@media (min-width: 1280px) {
  .viewer {
    height: 100vh;
    overflow: hidden;
  }
  .layout {
    grid-template-columns: 19rem minmax(0, 1fr) 23rem;
    grid-template-rows: minmax(0, 1fr);
    grid-template-areas: "left stage right";
    align-items: stretch;
  }
  .stage-area :deep(.stage) {
    max-height: none;
    aspect-ratio: auto;
  }
  .side {
    overflow-y: auto;
    padding-right: 2px;
  }
}
</style>
