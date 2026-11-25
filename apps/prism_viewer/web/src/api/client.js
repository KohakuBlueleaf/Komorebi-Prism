// The server's routes; the token is the page address's `token`, sent with every request.

const TOKEN_HEADER = "X-Token"

export const token = new URLSearchParams(window.location.search).get("token") || ""

function query(path) {
  return `${path}?token=${encodeURIComponent(token)}`
}

async function get(path) {
  const response = await fetch(query(path), { cache: "no-store" })
  if (!response.ok) throw new Error(`${path}: ${response.status}`)
  return response.json()
}

// A POST's answer: { ok, status, body } (a refusal's body carries its `error`).
async function post(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", [TOKEN_HEADER]: token },
    body: JSON.stringify(body),
  })
  let answer = null
  try {
    answer = await response.json()
  } catch {
    answer = { error: `${response.status}` }
  }
  return { ok: response.ok, status: response.status, body: answer }
}

export const api = {
  state: () => get("/api/state"),
  catalog: () => get("/api/catalog"),
  streamUrl: (nonce) => `${query("/api/stream")}&n=${nonce}`,
  pose: (pose, sceneSerial) => post("/api/pose", { ...pose, scene_serial: sceneSerial }),
  size: (width, height) => post("/api/size", { width, height }),
  select: (pipeline, scene, view) => post("/api/select", { pipeline, scene, view }),
  control: (name, value) => post("/api/control", { name, value }),
}
