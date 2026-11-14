#!/usr/bin/env python3
"""bearings_run: record one real run of a route, for the bearings map.

A route on the parts list says in words how one thing travels through the project. This module measures
that journey once: for each step, which box of the route it belongs to, the file and line the code was at,
how long it took, and the values that went in and came out. It writes docs/runs/<route>.json, which
`bearings.py web` shows under the route and `bearings.py doctor` compares with it.

Use it from a small script of your own that drives the project's real code. The project's code is not
changed: `watch` wraps a function for as long as the recording lasts and puts it back afterwards.

    import sys
    sys.path.insert(0, "<this skill's scripts folder>")
    from bearings_run import Run
    import robot.control as control

    with Run("One control tick", name="simulator, one step") as run:
        run.watch(control, "read_sensors", "Read sensors")       # owner, attribute, box of the route
        run.watch(control.Policy, "infer", "Run the policy", out="action")
        control.tick()                                           # the real thing, run for real

Where no function marks a step, time a stretch of your own script instead:

        with run.step("Assemble observation", joints=q) as s:
            obs = build(q)
            s.out(obs=obs)

Values are cut to one short line each (a long array becomes its length and its first numbers), and a value
whose name looks like a secret (password, token, key, ...) is written as dots. The file is still made of
real values from a real run: read it before committing it or sharing the map.

A program in another language can write the same file; `bearings.py --help` gives its shape.
Python 3 standard library only.
"""
import contextvars
import dataclasses
import datetime
import functools
import inspect
import json
import os
import re
import subprocess
import sys
import threading
import time

RUNS_DIR = "docs/runs"
MAX_STEPS = 200    # steps kept from one run; a watched function called in a long loop stops being recorded
TEXT = 220         # characters kept of one value
HEAD = 6           # numbers kept from the start of a long array
SECRET_RE = re.compile(r"pass(?:word|wd)?|secret|token|api[_-]?key|authori[sz]ation|cookie|credential|private[_-]?key", re.I)
_depth = contextvars.ContextVar("bearings_run_depth", default=0)


def _cut(text):
    text = " ".join(str(text).split())
    return text if len(text) <= TEXT else text[:TEXT - 1] + "…"


def _plain(value, name="", level=0):
    """A value as something JSON can hold and a person can read in one line."""
    if name and SECRET_RE.search(str(name)):
        return "•••"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, str):
        return _cut(value)
    if isinstance(value, bytes):
        return "%d bytes" % len(value)
    if level > 3:
        return _cut(repr(value))
    shape = getattr(value, "shape", None)
    if shape is not None and hasattr(value, "tolist"):  # a numpy array, a torch tensor: its shape and its start
        try:
            flat = value.reshape(-1)[:HEAD].tolist()
            return "shape %s · [%s%s]" % (tuple(shape), ", ".join(json.dumps(_plain(x)) for x in flat),
                                          ", …" if _size(shape) > HEAD else "")
        except Exception:
            return _cut(repr(value))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = {f.name: getattr(value, f.name) for f in dataclasses.fields(value)}
    elif hasattr(value, "model_dump") and callable(value.model_dump):  # a pydantic model
        try:
            value = value.model_dump()
        except Exception:
            return _cut(repr(value))
    if isinstance(value, dict):
        return {str(k): _plain(v, k, level + 1) for k, v in list(value.items())[:24]}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        if len(items) > HEAD and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in items):
            return "%d × [%s, …]" % (len(items), ", ".join(json.dumps(_plain(x)) for x in items[:HEAD]))
        return [_plain(x, "", level + 1) for x in items[:24]] + (["… %d more" % (len(items) - 24)] if len(items) > 24 else [])
    text = repr(value)
    if re.match(r"^<.* at 0x[0-9a-fA-F]+>$", text):  # no repr of its own: the address says nothing, the class does
        return "<%s>" % type(value).__name__
    return _cut(text)


def _size(shape):
    n = 1
    for k in shape:
        n *= int(k)
    return n


def _values(pairs):
    """{name: value} for what went into a step or came out. A small record is spread over a line per field
    (`state.gyro`), so each of its values can be read by itself."""
    out = {}
    for k, v in pairs:
        plain = _plain(v, k)
        if isinstance(plain, dict) and 0 < len(plain) <= 8:
            for field, inner in plain.items():
                out["%s.%s" % (k, field)] = inner
        else:
            out[str(k)] = plain
    return out


def _git(root, *args):
    try:
        out = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)
    except OSError:
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


class _Step:
    """One step being recorded. `out(name=value)` says what came out of it; `note(text)` adds a remark."""

    def __init__(self, run, row):
        self._run, self._row = run, row

    def out(self, **values):
        if self._row is not None:
            self._row["out"].update(_values(values.items()))
        return self

    def note(self, text):
        if self._row is not None:
            self._row["note"] = _cut(text)
        return self


class _Stretch:
    """`with run.step(...)`: the stretch of code inside is one step."""

    def __init__(self, run, box, ins, where):
        self.run, self.box, self.ins, self.where = run, box, ins, where

    def __enter__(self):
        self.row, self.token, self.t0 = self.run._open(self.box, self.where, self.ins)
        return _Step(self.run, self.row)

    def __exit__(self, kind, err, tb):
        self.run._close(self.row, self.token, self.t0, err)
        return False


