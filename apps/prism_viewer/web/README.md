# The viewer's page

A Vue 3 + Vite project in JavaScript, with UnoCSS, Element Plus and Pinia, in the design
language of KohakuTerrarium's frontend: the gem accents (sapphire, aquamarine, taaffeite,
iolite, amber), the functional colours (coral, sage), the warm surface scale, a light
"stone" theme and a dark one, the semantic size scale, Inter and JetBrains Mono (bundled
from `@fontsource`, no font service at run time). The tokens live in one place
(`uno.config.js` and `src/style.css`); a component names a token, never a colour.

```
npm install
npm run build     # dist/, served by the viewer's server
npm run dev       # port 5173, /api proxied to $PRISM_VIEWER_API (default 127.0.0.1:8790)
npm run lint
npm run format
```

`src/`: `main.js`, `App.vue`; `api/client.js` (the routes, the token from the address);
`stores/` (`viewer.js` the server's state and its polling, `settings.js` the theme and the
folded panels kept in the browser); `composables/` (`usePose.js` keys and drag to a pose,
`useStream.js` the frames' stream, `sceneFacts.js` a scene's numbers as the scene menu
shows them and the preset a scene falls back to); `components/stage/` (the frame and the
camera's input), `components/panels/` (pipeline and scene with the scene menu
`ScenePicker.vue`, controls, numbers, keys),
`components/shell/` (header, theme switch, status, notices).

How to start the whole viewer and what the page shows: `docs/guides/viewer.md`.
