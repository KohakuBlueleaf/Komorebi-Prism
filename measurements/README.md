# Measurements

Recorded measurements: the card, the date and the command with every number. The pages
under `docs/performance/` quote from here.

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
| [lookup_model](lookup_model/README.md) | the pages a frame's lookups read, modelled on the host and checked against the account: today's passes, an item's pages, the pages a core would keep |
| [update_beside](update_beside/README.md) | the field's update on the cluster beside the frames' (`gi_tile`): the frames drawn during it, the swap, against `gi`'s blocking update |
| [viewer](viewer/README.md) | the viewer's field of view at its ends |
| [open](open/README.md) | `prism_cli open` on four artists' scenes: the account of a load part by part, cold and warm, `textured` and `lit`; the bake of the sky's visibility alone |
| [transport_build](transport_build/README.md) | the indirect light's transport built dense and block by block on Sponza and an artists' scene: seconds by phase, rays, flops, memory, bytes, the error against the dense matrix; ray trees |
