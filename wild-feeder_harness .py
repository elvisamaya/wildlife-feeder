#!/usr/bin/env python3
# last edited: 2025-07-13
"""
Test harness for wildlife feeder v2 (ATmega328 + HC-SR501 PIR).

Connects over serial, timestamps incoming lines, optionally logs to CSV.
Simulate mode replays a recorded session for CI / offline testing.

Usage:
    python feeder_harness.py --port /dev/tty.usbmodem1101
    python feeder_harness.py --port COM3 --baud 115200 --csv run_001.csv
    python feeder_harness.py --simulate --interval 4 --count 8
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
import random
import sys
import time
from pathlib import Path

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

LOG_FORMAT = "%(asctime)s  %(levelname)-7s  %(message)s"
DATE_FORMAT = "%H:%M:%S"

logging.basicConfig(format=LOG_FORMAT, datefmt=DATE_FORMAT, level=logging.DEBUG)
logger = logging.getLogger("feeder")

# Firmware emits lines like:
#   [BOOT] fw=0.4.1 chip=328P
#   [PIR]  state=1 raw=847 thresh=600
#   [FEED] motor_ms=400 qty=1
#   [INFO] cooldown_s=30 uptime=00:01:42
# Keep these in sync with feeder.ino LOG_* macros.
_SIM_BOOT = [
    "[BOOT] fw=0.4.1 chip=328P",
    "[INFO] pir_warmup_s=30 ... skipping in test mode",
    "[INFO] thresh=600 cooldown_s=30",
    "[INFO] armed",
]

_SIM_CYCLE = [
    "[PIR]  state=1 raw={raw} thresh=600",
    "[FEED] motor_ms=400 qty=1",
    "[INFO] dispense_ok=1",
    "[INFO] cooldown_s=30 uptime={uptime}",
    "[PIR]  state=0 raw={raw2} thresh=600",
    "[INFO] armed",
]

# TODO: add --filter flag to grep for specific tags (PIR, FEED, ERR)
# TODO: wire up --replay <csv> to re-emit a previous session for regression


def _open_csv(path: str) -> tuple[object, object]:
    """Open CSV for append, write header if new. Raises on permission error."""
    p = Path(path)
    write_header = not p.exists() or p.stat().st_size == 0
    fh = open(p, "a", newline="", encoding="utf-8")
    writer = csv.writer(fh)
    if write_header:
        writer.writerow(["timestamp_iso", "elapsed_ms", "source", "raw"])
    return fh, writer


def run_serial(port: str, baud: int, csv_path: str | None) -> None:
    if serial is None:
        logger.error("pyserial not installed — run: pip install pyserial")
        sys.exit(1)

    csv_fh = csv_writer = None
    if csv_path:
        try:
            csv_fh, csv_writer = _open_csv(csv_path)
            logger.info("logging to %s", csv_path)
        except OSError as exc:
            logger.error("cannot open csv %s: %s", csv_path, exc)
            sys.exit(1)

    t0 = time.monotonic()

    try:
        with serial.Serial(port, baud, timeout=1) as ser:
            logger.info("opened %s @ %d baud", port, baud)
            while True:
                raw = ser.readline()
                if not raw:
                    continue

                elapsed_ms = int((time.monotonic() - t0) * 1000)

                try:
                    line = raw.decode("utf-8", errors="replace").strip()
                except Exception:
                    line = repr(raw)

                if not line:
                    continue

                # surface ERR lines louder
                level = logging.WARNING if line.startswith("[ERR]") else logging.INFO
                logger.log(level, "[%6d ms]  %s", elapsed_ms, line)

                if csv_writer:
                    csv_writer.writerow([
                        dt.datetime.now().isoformat(timespec="milliseconds"),
                        elapsed_ms,
                        "hw",
                        line,
                    ])
                    csv_fh.flush()

    except serial.SerialException as exc:
        logger.error("serial error: %s", exc)
    except KeyboardInterrupt:
        logger.info("interrupted — %.1f s elapsed", time.monotonic() - t0)
    finally:
        if csv_fh:
            csv_fh.close()


def run_simulation(interval: float, count: int, csv_path: str | None) -> None:
    csv_fh = csv_writer = None
    if csv_path:
        try:
            csv_fh, csv_writer = _open_csv(csv_path)
            logger.info("logging to %s", csv_path)
        except OSError as exc:
            logger.error("cannot open csv %s: %s", csv_path, exc)
            sys.exit(1)

    t0 = time.monotonic()

    def emit(line: str, source: str = "sim") -> None:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        level = logging.WARNING if line.startswith("[ERR]") else logging.INFO
        logger.log(level, "[%6d ms]  %s", elapsed_ms, line)
        if csv_writer:
            csv_writer.writerow([
                dt.datetime.now().isoformat(timespec="milliseconds"),
                elapsed_ms,
                source,
                line,
            ])
            csv_fh.flush()

    try:
        logger.info("starting simulation — %d cycles @ %.1fs interval", count, interval)

        for line in _SIM_BOOT:
            emit(line)
            time.sleep(0.15)

        uptime_s = 5  # rough seconds since boot after warmup skip
        for i in range(count):
            jitter = random.uniform(-0.3 * interval, 0.3 * interval)
            sleep_s = max(0.5, interval + jitter)
            logger.debug("cycle %d/%d — waiting %.2fs", i + 1, count, sleep_s)
            time.sleep(sleep_s)
            uptime_s += int(sleep_s)

            raw_val  = random.randint(780, 920)
            raw_val2 = random.randint(100, 300)
            uptime_str = time.strftime("%H:%M:%S", time.gmtime(uptime_s))

            for tmpl in _SIM_CYCLE:
                line = tmpl.format(raw=raw_val, raw2=raw_val2, uptime=uptime_str)
                emit(line)
                time.sleep(0.1)
            uptime_s += 1

        logger.info("simulation done — %.1f s total", time.monotonic() - t0)

    except KeyboardInterrupt:
        logger.info("interrupted at cycle — %.1f s elapsed", time.monotonic() - t0)
    finally:
        if csv_fh:
            csv_fh.close()


def _list_ports() -> None:
    if serial is None:
        print("pyserial not installed")
        return
    ports = sorted(serial.tools.list_ports.comports())
    if not ports:
        print("no serial ports found")
        return
    for p in ports:
        print(f"  {p.device:<20} {p.description}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="feeder serial harness",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--port", help="serial port (e.g. /dev/tty.usbmodem1101, COM3)")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--csv", metavar="FILE", help="append events to CSV")
    parser.add_argument("--simulate", action="store_true", help="offline sim, no hardware needed")
    parser.add_argument("--interval", type=float, default=3.0, help="mean seconds between motion events (sim only)")
    parser.add_argument("--count", type=int, default=3, help="number of motion cycles (sim only)")
    parser.add_argument("--list-ports", action="store_true", help="print available serial ports and exit")
    parser.add_argument("--quiet", action="store_true", help="suppress DEBUG lines")

    args = parser.parse_args()

    if args.list_ports:
        _list_ports()
        sys.exit(0)

    if not args.simulate and not args.port:
        parser.error("provide --port or use --simulate (--list-ports to see available ports)")

    if args.quiet:
        logging.getLogger().setLevel(logging.INFO)

    return args


def main() -> int:
    args = parse_args()
    if args.simulate:
        run_simulation(args.interval, args.count, args.csv)
    else:
        run_serial(args.port, args.baud, args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
