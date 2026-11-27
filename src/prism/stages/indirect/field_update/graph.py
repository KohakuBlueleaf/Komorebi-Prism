"""The field update as the job thread's job and a graph the dispatcher keeps: the job
(its C, commands, shared regions, defines), the graph (the sources, each bounce's apply
a core step of the frame's thread on every core and its pass, the finish, the field
given to the frame's thread) and its host side (written, started, served)."""

from pathlib import Path

import komorebi as km
import numpy as np
from komorebi.engines.graph import Graph

from prism.core.headers import defined
from prism.program.director.thread import STEP_ARGS, STEP_CODE_MASK
from prism.program.jobs.frame import wants_args
from prism.program.jobs.job import Job, Shared
from prism.stages.indirect.field_update.model.header import sun_words
from prism.stages.indirect.field_update.model.numbers import (
    F32,
    HEADER_BYTES,
    PAGE_BYTES,
    PAGE_TEXELS,
    SUN_FIRST,
    TIMES_BYTES,
    U,
    header_defines,
)
from prism_reference.direct.lights import bounce_count, shadow_side

FOLDER = Path(__file__).resolve().parent
N = defined(FOLDER / "thread" / "job_field.h")
NUMBERS = ("cores", "shadow", "shadow_first", "field", "field_first", "x", "y")
COMMANDS = {
    "field_sources": "job_field_sources",
    "field_pass": "job_field_pass",
    "field_finish": "job_field_finish",
    "field_scale": "job_field_scale",
}
REQ = 0x4655  # the kept graph's request id
DEADLINE_US = 5_000_000  # a node's command's give-up, microseconds
POLL_S = 0.0005  # a look at the graph's end that does not wait
WAIT_S = 60.0  # a wait for the graph's end


def job_defines():
    """The job's C defines: the header's word places and the numbers of
    indirect_field_update.h (sizes, times row, steps) it cannot include."""
    numbers = {
        name: f"{value}u"
        for name, value in U.items()
        if name.startswith("FU_") and isinstance(value, int)
    }
    return numbers | header_defines()


JOB = Job(
    folder=FOLDER,
    sources=("thread/job_field_update.c", "thread/job_field_parts.c"),
    includes=("thread",),
    serves=COMMANDS,
    regions={
        "field_header": Shared(HEADER_BYTES, lambda host: host.header_words()),
        "field_numbers": Shared(4 * N["JF_N_WORDS"]),
        "field_elements": Shared(
            lambda host: host.elements.nbytes,
            lambda host: host.elements.view(np.uint32),
        ),
        "field_shadow": Shared(
            lambda host: shadow_side(host.lights) ** 2 * PAGE_BYTES // PAGE_TEXELS
        ),
        "field_work": Shared(lambda host: host.work_bytes),
        "field_pages": Shared(lambda host: host.counts["pages"] * PAGE_BYTES),
        "field_times": Shared(TIMES_BYTES),
    },
    defines=lambda host: job_defines(),
)


def update_graph(jobs, frame, step, step_args, lead, runs):
    """The kept graph of an update: `jobs` {command: number} of the job thread on
    cluster `lead`, `frame` and `step` the frame's thread's job_wants and core_step
    numbers, `step_args` the apply's core_step words, at most `runs` rounds (a bounce a round).
    Registers 0 and 1: the code, the scale's word."""
    graph = Graph(deadline_microseconds=DEADLINE_US, max_runs=runs, req=REQ, keep=True)
    code, scale = graph.registers(2)
    left, half, first = graph.bindings("left", "half", "first")
    zero, one, mask = graph.const(0), graph.const(1), graph.const(STEP_CODE_MASK)
    last, release, go, stepped = graph.registers(4)
    again = graph.again
    sources = graph.command(
        jobs["field_sources"], cluster=lead, result=code, skip_if_zero=first
    )
    ahead = graph.cpu(after=[sources])
    clean = ahead.forward()
    ahead.mov(go, left)
    ahead.set(stepped, 0)
    ahead.jeq(code, zero, clean)
    ahead.set(go, 0)
    ahead.bind(clean)
    applied = graph.command(
        step, cluster=1, args=step_args, after=[ahead], result=stepped, skip_if_zero=go
    )
    passed = graph.command(
        jobs["field_pass"], cluster=lead, after=[applied], result=code, skip_if_zero=go
    )
    turn = graph.cpu(after=[passed])
    failed, kept = turn.forward(), turn.forward()
    turn.set(first, 0)
    turn.and_(stepped, stepped, mask)
    turn.jnz(stepped, failed)
    turn.jnz(code, failed)
    turn.jeq(go, zero, kept)
    turn.sub(left, left, one)
    turn.bind(kept)
    turn.lt(again, zero, left)
    turn.ge(last, zero, left)
    turn.mov(release, last)
    end = turn.forward()
    turn.jmp(end)
    turn.bind(failed)
    turn.set(again, 0)
    turn.set(last, 0)
    turn.set(release, 1)
    turn.bind(end)
    finish = graph.command(
        jobs["field_finish"], cluster=lead, after=[turn], result=code, skip_if_zero=last
    )
    scaled = graph.command(
        jobs["field_scale"],
        cluster=lead,
        after=[finish],
        result=scale,
        skip_if_zero=last,
    )
    checked = graph.cpu(after=[scaled])
    good = checked.forward()
    checked.jeq(code, zero, good)
    checked.set(last, 0)
    checked.bind(good)
    graph.command(
        frame,
        cluster=1,
        args=wants_args(last, half, scale),
        after=[checked],
        skip_if_zero=release,
    )
    return graph


