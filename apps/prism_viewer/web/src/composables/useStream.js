import { onBeforeUnmount, ref } from "vue"

import { api } from "@/api/client"

const RETRY_MS = 1500

// The frames' stream as an image address; opened again after an error (a server restart).
export function useStream() {
  const nonce = ref(Date.now())
  const src = ref(api.streamUrl(nonce.value))
  const broken = ref(false)
  let timer = 0

  function failed() {
    broken.value = true
    window.clearTimeout(timer)
    timer = window.setTimeout(() => {
      nonce.value = Date.now()
      src.value = api.streamUrl(nonce.value)
    }, RETRY_MS)
  }
  function loaded() {
    broken.value = false
  }

  onBeforeUnmount(() => window.clearTimeout(timer))

  return { src, broken, failed, loaded }
}