class Run:
    """One recording. `route` is the title of a route on the parts list, exactly as written there."""

    def __init__(self, route, name="", root=None, out=None, command=""):
        self.route, self.name = route, name
        self.root = os.path.abspath(root or _git(os.getcwd(), "rev-parse", "--show-toplevel") or os.getcwd())
        self.out = out
        self.command = command or " ".join(sys.argv)
        self.steps, self.dropped = [], 0
        self._lock, self._patched = threading.Lock(), []
        self.path = None

    # -- recording ----------------------------------------------------------
    def _place(self, filename, line):
        path = os.path.abspath(filename)
        if not path.startswith(self.root + os.sep) or not os.path.isfile(path):
            return {"file": "", "line": 0}  # code outside the repository, or typed in: the step is kept, without a place
        return {"file": os.path.relpath(path, self.root).replace(os.sep, "/"), "line": int(line)}

    def _open(self, box, where, ins):
        depth = _depth.get()
        token = _depth.set(depth + 1)
        row = None
        with self._lock:
            if len(self.steps) < MAX_STEPS:
                row = dict({"box": box}, **where, ms=None, depth=depth, **{"in": _values(ins), "out": {}})
                self.steps.append(row)
            else:
                self.dropped += 1
        return row, token, time.perf_counter()

    def _close(self, row, token, t0, err=None):
        ms = (time.perf_counter() - t0) * 1000
        _depth.reset(token)
        if row is not None:
            row["ms"] = round(ms, 3)
            if err is not None:
                row["out"]["raised"] = _cut(repr(err))

    def step(self, box, **ins):
        """Record the stretch of code inside `with run.step("Box", name=value) as s:` as one step. The
        place noted is the line of the `with`."""
        frame = sys._getframe(1)
        return _Stretch(self, box, ins.items(), self._place(frame.f_code.co_filename, frame.f_lineno))

    def watch(self, owner, attr, box, out="return", ins=True):
        """Record every call of `owner.attr` (a function of a module, a method of a class) as a step of
        `box`, until the recording ends. What goes in is the call's arguments by name; what comes out is
        the return value, under the name `out`. The place noted is where the function is defined.
        `ins=False` leaves the arguments out, for a call whose arguments are large or private."""
        raw = inspect.getattr_static(owner, attr)
        kind = staticmethod if isinstance(raw, staticmethod) else classmethod if isinstance(raw, classmethod) else None
        fn = raw.__func__ if kind else raw
        if not callable(fn):
            raise TypeError("%r of %r is not a function" % (attr, owner))
        code = getattr(inspect.unwrap(fn), "__code__", None)
        where = self._place(code.co_filename, code.co_firstlineno) if code else {"file": "", "line": 0}
        where["fn"] = getattr(fn, "__qualname__", attr)
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            sig = None
        run = self

        def given(args, kwargs):
            if not ins:
                return []
            try:
                bound = sig.bind_partial(*args, **kwargs).arguments.items() if sig else []
            except TypeError:
                bound = []
            return [(k, v) for k, v in bound if k not in ("self", "cls")]

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                row, token, t0 = run._open(box, where, given(args, kwargs))
                try:
                    result = await fn(*args, **kwargs)
                except BaseException as err:
                    run._close(row, token, t0, err)
                    raise
                if row is not None and result is not None:
                    row["out"].update(_values([(out, result)]))
                run._close(row, token, t0)
                return result
        else:
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                row, token, t0 = run._open(box, where, given(args, kwargs))
                try:
                    result = fn(*args, **kwargs)
                except BaseException as err:
                    run._close(row, token, t0, err)
                    raise
                if row is not None and result is not None:
                    row["out"].update(_values([(out, result)]))
                run._close(row, token, t0)
                return result
        self._patched.append((owner, attr, raw))
        setattr(owner, attr, kind(wrapper) if kind else wrapper)
        return self

    def unwatch(self):
        """Put every watched function back as it was."""
        while self._patched:
            owner, attr, raw = self._patched.pop()
            setattr(owner, attr, raw)

    # -- writing ------------------------------------------------------------
    def save(self):
        """Write the run and return its path: docs/runs/<route>[-<name>].json under the repository root."""
        self.unwatch()
        slug = re.sub(r"[^\w]+", "-", self.route + ("-" + self.name if self.name else ""), flags=re.UNICODE).strip("-")
        path = self.out or os.path.join(self.root, RUNS_DIR, (slug or "run")[:80] + ".json")
        top = [s["ms"] for s in self.steps if s["depth"] == 0 and s["ms"] is not None]
        # Was the code that ran the code of that commit? Earlier recordings rewritten in this folder do not count.
        kept = os.path.relpath(os.path.dirname(os.path.abspath(path)), self.root).replace(os.sep, "/")
        apart = [":(exclude)" + kept] if kept != "." and not kept.startswith("..") else []
        data = {"route": self.route, "name": self.name,
                "recorded": datetime.datetime.now().replace(microsecond=0).isoformat(),
                "commit": _git(self.root, "rev-parse", "--short", "HEAD"),
                "dirty": bool(_git(self.root, "status", "--porcelain", "--untracked-files=no", "--", ".", *apart)),
                "command": _cut(self.command), "ms": round(sum(top), 3) if top else None,
                "dropped": self.dropped, "steps": self.steps}
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        self.path = path
        return path

    def __enter__(self):
        return self

    def __exit__(self, kind, err, tb):
        self.unwatch()
        if kind is None:  # a run that fell over is not written: half a journey would read as a whole one
            print("bearings_run: %d steps -> %s" % (len(self.steps), self.save()), file=sys.stderr)
        return False
