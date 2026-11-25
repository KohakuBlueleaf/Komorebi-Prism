import { defineStore } from "pinia"

// What this browser keeps: the theme, which panels are folded and which disclosures are
// open; the address's `theme` (light or dark) wins for that visit.
const KEY = "prism-viewer-settings"
const ASKED = new URLSearchParams(window.location.search).get("theme")

function read() {
  try {
    return JSON.parse(window.localStorage.getItem(KEY) || "{}")
  } catch {
    return {}
  }
}

function prefersDark() {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false
}

export const useSettingsStore = defineStore("settings", {
  state: () => {
    const kept = read()
    return {
      dark: ASKED ? ASKED === "dark" : (kept.dark ?? prefersDark()),
      folded: kept.folded ?? {},
      opened: kept.opened ?? {},
    }
  },
  actions: {
    apply() {
      document.documentElement.classList.toggle("dark", this.dark)
    },
    keep() {
      try {
        window.localStorage.setItem(
          KEY,
          JSON.stringify({ dark: this.dark, folded: this.folded, opened: this.opened }),
        )
      } catch {
        // a browser without storage keeps the settings for this visit only
      }
    },
    toggleTheme() {
      this.dark = !this.dark
      this.apply()
      this.keep()
    },
    toggleOpen(disclosure) {
      this.opened = { ...this.opened, [disclosure]: !this.opened[disclosure] }
      this.keep()
    },
    toggleFold(panel) {
      this.folded = { ...this.folded, [panel]: !this.folded[panel] }
      this.keep()
    },
  },
})
