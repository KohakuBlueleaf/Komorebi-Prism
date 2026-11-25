import { defineStore } from "pinia"

import { api } from "@/api/client"

const POLL_MS = 500
const LOCAL_NOTICES = 4

// The server's state, read twice a second, its catalog, and the requests the page makes;
// a request the server refuses becomes a local notice with its reason (unless the server
// says it has noticed it already). The page's pose (steered by usePose) and its edits'
// count, which makes usePose post it.
export const useViewerStore = defineStore("viewer", {
  state: () => ({
    state: null,
    catalog: { pipelines: [], scenes: [] },
    reachable: true,
    local: [],
    localSerial: 0,
    clearedAt: 0,
    timer: null,
    pose: null,
    poseEdits: 0,
  }),

  getters: {
    status: (s) => (!s.reachable ? "unreachable" : (s.state?.status ?? "loading")),
    loaded: (s) => s.state?.loaded ?? null,
    controls: (s) => s.state?.controls ?? [],
    readings: (s) => s.state?.readings ?? [],
    size: (s) => s.state?.size ?? null,
    pipeline: (s) => s.catalog.pipelines.find((one) => one.name === s.state?.choice?.[0]) ?? null,
    notices: (s) => {
      const server = s.state?.notices ?? []
      return [...server, ...s.local]
        .filter((one) => one.at > s.clearedAt)
        .sort((a, b) => a.at - b.at)
    },
    reloading: (s) => s.state?.status === "loading",
    fovLimits: (s) => s.state?.fov_limits ?? [1, 179],
    ownFov: (s) => s.state?.first_pose?.fov ?? null,
  },

  actions: {
    async start() {
      try {
        this.catalog = await api.catalog()
      } catch (error) {
        this.refused("catalog", error.message)
      }
      await this.poll()
      this.timer = window.setInterval(() => this.poll(), POLL_MS)
    },
    stop() {
      window.clearInterval(this.timer)
    },
    async poll() {
      try {
        this.state = await api.state()
        this.reachable = true
      } catch {
        this.reachable = false
      }
    },
    clearNotices() {
      this.clearedAt = Date.now() / 1000
    },
    refused(what, reason) {
      this.localSerial += 1
      const notice = {
        serial: `local-${this.localSerial}`,
        kind: "refusal",
        text: `${what}: ${reason}`,
        seconds: null,
        at: Date.now() / 1000,
      }
      this.local = [...this.local, notice].slice(-LOCAL_NOTICES)
    },
    async answered(what, request) {
      const answer = await request
      if (!answer.ok && !answer.body?.noticed)
        this.refused(what, answer.body?.error ?? answer.status)
      await this.poll()
      return answer.ok
    },
    select(pipeline, scene, view) {
      return this.answered("select", api.select(pipeline, scene, view))
    },
    resize(width, height) {
      return this.answered("size", api.size(width, height))
    },
    setControl(name, value) {
      return this.answered(name, api.control(name, value))
    },
    // The pose's field of view in degrees, within the server's limits; posted next tick.
    setFov(fov) {
      if (!this.pose || !Number.isFinite(fov)) return
      const [least, most] = this.fovLimits
      this.pose.fov = Math.max(least, Math.min(most, fov))
      this.poseEdits += 1
    },
  },
})
