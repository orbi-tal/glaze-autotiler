#!/usr/bin/env python
"""
Stress test for glaze-autotiler: repeatedly opens and closes a batch of
Notepad windows to exercise window_managed / focus_changed / tiling-direction
handling under load.

NOTE ON CLOSING: this closes windows via `taskkill /IM notepad.exe /F`,
which force-closes EVERY notepad.exe process on the machine, not just ones
this script opened. That's intentional, on current Windows,
"notepad.exe" resolves through an App Execution Alias to the packaged
Notepad app, and depending on Windows build/config a launch may: spawn a
real new process, spawn a short-lived alias stub that hands off to a
separately-hosted real process, or get absorbed as a new tab into an
already-running single instance.Don't run this on a machine where you
(or anyone else) has Notepad open with something you care about.

Usage:
    python stress_test_notepad.py
    python stress_test_notepad.py --windows 10 --cycles 20
    python stress_test_notepad.py -w 15 -c 0 --dwell 3 --open-delay 0.2

Press Ctrl+C at any time to stop early (it'll still try to close whatever's
currently open before exiting).
"""
import argparse
import subprocess
import sys
import time


def open_notepads(count, open_delay, procs):
    """Launch count notepad.exe processes, appending Popen handles to
    procs as each one opens, so a Ctrl+C mid-burst doesn't lose track
    of ones already opened.
    """
    for i in range(count):
        proc = subprocess.Popen(["notepad.exe"])
        procs.append(proc)
        if open_delay > 0 and i < count - 1:
            time.sleep(open_delay)


def close_notepads(procs):
    # Force-close EVERY running notepad.exe process.

    result = subprocess.run(
        ["taskkill", "/IM", "notepad.exe", "/F", "/T"],
        capture_output=True,
        text=True,
    )
    # returncode 128 ("process not found") just means there was nothing
    # left to close
    if result.returncode not in (0, 128):
        print(
            f"  warning: taskkill exited {result.returncode}: "
            f"{result.stdout.strip()} {result.stderr.strip()}",
            file=sys.stderr,
        )

    for proc in procs:
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass  # taskkill already handled the real process either way


def run(windows, cycles, open_delay, dwell, cycle_delay):
    if sys.platform != "win32":
        print(
            "error: this stress test launches notepad.exe and uses "
            "taskkill, so it only runs on Windows.",
            file=sys.stderr,
        )
        sys.exit(1)

    infinite = cycles <= 0
    cycle_num = 0
    procs = []  # so a Ctrl+C during the very first open_notepads() call has something to close
    try:
        while infinite or cycle_num < cycles:
            cycle_num += 1
            label = f"{cycle_num}" + ("" if infinite else f"/{cycles}")
            print(f"[cycle {label}] opening {windows} notepad windows...")
            start = time.time()
            procs = []
            open_notepads(windows, open_delay, procs)
            print(f"[cycle {label}] opened in {time.time() - start:.2f}s, " f"holding for {dwell}s")
            time.sleep(dwell)
            close_start = time.time()
            close_notepads(procs)
            print(f"[cycle {label}] closed in {time.time() - close_start:.2f}s")
            if cycle_delay > 0 and (infinite or cycle_num < cycles):
                time.sleep(cycle_delay)
    except KeyboardInterrupt:
        print("\nInterrupted -- closing any remaining windows...")
        close_notepads(procs)
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-w",
        "--windows",
        type=int,
        default=10,
        help="Notepad windows to open per cycle (default: 10)",
    )
    parser.add_argument(
        "-c",
        "--cycles",
        type=int,
        default=0,
        help="Number of cycles to run, 0 = run until Ctrl+C (default: 0)",
    )
    parser.add_argument(
        "--open-delay",
        type=float,
        default=0.1,
        help="Seconds between opening each window (default: 0.1)",
    )
    parser.add_argument(
        "--dwell",
        type=float,
        default=2.0,
        help="Seconds to leave a batch open before closing it (default: 2.0)",
    )
    parser.add_argument(
        "--cycle-delay",
        type=float,
        default=1.0,
        help="Seconds to pause between cycles (default: 1.0)",
    )
    args = parser.parse_args()
    run(args.windows, args.cycles, args.open_delay, args.dwell, args.cycle_delay)


if __name__ == "__main__":
    main()
