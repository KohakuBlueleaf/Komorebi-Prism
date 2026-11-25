# The viewer: the pose's field of view at its ends

The range of the pose's field of view the viewer offers (`FOV_LEAST`, `FOV_MOST` in
`apps/prism_viewer/server/camera.py`) and the table in `docs/guides/viewer.md`, "The field
of view", come from these runs.

- Card: one Blackhole P150A, 120 cores (a 12 x 10 grid), card 1.
- Date: 2026-11-25 (UTC+8).
- Tree: the code that gave the viewer's pose its field of view.
- How: a script (not in the repository) opened the preset `lit` as the command line opens
  it (`prism_cli.preset.opened(pipeline, scene, view, size)`), took the view's own pose
  (`server/camera.py` `pose_of`), and for each field of view in turn made the camera of that
  pose with that field of view (`camera_of`), rendered one frame of it
  (`Loop.frame(sized_camera(camera, size), picture=True)`) and, for the angles judged, ran
  the preset's `JUDGE` (`prism.stages.direct.light.check.thread_frame.lit`) on the picture
  against the reference at that camera. One session and one loop a file, the frames one
  after another in the order of the file.

| file | scene, view | size |
| --- | --- | --- |
| `fov_sponza_overview_1024_1024.jsonl` | sponza, overview (own field of view 75) | 1,024 x 1,024 |
| `fov_sponza_overview_1920_1080.jsonl` | sponza, overview | 1,920 x 1,080 |
| `fov_bistro_exterior_overview_1024_1024.jsonl` | bistro_exterior, overview (own 70) | 1,024 x 1,024 |
| `fov_bistro_exterior_overview_1920_1080.jsonl` | bistro_exterior, overview | 1,920 x 1,080 |

Each file is the run's output as it printed it: a first line with the view's own field of
view (`own_fov`, degrees, from the camera's focal), the size and the scene; then one line a
field of view, 179, 178, 170, 150, 120, 100, 75, 50, 30, 15, 8, 4, 2, 1 and 0.5 degrees:
`code` (the frame's), `retries`, `reloads` (and their records), `ms` (the host's time of
the call, the picture included), and for the angles judged, `judged`: the judge's report (`checked` pixels,
`later_pieces`, `share_over_2`, `share_over_4`, `share_over_8`, `max_error`, the same on
the glass in front and on the band and outside it). Sponza at 1,024 x 1,024 is judged at
every angle; the others at 179, 170, 120, 75, 8, 1 and 0.5.

Every frame of the four files is code 0, with no retry and no reload. The guide's table
quotes `share_over_2`, `share_over_8` and `max_error` at 0.5 degrees, 75 degrees and 179
degrees.
