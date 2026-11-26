"""The job thread of an assembled program: one image on the job clusters (the runtime,
the generated switch, the jobs' C), its regions shared by every cluster of the image,
declared on the program."""

from prism.core.headers import INCLUDE
from prism.program.jobs.layout import C, JobLayout
from prism_common.paths import build_root

CLUSTERS = (2, 3)  # the work clusters the job thread's image runs on
DEADLINE = 10.0  # seconds kmx_main may take: the lead waits there for the others


def lead(clusters=CLUSTERS):
    """The cluster that answers job commands: the lowest of the image's."""
    return min(clusters)


def declare(program, jobs, name, clusters=CLUSTERS):
    """The job thread for `jobs` (owner, Job, host) declared on `program` under the
    build folder `name`: its regions declared shared, its image on `clusters`; its
    JobLayout."""
    layout = JobLayout(jobs)
    sources, includes = [], []
    for _, job, _ in layout.jobs:
        job_sources, job_includes = job.files()
        sources += job_sources
        includes += job_includes
    stems = [source.stem for source in sources]
    if len(set(stems)) != len(stems):
        raise ValueError(f"job sources with one name: {', '.join(sorted(stems))}")
    generated = layout.write(build_root() / "jobs" / name)
    for region, value in layout.region_values().items():
        program.region(region, value)
    program.thread(
        clusters=tuple(clusters),
        sources=[C / "jobs.c", generated / "jobs_program.c", *sources],
        includes=[C, generated, INCLUDE, *includes],
        regions={},
        shared=tuple(layout.regions),
        handlers=layout.handlers(),
        defines=layout.defines,
        deadline=DEADLINE,
    )
    return layout
