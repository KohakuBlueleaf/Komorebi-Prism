<template>
  <button class="btn-icon" :title="settings.dark ? 'Light theme' : 'Dark theme'" :aria-label="settings.dark ? 'Light theme' : 'Dark theme'" @click="settings.toggleTheme()">
    <span :class="settings.dark ? 'i-carbon-sun' : 'i-carbon-moon'" />
  </button>
</template>

<script setup>
import { useSettingsStore } from "@/stores/settings"

const settings = useSettingsStore()
</script>
