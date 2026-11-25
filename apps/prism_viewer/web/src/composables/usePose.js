import { onBeforeUnmount, onMounted, toRef, watch } from "vue"

import { api } from "@/api/client"

const MOVE_KEYS = new Set(["w", "a", "s", "d", "q", "e"])
const POSTS_A_SECOND = 60
const STEP_OF_DIAGONAL = 0.1 // a tenth of the scene box's diagonal a second
const FAST = 5 // with shift
const PITCH_LIMIT = (89 * Math.PI) / 180
const WHEEL_FACTOR = 1.1 // the field of view a wheel notch narrows or widens by
const WHEEL_PIXELS = 100 // a notch, when the wheel counts in pixels

function ahead(pose) {
  const c = Math.cos(pose.pitch)
  return [c * Math.sin(pose.yaw), Math.sin(pose.pitch), c * Math.cos(pose.yaw)]
}

function right(pose) {
  return [-Math.cos(pose.yaw), 0, Math.sin(pose.yaw)]
}

function typing(event) {
  const target = event.target
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target?.isContentEditable
  )
}

// The pose (the viewer store's) from the keys (W A S D along the view, Q E down and up,
// shift faster), a drag on `surface` (yaw and pitch, the shown frame's width half a turn)
// and the wheel over it (the field of view, WHEEL_FACTOR a notch; where the page itself
// scrolls, only while steering); posted at most
// 60 times a second while it changes. A new scene (its serial) starts from its own pose.
export function usePose(viewer, surface, shownWidth, steering) {
  const pose = toRef(viewer, "pose")
  const held = new Set()
  let shift = false
  let changed = false
  let posting = false
  let lastPost = 0
  let before = performance.now()
  let drag = null
  let frame = 0

  watch(
    () => viewer.state?.scene_serial,
    () => {
      const first = viewer.state?.first_pose
      pose.value = first ? JSON.parse(JSON.stringify(first)) : null
    },
    { immediate: true },
  )
  watch(
    () => viewer.poseEdits,
    () => (changed = true),
  )

  function onKey(event, down) {
    shift = event.shiftKey
    if (typing(event)) return
    const key = event.key.toLowerCase()
    if (!MOVE_KEYS.has(key)) return
    if (down) held.add(key)
    else held.delete(key)
    event.preventDefault()
  }
  const keydown = (event) => onKey(event, true)
  const keyup = (event) => onKey(event, false)
  const blur = () => held.clear()

  function pointerdown(event) {
    surface.value?.focus()
    drag = { x: event.clientX, y: event.clientY }
    surface.value?.setPointerCapture(event.pointerId)
  }
  function pointermove(event) {
    if (!drag || !pose.value) return
    const turn = Math.PI / Math.max(shownWidth(), 1)
    pose.value.yaw -= (event.clientX - drag.x) * turn
    pose.value.pitch -= (event.clientY - drag.y) * turn
    pose.value.pitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, pose.value.pitch))
    drag = { x: event.clientX, y: event.clientY }
    changed = true
  }
  function pointerup() {
    drag = null
  }
  // The page does not scroll (the columns' layout): the wheel over the frame has no other use.
  const pageFixed = () => {
    const page = document.scrollingElement
    return !!page && page.scrollHeight <= page.clientHeight
  }
  function wheel(event) {
    if (!(steering() || pageFixed()) || !pose.value || !event.deltaY) return
    event.preventDefault()
    const notches = event.deltaMode === 0 ? event.deltaY / WHEEL_PIXELS : Math.sign(event.deltaY)
    viewer.setFov(pose.value.fov * WHEEL_FACTOR ** notches)
  }

  function tick(now) {
    const seconds = Math.min((now - before) / 1000, 0.1)
    before = now
    const current = pose.value
    if (current && held.size) {
      const step = (viewer.state?.diagonal ?? 1) * STEP_OF_DIAGONAL * (shift ? FAST : 1) * seconds
      const move = [0, 0, 0]
      const add = (v, s) => v.forEach((x, i) => (move[i] += x * s))
      if (held.has("w")) add(ahead(current), 1)
      if (held.has("s")) add(ahead(current), -1)
      if (held.has("d")) add(right(current), 1)
      if (held.has("a")) add(right(current), -1)
      if (held.has("e")) add([0, 1, 0], 1)
      if (held.has("q")) add([0, 1, 0], -1)
      current.position = current.position.map((x, i) => x + move[i] * step)
      changed = true
    }
    if (changed && !posting && now - lastPost >= 1000 / POSTS_A_SECOND && current) {
      changed = false
      posting = true
      lastPost = now
      api
        .pose(current, viewer.state?.scene_serial ?? -1)
        .catch(() => {})
        .finally(() => (posting = false))
    }
    frame = requestAnimationFrame(tick)
  }

  onMounted(() => {
    window.addEventListener("keydown", keydown)
    window.addEventListener("keyup", keyup)
    window.addEventListener("blur", blur)
    frame = requestAnimationFrame(tick)
  })
  onBeforeUnmount(() => {
    window.removeEventListener("keydown", keydown)
    window.removeEventListener("keyup", keyup)
    window.removeEventListener("blur", blur)
    cancelAnimationFrame(frame)
  })

  return { pose, pointerdown, pointermove, pointerup, wheel }
}
