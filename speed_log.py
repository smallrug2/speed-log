"""Periodic latency + download-speed logger with ping sparkline.

Each round pings --host (4 packets, OS-specific flags) and times an
HTTP download of --url via urllib (-> Mbps), appending a CSV row of
timestamp, ping_ms, down_mbps and printing an ASCII sparkline of the
last 20 ping readings.

Usage examples:
    python speed_log.py --rounds 3 --interval 5
    python speed_log.py --host 1.1.1.1 --rounds 10 --interval 60
    python speed_log.py --url https://example.com/file.bin --out speeds.csv

Platform notes:
    Windows (os.name == 'nt'): ping -n 4 -w 1000 <host>, parses Average = Nms
    Linux: ping -c 4 -W 2 <host>, parses rtt min/avg/max/mdev line
    macOS (sys.platform == 'darwin'): ping -c 4 -t 5 <host>, parses round-trip line
    Missing ping binary -> clean SKIP (blank ping_ms), never a traceback.
    Default --rounds 0 = infinite loop with --interval 300; Ctrl+C exits cleanly.

Dependencies:
    Standard library only (argparse, sys, os, csv, re, shutil,
    subprocess, time, datetime, urllib, pathlib).
"""

import argparse
import csv
import datetime
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

CSV_FIELDS = ["timestamp", "ping_ms", "down_mbps"]
DEFAULT_OUT = str(Path.cwd() / "speed_log.csv")
DEFAULT_URL = "https://speed.cloudflare.com/__down?bytes=10000000"
BLOCKS = "▁▂▃▄▅▆▇█"
BLOCKS_ASCII = ".-:=+*#@"  # console-safe fallback for Windows (cp1252)

IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def ping_host(host, timeout=30):
    """Ping host with 4 packets; return avg ms float or (None, skip_msg)."""
    exe = shutil.which("ping")
    if not exe:
        return None, "SKIP: 'ping' not found; recording blank ping_ms."
    if IS_WINDOWS:
        cmd = [exe, "-n", "4", "-w", "1000", host]
    elif IS_MAC:
        cmd = [exe, "-c", "4", "-t", "5", host]
    else:  # Linux and other POSIX ping variants
        cmd = [exe, "-c", "4", "-W", "2", host]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return None, "SKIP: ping failed (%s); recording blank ping_ms." % e
    text = (out.stdout or "") + "\n" + (out.stderr or "")
    avg = None
    if IS_WINDOWS:
        m = re.search(r"Average\s*=\s*(\d+(?:\.\d+)?)\s*ms", text)
        if m:
            try:
                avg = float(m.group(1))
            except ValueError:
                avg = None
    else:
        # Linux: rtt min/avg/max/mdev = ... ; macOS: round-trip ... = ...
        m = re.search(r"=\s*[\d.]+/([\d.]+)/[\d.]+/[\d.]+\s*ms", text)
        if m:
            try:
                avg = float(m.group(1))
            except ValueError:
                avg = None
    if avg is None:
        return None, "SKIP: could not parse ping output; recording blank ping_ms."
    return avg, ""


def download_mbps(url, timeout=30):
    """Download URL fully, return (Mbps float|None, bytes, seconds)."""
    start = time.monotonic()
    nbytes = 0
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "speed-log/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                nbytes += len(chunk)
                # Guard against endless streams: cap at 100 MiB.
                if nbytes >= 100 * 1024 * 1024:
                    break
    except Exception as e:  # noqa: BLE001 - report cleanly, never traceback
        return None, nbytes, time.monotonic() - start, "download failed: %s" % e
    secs = time.monotonic() - start
    if secs <= 0 or nbytes == 0:
        return None, nbytes, secs, "download returned no data"
    return (nbytes * 8 / 1e6 / secs), nbytes, secs, ""


