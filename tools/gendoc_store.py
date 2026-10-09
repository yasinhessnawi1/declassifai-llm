"""Durable, resumable run storage for the document generator.

A full generation run is days of GPU time on a card that other jobs have priority
over, so it is stopped and restarted many times. Pilot runs wrote their output once,
at the end, and a kill lost everything. This module is the part that makes a kill cheap:

* every finished document is appended to disk, flushed and fsynced, the moment it
  finishes, into shards of a fixed number of accepted documents;
* a document is *committed* by its metadata line, which is written last, so a kill
  between the three accepted-document files leaves orphan lines that the next load
  removes and the document is simply generated again;
* a torn last line (power loss, SIGKILL in the middle of a write) is detected and
  dropped on load, never parsed;
* `run_manifest.json` records what produced the files (arguments, git commit, source and
  data hashes), so a resume can refuse when the generator or its data changed and a
  deliberate override is written into the manifest's history rather than done silently;
* `StopController` turns SIGTERM, SIGINT, a stop file and optionally another process
  taking the GPU into one flag the run loop honours between documents.

Nothing here knows what a document is; `generate_documents` supplies the lines.
"""

from __future__ import annotations

import datetime
import glob
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

MANIFEST_NAME = "run_manifest.json"
PLAN_NAME = "plan.json"
G1_NAME = "g1_shards.json"
DISCARDED_NAME = "discarded.jsonl"
MANIFEST_FORMAT = 1


class StoreError(RuntimeError):
    """The files on disk are not a state a run can safely continue from."""


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# -- hashing ---------------------------------------------------------------------------

def sha256_file(path: str) -> Optional[str]:
    """Return the SHA-256 of a file, or None when it does not exist."""
    if not os.path.exists(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code_hashes(tools_dir: str) -> Dict[str, str]:
    """Hash every generator source file: `generate_documents.py` and `gendoc_*.py`.

    `validate_labels.py` is left out on purpose: it judges the output (G1) and cannot change
    which documents are generated.

    Args:
        tools_dir: The directory holding the generator.

    Returns:
        File name -> SHA-256.
    """
    names = ["generate_documents.py"] + sorted(
        os.path.basename(p) for p in glob.glob(os.path.join(tools_dir, "gendoc_*.py")))
    return {name: sha256_file(os.path.join(tools_dir, name)) or "" for name in names}


def combined_hash(hashes: Dict[str, Optional[str]]) -> str:
    """Return one digest over a name -> hash mapping."""
    digest = hashlib.sha256()
    for name in sorted(hashes):
        digest.update(f"{name}={hashes[name]}\n".encode())
    return digest.hexdigest()


def git_commit(directory: str) -> str:
    """Return the HEAD commit of the repository containing `directory`, or "unknown"."""
    try:
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=directory, capture_output=True,
                              text=True, timeout=10)
        return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def changed_hashes(old: Dict[str, Optional[str]], new: Dict[str, Optional[str]]) -> Dict[str, dict]:
    """Return `{name: {"was": old, "now": new}}` for every name whose hash differs."""
    return {name: {"was": old.get(name), "now": new.get(name)}
            for name in sorted(set(old) | set(new)) if old.get(name) != new.get(name)}


# -- durable file operations -------------------------------------------------------------

