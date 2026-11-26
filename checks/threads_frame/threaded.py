"""A threads' preset assembled and loaded (prism.program.threads.assemble), held as the
checks hold a loop: its loaded run, options, size, session, hosts, one attempt of a
frame, its picture, the stop."""

from prism.program.threads import assemble
from prism_reference.scene.camera import with_size


class ThreadedLoop:
    """`preset` (prism_cli.preset.Opened of a threads' preset) on `session`."""

    def __init__(self, preset, session):
        self.session = session
        self.size = tuple(preset.size)
        scene = with_size(preset.scene, self.size)
        self.threaded = assemble.assembled(
            preset.pipeline, session, scene, preset.options
        )
        self.loaded = assemble.load(self.threaded, session)
        self.options = dict(self.threaded.options)

    def hosts(self):
        """The hosts in the pipeline's order."""
        return list(self.threaded.hosts.values())

    def attempt(self, camera):
        """Every host's view, then the FRAME command: its code."""
        assemble.view(self.threaded, self.loaded, camera, self.size)
        return assemble.frame(self.loaded)

    def picture(self):
        """The display read back (H, W, 4) uint8."""
        return assemble.target(self.threaded, self.loaded)

    def stop(self):
        """The run stopped."""
        self.loaded.stop()
