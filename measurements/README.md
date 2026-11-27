# Measurements

Recorded measurements: the card, the date and the command with every number. The pages
under `docs/performance/` quote from here.

A folder's README opens with its conditions; its card line, from the records'
`aiclk_mhz` and `pcie_link`:

    - Card: one Blackhole P150A, card <n>, <cores> cores, AICLK <MHz> MHz and its PCIe
      link at <current> of <max> GT/s, before and after every run as the runs report it.

| folder | what it records |
| --- | --- |
| [raster_show](raster_show/README.md) | the preset `raster` with its display: nine cases on a moving camera, the card's parts and the host's frame |
| [textured_show](textured_show/README.md) | the preset `textured` with its display |
| [textured_frame](textured_frame/README.md) | the preset `textured` without the display: each layer's parts |
| [lit_frame](lit_frame/README.md) | the preset `lit`: the frames at three sizes, a moved sun, the controls |
| [gi_frame](gi_frame/README.md) | the preset `gi`: the frames at three sizes, the field's update in the loop |
| [field_update](field_update/README.md) | the preset `field`: the update alone, against the reference, its parts |
| [apply](apply/README.md) | the preset `apply`: the transport's apply alone |
| [account](account/README.md) | the account of a frame: each command's cores, waits, standing still, bytes and closure, the L1, the code, the per-item constants |
| [account_tile](account_tile/README.md) | the account with LIGHT shown (`lit_tile`, `gi_tile`): the tile frame against the stage-wise frame, the L1 |
| [threads_account](threads_account/README.md) | the account of the threads' frame: four ways of handing out, bytes by path, a core's time, the CPUs by step, the X280's choice, a record a thread |
| [gi_threads](gi_threads/README.md) | the renderer's frame: `gi_threads` against `gi` on the ten scenes of the viewer's data at 1,920 x 1,080, by phase, pictures equal; the field's update after one sun move |
| [lists_kept](lists_kept/README.md) | the eye's lists kept while its view stands: the standing frame (the tile pull alone) against the whole frame on four scenes at three poses, pictures equal |
| [threads_ranges](threads_ranges/README.md) | the size of a count range: 4 blocks against the size chosen from the scene, on four scenes at three poses, by phase, pictures equal |
| [lookup_model](lookup_model/README.md) | the pages a frame's lookups read, modelled on the host and checked against the account: today's passes, an item's pages, the pages a core would keep |
| [update_beside](update_beside/README.md) | the field's update on the cluster beside the frames' (`gi_tile`): the frames drawn during it, the swap, against `gi`'s blocking update |
| [viewer](viewer/README.md) | the viewer's field of view at its ends |
| [gltf_truth](gltf_truth/README.md) | the artists' scenes exported plain and rendered by Cycles from the glTF: what the export loses against the `.blend`, which scenes are usable, the reference and the card against the same file |
| [open](open/README.md) | `prism_cli open` on four artists' scenes: the account of a load part by part, cold and warm, `textured` and `lit`; the bake of the sky's visibility alone |
| [transport_build](transport_build/README.md) | the indirect light's transport built dense and block by block on Sponza and an artists' scene: seconds by phase, rays, flops, memory, bytes, the error against the dense matrix; ray trees |
