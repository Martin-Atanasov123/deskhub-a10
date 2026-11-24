"""Log the phone's battery and the dashboard's health over time, wirelessly (no USB).

    cd companion
    uv run python ..\\tools\\phone_monitor.py --minutes 60 --adb PHONE_IP:PORT --out ..\\phone_log.csv

Each minute it writes one CSV row with:
  * from the PC: is the phone connected, its power mode, which page is open, whether the page is visible,
    how many times it reconnected, the page's JavaScript memory, and how long the page has been up;
  * from the phone over Wi-Fi debugging (only with --adb; read-only): battery %, charging or not,
    temperature, voltage, Chrome's memory and recent CPU (blank CPU = Chrome was too quiet to be listed);
  * the companion's own CPU and memory on this PC.
Without --adb the battery columns stay empty. If the phone disappears for a while the rows say so and logging goes on.
"""
import argparse
import csv
import json
import re
import subprocess
import time
import urllib.request

import psutil

STATUS = {"1": "unknown", "2": "charging", "3": "discharging", "4": "not charging", "5": "full"}


def adb(target, *args, timeout=25):
    try:
        r = subprocess.run(["adb", "-s", target, *args], capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def phone_numbers(target):
    out = {}
    try:   # re-connect every time: the link drops whenever the phone's Wi-Fi sleeps
        subprocess.run(["adb", "connect", target], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return out
    bat = adb(target, "shell", "dumpsys", "battery")
    if bat:
        g = lambda k: (re.search(rf"^\s*{k}: (\S+)", bat, re.M) or [None, ""])[1]
        out["battery_pct"] = g("level")
        plugged = any(g(k) == "true" for k in ("AC powered", "USB powered", "Wireless powered")) or \
            re.search(r"(AC|USB|Wireless) powered: true", bat) is not None
        out["charging"] = STATUS.get(g("status"), g("status")) + (" (plugged in)" if plugged else "")
        t = g("temperature")
        out["temp_c"] = f"{int(t) / 10:.1f}" if t.isdigit() else ""
        out["voltage_mv"] = g("voltage")
    mem = adb(target, "shell", "dumpsys", "meminfo", "com.android.chrome")
    m = re.search(r"TOTAL PSS:\s+(\d+)", mem)
    out["chrome_pss_mb"] = f"{int(m.group(1)) / 1024:.0f}" if m else ""
    cpu = adb(target, "shell", "dumpsys", "cpuinfo")
    pct = [float(x) for x in re.findall(r"^\s*([\d.]+)% \d+/com\.android\.chrome", cpu, re.M)]
    out["chrome_cpu_pct"] = f"{sum(pct):.1f}" if pct else ""
    return out


def companion_procs():
    out = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        if "-m deskhub" in " ".join(p.info["cmdline"] or []) and (p.info["name"] or "").lower() in ("python.exe", "pythonw.exe"):
            out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--minutes", type=float, default=60)
    ap.add_argument("--interval", type=float, default=60, help="seconds between rows")
    ap.add_argument("--adb", help="the phone's Wireless debugging address, e.g. PHONE_IP:PORT (optional)")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--out", default="phone_log.csv")
    a = ap.parse_args()

    cols = ["time", "phone_connected", "mode", "page", "visible", "reconnects", "page_heap_mb", "page_up_s", "page_msgs",
            "battery_pct", "charging", "temp_c", "voltage_mv", "chrome_pss_mb", "chrome_cpu_pct",
            "companion_cpu_pct", "companion_rss_mb"]
    procs = companion_procs()
    for p in procs:
        p.cpu_percent(None)
    rows = []
    end = time.time() + a.minutes * 60
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        while True:
            row = {c: "" for c in cols}
            row["time"] = time.strftime("%H:%M:%S")
            try:   # the PC's own browser address is trusted, so no pairing code is needed here
                d = json.load(urllib.request.urlopen(f"http://127.0.0.1:{a.port}/api/diag", timeout=5))
                phones = [c for c in d["clients"] if not c["ip"].startswith("127.")]
                row["phone_connected"] = "yes" if phones else "NO"
                if phones:
                    i = phones[0]["info"]
                    row.update(mode=phones[0]["mode"], page=i.get("page", ""), visible=i.get("visible", ""),
                               reconnects=i.get("reconnects", ""), page_heap_mb=i.get("heap_mb", ""),
                               page_up_s=i.get("up_s", ""), page_msgs=i.get("msgs", ""))
            except (OSError, ValueError):
                row["phone_connected"] = "companion unreachable"
            if a.adb:
                row.update(phone_numbers(a.adb))
            current = companion_procs()
            if {p.pid for p in current} != {p.pid for p in procs}:   # the companion was restarted: follow the new one
                procs = current
                for p in procs:
                    p.cpu_percent(None)
            else:
                try:
                    row["companion_cpu_pct"] = f"{sum(p.cpu_percent(None) for p in procs):.2f}"
                except psutil.Error:
                    pass
            try:
                row["companion_rss_mb"] = f"{sum(p.memory_info().rss for p in procs) / 2**20:.0f}"
            except psutil.Error:
                pass
            w.writerow(row)
            f.flush()
            rows.append(row)
            print(" | ".join(f"{k}={row[k]}" for k in ("time", "phone_connected", "mode", "visible", "page_heap_mb", "battery_pct", "charging",
                                                        "chrome_pss_mb", "companion_cpu_pct") if row[k] != ""), flush=True)
            if time.time() + a.interval > end:
                break
            time.sleep(a.interval)

    n = len(rows)
    up = sum(1 for r in rows if r["phone_connected"] == "yes")
    print(f"\n{n} rows in {a.out}; the phone was connected in {up} of them.")
    lv = [int(r["battery_pct"]) for r in rows if str(r["battery_pct"]).isdigit()]
    if len(lv) >= 2:
        hours = (n - 1) * a.interval / 3600
        print(f"battery {lv[0]}% -> {lv[-1]}% in {hours:.2f} h" + (f" = {(lv[0] - lv[-1]) / hours:.1f} %/hour" if hours else ""))
    hp = [float(r["page_heap_mb"]) for r in rows if str(r["page_heap_mb"]).replace(".", "", 1).isdigit()]
    if len(hp) >= 2:
        print(f"page JavaScript memory {hp[0]} MB -> {hp[-1]} MB (max {max(hp)})")


if __name__ == "__main__":
    main()
