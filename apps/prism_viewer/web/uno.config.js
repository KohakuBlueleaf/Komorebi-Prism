import {
  defineConfig,
  presetWind,
  presetAttributify,
  presetIcons,
  transformerDirectives,
} from "unocss"

// The tokens' one place (with src/style.css): KohakuTerrarium's gem colours, the
// functional coral and sage, the warm surfaces; the page's surfaces and inks follow the theme.
export default defineConfig({
  content: {
    pipeline: {
      include: [/\.(vue|html)($|\?)/, /[\\/]src[\\/].*\.js($|\?)/],
    },
  },
  presets: [
    presetWind(),
    presetAttributify(),
    presetIcons({
      scale: 1.2,
      extraProperties: {
        display: "inline-block",
        "vertical-align": "middle",
      },
    }),
  ],
  transformers: [transformerDirectives()],
  preflights: [
    {
      getCSS: ({ theme }) => {
        const declarations = []
        for (const [name, value] of Object.entries(theme.colors)) {
          if (typeof value === "string") {
            if (!value.startsWith("var(")) declarations.push(`--kt-color-${name}: ${value};`)
            continue
          }
          for (const [shade, hex] of Object.entries(value)) {
            const suffix = shade === "DEFAULT" ? "" : `-${shade}`
            declarations.push(`--kt-color-${name}${suffix}: ${hex};`)
          }
        }
        return `:root {\n  ${declarations.join("\n  ")}\n}`
      },
    },
  ],
  theme: {
    colors: {
      // Gem accents
      sapphire: { light: "#D6E3F8", DEFAULT: "#0F52BA", shadow: "#082567" },
      aquamarine: { light: "#D4EDE8", DEFAULT: "#4C9989", shadow: "#1B6B5A" },
      taaffeite: { light: "#E8D5ED", DEFAULT: "#A57EAE", shadow: "#6B4670" },
      iolite: { light: "#DDD0F0", DEFAULT: "#5A4FCF", shadow: "#312A7A" },
      amber: { light: "#F5E6C8", DEFAULT: "#D4920A", shadow: "#8B5E00" },
      // Functional
      coral: { light: "#F5D5D5", DEFAULT: "#D46B6B", shadow: "#8B3A3A" },
      sage: { light: "#D5E8DA", DEFAULT: "#5A9E6F", shadow: "#3A6B48" },
      // Warm surfaces
      warm: {
        50: "#F7F5F2",
        100: "#EFECE7",
        200: "#E0DBD4",
        300: "#C5BFB7",
        400: "#A09A92",
        500: "#8A8480",
        600: "#6A645F",
        700: "#4A4540",
        800: "#3A3632",
        900: "#2A2724",
        950: "#1A1816",
      },
      // The theme's surfaces and inks (src/style.css)
      page: "var(--color-bg)",
      surface: "var(--color-surface)",
      "surface-alt": "var(--color-surface-alt)",
      line: "var(--color-border)",
      ink: "var(--color-text)",
      "ink-muted": "var(--color-text-muted)",
      "ink-faint": "var(--color-text-faint)",
      stage: "var(--kt-stage)",
    },
    fontFamily: {
      sans: "var(--font-sans)",
      mono: "var(--font-mono)",
    },
  },
  shortcuts: {
    card: "bg-surface rounded-xl border border-solid border-line",
    "card-head":
      "flex items-center gap-2 px-3 h-9 border-b border-solid border-line kt-text-caption font-medium uppercase tracking-wider text-ink-muted",
    "btn-primary":
      "inline-flex items-center justify-center gap-1.5 px-4 h-8 rounded-lg bg-iolite text-white hover:bg-iolite-shadow transition-colors font-medium kt-text-body border-none disabled:bg-surface-alt disabled:text-ink-faint disabled:cursor-not-allowed",
    "btn-icon":
      "inline-flex items-center justify-center w-8 h-8 rounded-lg text-ink-muted hover:bg-warm-200/60 dark:hover:bg-warm-700/40 hover:text-ink transition-colors",
    "field-label": "kt-text-caption text-ink-muted",
    "num-value": "font-mono kt-text-body text-ink",
    "chip-warm":
      "inline-flex items-center gap-1 px-2 h-6 rounded-full kt-text-caption leading-none border border-solid border-line bg-surface-alt text-ink-muted",
    "chip-iolite":
      "inline-flex items-center gap-1 px-2 h-6 rounded-full kt-text-caption leading-none border border-solid border-iolite/40 bg-iolite/10 text-iolite dark:text-iolite-light",
  },
})
