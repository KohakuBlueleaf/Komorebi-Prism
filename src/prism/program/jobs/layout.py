"""The job thread's resources assigned from the jobs of a pipeline: its command numbers,
its regions in id order with their sizes, its defines; the text of jobs_layout.h and of
jobs_program.c (the command switch)."""

import hashlib
from pathlib import Path

import numpy as np
from komorebi.program import thread as km_thread

from prism.core.headers import defined

RUNTIME = "jobs"  # the runtime's own commands and regions
C = Path(__file__).resolve().parent / "c"
J = defined(C / "jobs.h")
PAGE = km_thread.PAGE
REGIONS_MAX = km_thread.layout()["KMX_REGIONS_MAX"]
HANDLER_MOST = 239  # a thread's handler numbers are 1 to 239
SERVE = "jobs_serve"  # the runtime's command: a cluster that is not the lead serves
BLOCK = "jobs_block"  # the runtime's region: the job's input and the parts' lines
HEADER = "jobs_layout.h"
SOURCE = "jobs_program.c"


def pages(bytes_):
    """`bytes_` rounded up to whole pages."""
    return -(-bytes_ // PAGE) * PAGE


class JobLayout:
    """The job thread's resources for `jobs`, a list of (owner name, Job, host) in the
    pipeline's order: commands {name: (owner, C function, number)}, regions {name:
    (owner, id, bytes, Shared or None)}; ValueError naming what does not fit."""

    def __init__(self, jobs):
        self.jobs = list(jobs)
        self.commands = {SERVE: (RUNTIME, "jb_serve", 1)}
        block = J["JB_BLOCK_IN"] + J["JB_PARTS_MOST"] * J["JB_LINE"]
        self.regions = {BLOCK: (RUNTIME, 0, pages(block), None)}
        for owner, job, host in self.jobs:
            for name, function in job.serves.items():
                if name in self.commands:
                    raise ValueError(
                        f"job thread: command {name!r} served by "
                        f"{self.commands[name][0]} and by {owner}"
                    )
                self.commands[name] = (owner, function, len(self.commands) + 1)
            for name, region in job.regions.items():
                if name in self.regions:
                    raise ValueError(
                        f"job thread: region {name!r} asked by "
                        f"{self.regions[name][0]} and by {owner}"
                    )
                size = pages(region.size(host))
                self.regions[name] = (owner, len(self.regions), size, region)
        if len(self.commands) > HANDLER_MOST:
            raise ValueError(
                f"job thread: {len(self.commands)} commands, at most {HANDLER_MOST}"
            )
        if len(self.regions) > REGIONS_MAX:
            raise ValueError(
                f"job thread: {len(self.regions)} regions "
                f"({', '.join(self.regions)}), at most {REGIONS_MAX}"
            )
        self.defines = self.place_defines()

    def place_defines(self):
        """Every job's defines, one value a name; refused for a name two jobs give
        differently."""
        out = {}
        for owner, job, host in self.jobs:
            for name, text in job.build_defines(host).items():
                if name in out and out[name] != text:
                    raise ValueError(
                        f"job thread: define {name} is {out[name]!r} and {text!r} "
                        f"({owner})"
                    )
                out[name] = text
        return out

    def handlers(self):
        """The commands {name: number} for program.thread."""
        return {name: number for name, (_, _, number) in self.commands.items()}

    def handler(self, name):
        """The number of command `name`; KeyError naming the commands."""
        if name not in self.commands:
            raise KeyError(
                f"job thread has no command {name!r}; it has {', '.join(self.commands)}"
            )
        return self.commands[name][2]

    def region_values(self):
        """{name: bytes or first words} of every region, in id order."""
        out = {}
        for name, (owner, _, bytes_, region) in self.regions.items():
            host = self.host_of(owner)
            if region is None or region.contents is None:
                out[name] = bytes_
                continue
            words = np.zeros(bytes_ // 4, np.uint32)
            first = np.asarray(region.contents(host), np.uint32).reshape(-1)
            if len(first) > len(words):
                raise ValueError(
                    f"job thread: region {name!r} given {4 * len(first)} B, sized "
                    f"{bytes_} B"
                )
            words[: len(first)] = first
            out[name] = words
        return out

    def host_of(self, owner):
        """The host of the job `owner` (None for the runtime)."""
        for name, _, host in self.jobs:
            if name == owner:
                return host
        return None

    def macros(self):
        """The layout's macros: {name: value}."""
        out = {"JB_REGIONS": len(self.regions)}
        for name, (_, index, bytes_, _) in self.regions.items():
            out[f"JB_REGION_{name.upper()}"] = index
            out[f"JB_REGION_{name.upper()}_BYTES"] = bytes_
        for name, (_, _, number) in self.commands.items():
            out[f"JB_HANDLER_{name.upper()}"] = number
        return out

    def header_text(self):
        """jobs_layout.h: every region and command as a macro."""
        out = ["/* Generated by prism.program.jobs.layout: the job thread's layout. */"]
        out += ["#pragma once", ""]
        out += [f"#define {name} {value}u" for name, value in self.macros().items()]
        return "\n".join(out) + "\n"

    def program_text(self):
        """jobs_program.c: each job function declared, kmx_program's switch."""
        jobs = [
            (n, f) for n, (owner, f, _) in self.commands.items() if owner != RUNTIME
        ]
        lines = [
            "/* Generated by prism.program.jobs.layout: the job commands' switch. */",
            '#include "jobs.h"',
            "",
            *[
                f"uint32_t {function}(const km_command_t* command);"
                for _, function in jobs
            ],
            "",
            "uint32_t kmx_program(const km_command_t* command) {",
            "    const uint32_t ready = jb_ready();",
            "    switch (kmx_handler(command)) {",
            f"        case JB_HANDLER_{SERVE.upper()}:",
            "            return jb_serve(command);",
        ]
        for name, function in jobs:
            lines += [
                f"        case JB_HANDLER_{name.upper()}:",
                f"            return ready ? ready : {function}(command);",
            ]
        lines += ["    }", "    return JB_BAD_ARGS;", "}"]
        return "\n".join(lines) + "\n"

    def write(self, root):
        """jobs_layout.h and jobs_program.c into a folder of `root` named by their
        text: the folder."""
        texts = {HEADER: self.header_text(), SOURCE: self.program_text()}
        digest = hashlib.sha256("".join(texts.values()).encode()).hexdigest()[:16]
        folder = Path(root) / f"jobs-{digest}"
        folder.mkdir(parents=True, exist_ok=True)
        for name, text in texts.items():
            path = folder / name
            if not path.exists() or path.read_text() != text:
                path.write_text(text)
        return folder