class FieldGraph:
    """The update of `update` (a prepared FieldUpdateHost, connected and bound) as the
    job of `jobs` (a JobThread) driven by a kept graph on `run`: `frame` and `step` the
    frame's thread's job_wants and core_step numbers, `apply` the transport's handler
    and `apply_args` its words, `cores` the cores its apply's tables were dealt to."""

    def __init__(self, update, jobs, run, frame, step, apply, apply_args, cores):
        self.update = update
        self.jobs = jobs
        self.run = run
        self.frame = frame
        self.step = step
        self.apply = apply
        self.apply_args = list(apply_args)
        self.cores = int(cores)
        self.upload = None
        self.runs = 0  # the rounds the uploaded graph allows
        self.kept = False  # whether the uploaded graph was started once (kept since)
        self.handle = None  # the graph's start that has not ended
        self.asked = None  # (sun, bounces, half) of the update running

    def step_args(self):
        """The apply as core_step's words: its header, its group (every core the
        tables were dealt to), its words; ValueError for words past STEP_ARGS."""
        if len(self.apply_args) > STEP_ARGS:
            raise ValueError(
                f"the apply's {len(self.apply_args)} words: a core step carries "
                f"{STEP_ARGS}"
            )
        header = int(self.apply) | self.run.program_field(self.apply.program) << 24
        words = self.apply_args + [0] * (STEP_ARGS - len(self.apply_args))
        return [header, self.cores << 16, *words]

    def write_numbers(self, half):
        """The numbers region: the cores that copy (those the update is given), the
        light pages for the shadow map and for the field's half `half`, x and y."""
        host = self.update
        values = {
            "cores": self.cores,
            "shadow": host.pages.address,
            "shadow_first": host.first["shadow"],
            "field": host.pages.address,
            "field_first": host.field_first(half),
            "x": host.x.address,
            "y": host.y.address,
        }
        words = np.zeros(N["JF_N_WORDS"], np.uint32)
        for name, value in values.items():
            words[N[f"JF_N_{name.upper()}"]] = value
        self.jobs.write("field_numbers", words)

    def graph_for(self, bounces):
        """The kept graph uploaded for `bounces` passes: the one uploaded when it
        allows them, else made again (the old one released)."""
        if self.upload is not None and bounces + 1 <= self.runs:
            return False
        if self.upload is not None:
            self.run.release(self.upload)
        handlers = {name: self.jobs.handler(name) for name in COMMANDS}
        self.runs, self.kept = bounces + 1, False
        graph = update_graph(
            handlers,
            self.frame,
            self.step,
            self.step_args(),
            self.jobs.lead,
            self.runs,
        )
        self.upload = self.run.upload(graph)
        return True

    def start(self, lights, sun, bounces):
        """An update of `lights` (the sun `sun`) with `bounces` passes into the half
        the field is not read from: the sun's words and the numbers written, the graph
        started (False while one runs)."""
        if self.handle is not None:
            return False
        host = self.update
        bounces = bounce_count(bounces)
        half = host.written()
        self.jobs.write("field_header", sun_words(lights, bounces), 4 * SUN_FIRST)
        self.write_numbers(half)
        bindings = {"left": bounces, "half": half, "first": 1}
        self.graph_for(bounces)
        if self.kept:
            self.handle = self.run.restart(REQ, bindings)
        else:
            self.handle = self.run.start(self.upload, bindings)
            self.kept = True
        self.asked = (sun, bounces, half)
        return True

    def served(self, wait=False):
        """The graph's end once it came (`wait`: waited for): (code, scale) with the
        update host's field kept (its sun, bounces, half, scale); None while it runs;
        KomorebiError for an error event."""
        if self.handle is None:
            return None
        try:
            event = self.run.wait_engine(self.handle, WAIT_S if wait else POLL_S)
        except km.EngineTimeout:
            return None
        except km.EngineError as error:
            self.handle = None
            raise km.KomorebiError(f"field update graph: {error}") from error
        self.handle = None
        code, word = (int(value) for value in event.registers)
        scale = np.array([word], np.uint32).view(F32)[0]
        if code == 0:
            host = self.update
            sun, bounces, half = self.asked
            host.made, host.half = (sun, bounces), half
            host.given.update(updates=host.given["updates"] + 1, scale=scale, half=half)
        return code, scale

    def times(self):
        """The times region's bytes, read after the stop."""
        return self.jobs.read("field_times")