def sparkline(values):
    """ASCII sparkline of numeric list using block chars, scaled min/max."""
    # Explicit Windows vs POSIX difference: legacy Windows consoles
    # (cp1252) cannot print Unicode block chars, so use ASCII levels.
    chars_set = BLOCKS_ASCII if IS_WINDOWS else BLOCKS
    nums = [v for v in values if v is not None]
    if not nums:
        return "(no ping data yet)"
    if len(nums) == 1 or max(nums) == min(nums):
        return chars_set[3] * len(nums) + " (%.1f ms)" % nums[-1]
    lo, hi = min(nums), max(nums)
    span = hi - lo
    chars = []
    for v in nums:
        idx = int(round((v - lo) / span * (len(chars_set) - 1)))
        chars.append(chars_set[max(0, min(len(chars_set) - 1, idx))])
    return "".join(chars) + " (%.1f..%.1f ms)" % (lo, hi)


def append_csv(path, ping_ms, down_mbps):
    """Append one reading; write header if file is new/empty."""
    need_header = (not os.path.isfile(path)) or (os.path.getsize(path) == 0)
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if need_header:
                w.writeheader()
            w.writerow({
                "timestamp": stamp,
                "ping_ms": "" if ping_ms is None else ("%.1f" % ping_ms),
                "down_mbps": "" if down_mbps is None else ("%.2f" % down_mbps),
            })
    except OSError as e:
        print("error: cannot write %s: %s" % (path, e), file=sys.stderr)
        return False
    return True


def build_parser(default_out=DEFAULT_OUT):
    p = argparse.ArgumentParser(description="Log ping latency + download speed to CSV.")
    p.add_argument("--host", default="1.1.1.1",
                   help="Host to ping (default: %(default)s).")
    p.add_argument("--url", default=DEFAULT_URL,
                   help="Download URL to time (default: Cloudflare 10 MB).")
    p.add_argument("--out", default=default_out,
                   help="Output CSV path (default: %(default)s).")
    p.add_argument("--rounds", type=int, default=0,
                   help="Rounds to run; 0 = infinite (default: %(default)s).")
    p.add_argument("--interval", type=float, default=300,
                   help="Seconds between rounds (default: %(default)s).")
    p.add_argument("--timeout", type=float, default=30,
                   help="Per-probe timeout in seconds (default: %(default)s).")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.rounds < 0:
        print("error: --rounds must be >= 0 (0 = infinite)", file=sys.stderr)
        return 2
    if args.interval < 0:
        print("error: --interval must be >= 0", file=sys.stderr)
        return 2
    if not args.host.strip():
        print("error: --host must not be empty", file=sys.stderr)
        return 2
    if not args.url.strip():
        print("error: --url must not be empty", file=sys.stderr)
        return 2

    pings = []  # last 20 ping readings for the sparkline
    round_no = 0
    try:
        while True:
            round_no += 1
            ping_ms, ping_note = ping_host(args.host, timeout=args.timeout)
            if ping_note:
                print(ping_note, flush=True)
            mbps, nbytes, secs, dl_err = download_mbps(args.url, timeout=args.timeout)
            if dl_err:
                print("warning: %s" % dl_err, file=sys.stderr)
            if ping_ms is not None:
                pings.append(ping_ms)
                pings = pings[-20:]
            if not append_csv(args.out, ping_ms, mbps):
                return 1
            ping_s = "n/a" if ping_ms is None else ("%.1f ms" % ping_ms)
            dl_s = "n/a" if mbps is None else ("%.2f Mbps (%d bytes in %.1fs)" % (mbps, nbytes, secs))
            print("round %d: ping %s | down %s -> %s" % (round_no, ping_s, dl_s, args.out), flush=True)
            print("ping sparkline: %s" % sparkline(pings), flush=True)
            if args.rounds and round_no >= args.rounds:
                break
            if args.interval > 0:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped by user after %d round(s); csv -> %s" % (round_no, args.out))
        return 0
    print("done: %d round(s); csv -> %s" % (round_no, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
