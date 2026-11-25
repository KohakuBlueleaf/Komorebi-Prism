import { createApp } from "vue"
import { createPinia } from "pinia"

import App from "./App.vue"

import "@fontsource/inter/400.css"
import "@fontsource/inter/500.css"
import "@fontsource/inter/600.css"
import "@fontsource/jetbrains-mono/400.css"
import "@fontsource/jetbrains-mono/500.css"
import "element-plus/theme-chalk/dark/css-vars.css"
import "uno.css"
import "./style.css"

createApp(App).use(createPinia()).mount("#app")