def _fsync_dir(path: str) -> None:
    try:
        fd = os.open(path or ".", os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_json(path: str, obj: object) -> None:
    """Replace `path` with `obj` as JSON so a reader sees the old file or the new one, never half."""
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    _fsync_dir(os.path.dirname(path))


def append_line(path: str, line: str) -> None:
    """Append one line, flush it to the device, and return only when it is durable.

    The line goes out in a single `write` on an `O_APPEND` descriptor, so a signal handler
    that exits the process cannot run in the middle of it.
    """
    created = not os.path.exists(path)
    payload = (line.rstrip("\n") + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        view = memoryview(payload)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    if created:
        _fsync_dir(os.path.dirname(path))


def touch(path: str) -> None:
    """Create an empty file if it is missing."""
    if not os.path.exists(path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)
        os.close(fd)
        _fsync_dir(os.path.dirname(path))


def read_rows(path: str, repair: bool) -> Tuple[List[dict], List[int], Optional[str]]:
    """Read a JSONL file whose last line may be torn.

    A last line without its newline, or whose JSON does not parse, was cut short by a kill and
    is dropped. With `repair` the file is truncated to the last good line.

    Args:
        path: The file; a missing file reads as empty.
        repair: Truncate the file in place when a torn tail is found.

    Returns:
        Tuple of (parsed rows, the byte offset at which each row ends, a description of what
        was dropped or None).
    """
    if not os.path.exists(path):
        return [], [], None
    with open(path, "rb") as handle:
        raw = handle.read()
    good = len(raw)
    dropped = None
    if raw and not raw.endswith(b"\n"):
        good = raw.rfind(b"\n") + 1
        dropped = f"{len(raw) - good} bytes without a newline"
    rows: List[dict] = []
    ends: List[int] = []
    pos = 0
    while pos < good:
        end = raw.index(b"\n", pos) + 1
        try:
            rows.append(json.loads(raw[pos:end]))
        except ValueError:
            if end != good:
                raise StoreError(f"{path}: a line before the end of the file is not valid JSON "
                                 f"(byte {pos}); this is not a torn tail, refusing to guess")
            dropped = f"{len(raw) - pos} bytes whose last line is not valid JSON"
            good = pos
            break
        ends.append(end)
        pos = end
    if dropped and repair:
        truncate(path, good)
    return rows, ends, (f"{os.path.basename(path)}: dropped {dropped}" if dropped else None)


def truncate(path: str, size: int) -> None:
    """Cut a file to `size` bytes and fsync it."""
    with open(path, "r+b") as handle:
        handle.truncate(size)
        handle.flush()
        os.fsync(handle.fileno())


# -- shard store -----------------------------------------------------------------------

class ShardStore:
    """Accepted documents in shards of `shard_size`, discarded ones in one file.

    Files, with `stem` the dataset's file stem and `NNNNN` the shard number:
    `{stem}_batch_NNNNN.jsonl` (`{id, text_input, output}`), `{stem}_batch_NNNNN_labelled.jsonl`
    (the same lines with a non-empty output) and `{stem}_batch_NNNNN_meta.jsonl` (the commit
    record), plus `discarded.jsonl`.

    Attributes:
        out_dir: Output directory.
        stem: File stem of the dataset.
        shard_size: Accepted documents per shard.
        accepted: Committed `(batch_line, meta)` pairs in write order, after `load`.
        discarded: Discarded-document records in write order, after `load`.
        repairs: What `load` repaired.
    """

    def __init__(self, out_dir: str, stem: str, shard_size: int) -> None:
        if shard_size < 1:
            raise ValueError("shard size must be at least 1")
        self.out_dir = out_dir
        self.stem = stem
        self.shard_size = shard_size
        self.accepted: List[Tuple[dict, dict]] = []
        self.discarded: List[dict] = []
        self.repairs: List[str] = []

    def path(self, shard: int, kind: str = "") -> str:
        """Return the path of a shard file; `kind` is "", "labelled" or "meta"."""
        suffix = f"_{kind}" if kind else ""
        return os.path.join(self.out_dir, f"{self.stem}_batch_{shard:05d}{suffix}.jsonl")

    @property
    def discarded_path(self) -> str:
        return os.path.join(self.out_dir, DISCARDED_NAME)

    def shard_numbers(self) -> List[int]:
        """Return the shard numbers that have any file on disk."""
        found = set()
        pattern = re.compile(rf"^{re.escape(self.stem)}_batch_(\d{{5}})(?:_labelled|_meta)?\.jsonl$")
        for name in os.listdir(self.out_dir) if os.path.isdir(self.out_dir) else []:
            match = pattern.match(name)
            if match:
                found.add(int(match.group(1)))
        return sorted(found)

    def has_output(self) -> bool:
        """Whether the directory already holds shard files or a discard file."""
        return bool(self.shard_numbers()) or os.path.exists(self.discarded_path)

    def load(self, repair: bool) -> "ShardStore":
        """Read everything written so far, dropping torn tails and uncommitted lines.

        A document is committed iff its meta line is present. Batch and labelled lines past the
        last committed document belong to a document that was being written when the process
        died; with `repair` they are removed so that document can be generated again.

        Args:
            repair: Modify files (truncate torn tails and orphans). False for read-only views
                such as `--status` and `--report-only` while a run may be appending.

        Returns:
            self.

        Raises:
            StoreError: If the shards are inconsistent in a way a kill cannot cause.
        """
        self.accepted, self.discarded, self.repairs = [], [], []
        shards = self.shard_numbers()
        for position, shard in enumerate(shards):
            metas, _, note = read_rows(self.path(shard, "meta"), repair)
            self.repairs += [note] if note else []
            committed = {m["id"] for m in metas}
            if len(committed) != len(metas):
                raise StoreError(f"{self.path(shard, 'meta')}: duplicate document ids")
            batch_rows = self._committed_rows(self.path(shard), committed, repair)
            labelled_rows = self._committed_rows(self.path(shard, "labelled"), committed, repair)
            by_id = {row["id"]: row for row in batch_rows}
            missing = [m["id"] for m in metas if m["id"] not in by_id]
            if missing:
                raise StoreError(f"{self.path(shard)}: committed documents {missing[:3]} have no text line")
            if {row["id"] for row in labelled_rows} - committed:
                raise StoreError(f"{self.path(shard, 'labelled')}: lines for uncommitted documents")
            if len(metas) > self.shard_size:
                raise StoreError(f"shard {shard} holds {len(metas)} documents but --shard-size is "
                                 f"{self.shard_size}; the shard size of a run cannot change")
            if position < len(shards) - 1 and len(metas) != self.shard_size:
                raise StoreError(f"shard {shard} holds {len(metas)} documents but is not the last; "
                                 f"expected {self.shard_size}")
            self.accepted += [(by_id[m["id"]], m) for m in metas]
        rows, _, note = read_rows(self.discarded_path, repair)
        self.discarded = rows
        self.repairs += [note] if note else []
        return self

    def _committed_rows(self, path: str, committed: set, repair: bool) -> List[dict]:
        rows, ends, note = read_rows(path, repair)
        if note:
            self.repairs.append(note)
        keep = 0
        while keep < len(rows) and rows[keep]["id"] in committed:
            keep += 1
        if keep < len(rows):
            self.repairs.append(f"{os.path.basename(path)}: removed {len(rows) - keep} line(s) of a "
                                f"document that was not committed")
            if repair:
                truncate(path, ends[keep - 1] if keep else 0)
            rows = rows[:keep]
        return rows

    @property
    def n_accepted(self) -> int:
        return len(self.accepted)

    def append_accepted(self, batch_line: dict, meta: dict) -> Optional[int]:
        """Write one accepted document: text line, labelled line, then the meta commit line.

        Args:
            batch_line: `{id, text_input, output}`.
            meta: The metadata record, with the same `id`.

        Returns:
            The shard number if this document filled its shard, else None.
        """
        shard = self.n_accepted // self.shard_size
        for kind in ("", "labelled", "meta"):
            touch(self.path(shard, kind))
        line = json.dumps(batch_line, ensure_ascii=False)
        append_line(self.path(shard), line)
        if batch_line["output"]:
            append_line(self.path(shard, "labelled"), line)
        append_line(self.path(shard, "meta"), json.dumps(meta, ensure_ascii=False))
        self.accepted.append((batch_line, meta))
        return shard if self.n_accepted % self.shard_size == 0 else None

    def append_discarded(self, record: dict) -> None:
        """Write one discarded document."""
        append_line(self.discarded_path, json.dumps(record, ensure_ascii=False, default=str))
        self.discarded.append(record)

    def closed_shards(self) -> List[int]:
        """Return the shards that hold `shard_size` committed documents."""
        return list(range(self.n_accepted // self.shard_size))


# -- stopping ---------------------------------------------------------------------------

def query_gpu_processes() -> Optional[List[Tuple[int, int]]]:
    """Return `(pid, MiB)` for every compute process `nvidia-smi` reports, or None if it cannot run.

    The PIDs are those of the host's namespace, which in a container need not match
    `os.getpid()`.
    """
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    found = []
    for row in proc.stdout.splitlines():
        parts = [p.strip() for p in row.split(",")]
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            found.append((int(parts[0]), int(parts[1])))
    return found


class StopController:
    """One place that says whether the run should wind down, and why.

    A stop is *graceful*: the documents in flight are finished and written, the manifest is
    updated and the process exits 0. It is requested by SIGTERM or SIGINT, by a stop file
    appearing, or, when `yield_mb` is set, by other processes holding more than that much GPU
    memory. A second SIGINT exits at once; that is safe because every finished document is
    already durable.

    Attributes:
        stop_file: Path whose existence requests a stop.
        yield_mb: Other processes' GPU memory (MiB) above which the run steps aside; None disables.
        reason: Why the run is stopping, or None.
        gpu_query: Callable returning `[(pid, MiB)]`, replaceable in tests.
        own_gpu_mb: Callable returning this process's own GPU use in MiB when `nvidia-smi` cannot
            identify it by PID, or None.
    """

    def __init__(self, stop_file: str, yield_mb: Optional[int] = None,
                 log: Callable[[str], None] = lambda m: print(m, file=sys.stderr, flush=True)) -> None:
        self.stop_file = stop_file
        self.yield_mb = yield_mb
        self.reason: Optional[str] = None
        self.gpu_query: Callable[[], Optional[List[Tuple[int, int]]]] = query_gpu_processes
        self.own_gpu_mb: Callable[[], Optional[int]] = lambda: None
        self._log = log
        self._sigint_seen = False
        self._warned_smi = False

    def install_signal_handlers(self) -> None:
        """Route SIGTERM and SIGINT to graceful stop; a second SIGINT exits immediately."""
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT, self._on_signal)

    def _on_signal(self, signum, _frame) -> None:
        name = signal.Signals(signum).name
        if signum == signal.SIGINT and self._sigint_seen:
            self._log("second SIGINT: exiting immediately; every finished document is already on disk")
            os._exit(130)
        self._sigint_seen = self._sigint_seen or signum == signal.SIGINT
        if self.reason is None:
            self.request(f"signal {name}")
            self._log("finishing the documents in flight, then exiting (SIGINT again to exit at once)")

    def request(self, reason: str) -> None:
        """Ask for a graceful stop; the first reason wins."""
        if self.reason is None:
            self.reason = reason
            self._log(f"stop requested: {reason}")

    @property
    def stopping(self) -> bool:
        return self.reason is not None

    def gpu_contention(self) -> Optional[str]:
        """Return a description of the other GPU processes if they hold more than `yield_mb`."""
        if self.yield_mb is None:
            return None
        procs = self.gpu_query()
        if procs is None:
            if not self._warned_smi:
                self._warned_smi = True
                self._log("warning: nvidia-smi is unavailable; --yield-when-gpu-busy cannot check")
            return None
        me = os.getpid()
        listed_me = any(pid == me for pid, _ in procs)
        others = [(pid, mb) for pid, mb in procs if pid != me]
        total = sum(mb for _, mb in others)
        note = ""
        if not listed_me:
            own = self.own_gpu_mb()
            if own:
                total = max(0, total - own)
                note = (f" (this process is not identifiable by PID here; its own use is estimated at "
                        f"{own} MiB and subtracted)")
        if total <= self.yield_mb:
            return None
        listing = ", ".join(f"PID {pid} {mb} MiB" for pid, mb in others)
        return f"other GPU processes hold {total} MiB > {self.yield_mb} MiB: {listing}{note}"

    def poll(self) -> bool:
        """Check the stop file and GPU contention; return whether a stop is now requested."""
        if self.reason is None and self.stop_file and os.path.exists(self.stop_file):
            self.request(f"stop file {self.stop_file}")
        if self.reason is None:
            busy = self.gpu_contention()
            if busy:
                self.request(f"yielding the GPU: {busy}")
        return self.reason is not None
