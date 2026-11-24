# Final reliability and optimization audit (2026-11-23)

Everything here was done wirelessly. The phone was only read (battery, memory, CPU) over Wi-Fi debugging, with no taps.
Results are kept in four groups, so you can see what was **measured**, what was only **simulated**, what is an **assumption**, and what **needs you**.

## 1. Measured (real numbers from this PC, 12 logical cores)

### The Windows companion (hidden `pythonw`, started by the Startup shortcut)

| Situation | CPU (share of one core) | Memory (RSS) |
| --- | --- | --- |
| Before this audit, phone connected in Eco | 2.21% avg (peak 3.9%) | 127.8 MB |
| After, phone connected in Eco | **1.08%** | 97–118 MB |
| After, no display connected | **0.57%** (0.05% of the whole CPU) | 103 MB |
| After, one extra display in Normal (full speed on purpose) | 2.62% | 117 MB |

The remaining 0.57% when idle is the internet monitor (it pings every 2 s on purpose, to record outages), the tray, the power watcher and the periodic calendar and weather refreshes.

### What a display receives (payload of the WebSocket messages, 60 s, real data)

| Power mode | Messages | Data | Rate |
| --- | --- | --- | --- |
| Normal | 2.78 /s | 51.1 KB/min | 871 B/s |
| Eco | 0.87 /s | 16.7 KB/min | 284 B/s |
| Battery saver (new) | 0.50 /s | 9.9 KB/min | 168 B/s |

(The first seconds include the one-off state snapshot of about 6 KB. TCP/WebSocket framing is not counted.)

### The dashboard itself (desktop Chrome, 760×340 window, real server, Home page, 30 s windows)

| Power mode | Timer wake-ups per minute (before → after) | Screen redraws/min | Messages/min | Data/min |
| --- | --- | --- | --- | --- |
| Normal | 133 → **34** | 694 | 136 | 35 KB |
| Eco | 123 → **22** | 176 | 40 | 9.3 KB |
| Battery saver | 123 → **22** | 78 | 20 | 4.8 KB |

DOM size stayed at 267 nodes throughout; JavaScript heap grew by 12–124 KB per minute in these short windows (garbage not yet collected; no sustained growth seen).
These numbers show *relative* work between modes. They are not the A10's absolute cost.

### Leak soak (8 minutes)

244 display connect/disconnect cycles, 3 850 messages, power-mode changes at random. Companion memory 98.5 → 100.2 MB (range 97.3–101.7, noise), handles 437 → 441 (max 442), threads 15 → 14. The server ended with only your phone counted as connected, so no display entries leaked.

### The phone (read only, one instant, **on the charger at 45%**)

Chrome total memory about 97 MB (all of Chrome's processes, 6 tabs, not only the dashboard); the busiest Chrome renderer used about 5% CPU in the last interval; the whole phone 4.1%. Not isolated to the dashboard, and the battery drain could not be measured because the phone was charging.

### Tests

The whole suite (`uv run python tests/run_all.py`) passes: **33 test files, 0 failures**, including the new ones for the supervisor and pacing, the web server, the hardening rules, weather, game covers and the old-browser syntax guard. The ESP32 protocol check (`tests/fake_hub.py`) passes separately, as it is not part of that runner.

## 2. Verified by simulation (a desktop browser stands in for Android)

| Scenario | Result |
| --- | --- |
| Link silently stalls (packets dropped, connection stays open) | Detected at 11 s in Normal (limit 12 s; Eco 30 s, Battery saver 60 s, dark clock 150 s). Back online 1–2 s after the link returned. |
| Connection reset | Back online in 3 s. |
| A connection attempt that never answers (half-dead Wi-Fi) | **Bug found and fixed:** the page stayed on "connecting" until something else happened. Now abandoned after 10 s and retried with growing pauses. |
| Page suspended (timers jump 90 s) | Detected ("timers were paused for 95 s") and the connection is re-checked. In this simulation the socket was actually healthy, so no reconnect was needed. |
| Companion restarted while the page is open | Page reconnected by itself (M1 test, and today when the hidden copy started: your phone was back after about 2 s). |
| Page hidden / shown | Closes the connection when hidden, reconnects when shown (logic present; the real Android lock screen is in section 4). |

## 3. Fixed or added in this audit

* **Background loops that could silently die.** The stats, calendar and printer loops had no error handling: one unexpected error and that loop stayed dead until the program restarted. Every loop is now supervised and restarted with a growing pause (`supervise.py`).
* **Polling nobody looks at.** The loops polled Windows every second even with no display. They now rest while nobody is connected, wake the instant a display connects, and follow the slowest connected display's power mode (the ESP32 board always gets full speed; Claude waiting-alerts keep their pace).
* **Battery saver mode** (Settings → Power): stats every 15 s, media every 5 s, nothing moves between updates, 60 s staleness limit, no progress-bar timer.
* **Fewer messages and less drawing.** Identical messages are not repeated; a 4/10/20/60 s heartbeat tells a quiet link from a dead one; pages that are not on screen are not redrawn (they catch up when opened); timers for the media bar, Settings, Games clock and the countdown run only while their page is open.
* **Recovery after suspend.** Connection attempt timeout (above), the "gone quiet" clock starts at connect, page `freeze`/`resume` events, network-change event, and a suspend detector (timers that fire 20 s late).
* **Diagnostics.** Bytes sent per display, bytes and messages received and JavaScript heap on the phone are visible on `/diag` and in Settings.
* **Security** (section 6).

## 4. Needs you (physical interaction; I did not do these)

Do them in this order. After each one tell me, and I will read the PC's log to confirm the timing. Nothing here needs a cable.

1. **Lock the phone for 2 minutes, then unlock.** Expected: the log shows `disconnected` within seconds of locking and `connected` within about 3 s of unlocking, and the numbers are fresh.
2. **Leave the browser for another app for 3 minutes, then come back.** Same expectation.
3. **Switch Wi-Fi off for 30 s, then on** (or Airplane mode). Expected: back within a few seconds of Wi-Fi returning.
4. **Settings → Battery saver.** Check that numbers refresh about every 15 s and the page stays responsive.
5. **Put the PC to sleep, wake it.** Expected: the dashboard says "PC not reachable" while asleep and recovers within seconds of waking.
6. **Battery comparison (unplug the phone):** one hour in Eco, one hour in Battery saver, same brightness, same screen timeout. Note the battery % at start and end. Brightness and screen-on time will dominate, as explained in LIMITATIONS.
7. **Restart the PC (only with your approval).** Expected: within 1–2 minutes of signing in the companion is running and the phone reconnects. If not, `%USERPROFILE%\.deskhub\companion.log` will say why.

## 5. Auto-start (Windows)

Verified now: the shortcut `Desk Hub companion.lnk` is in your Startup folder; its target `…\.venv\Scripts\pythonw.exe`, working folder and `config.toml` all exist; it starts minimized, hidden. I started it the way Windows does and it ran, served the dashboard and wrote its log. The Wi-Fi is on the **Private** profile and the firewall rule (port 8790, Private, local subnet) exists.

Not tested (needs a real sign-in, so a restart):
* whether the companion starts before the Wi-Fi is connected at login. By design it should cope: it listens on all addresses, and weather, calendar and Steam retry on their own.
* the tray icon, which Windows may not accept if the companion starts before the taskbar exists. The program continues without it.
* Windows Fast Startup behaviour after "Shut down" versus "Restart".
* the Wi-Fi adapter's power-saving setting: Windows would not let me read it.
* (Resolved after this audit.) The whole process had no restarter: a crash left it down until the next sign-in. A guardian was added for hidden starts, see ACCEPTANCE.md section D.
* if the project folder is moved or its `.venv` deleted, the shortcut stops working (run `uv run deskhub-install` again).

## 6. Security audit: LAN authentication and remote shortcuts

What was already sound: the pairing code is compared in constant time; a phone can send only six message types (`media`, `shortcut`, `speedtest`, `steam_launch`, `alert_action`, and `ai_agent`, added later: it only picks which agent the AI page shows) and never a command line (a shortcut is a *number*; the PC looks up what it does in `config.toml`); `steam_launch` only accepts games Steam just reported; message sizes are capped; the web files hold no secrets.

Found and fixed:

| Finding | Fix |
| --- | --- |
| Unlimited guessing of the pairing code | 8 wrong codes per minute per address, then refused for the rest of the minute. |
| Any website could try to open the dashboard's WebSocket from a browser on your network | The `Origin` of a connection must be the dashboard's own address. |
| The PC's no-code trust for `localhost` (and the `/setup` page with the code) could be reached by a web page via DNS rebinding | Trust only applies when the `Host` header names `localhost`/`127.0.0.1`. |
| Dashboard could be shown inside another site's frame (clickjacking the shortcut buttons) | `X-Frame-Options: DENY` and `frame-ancestors 'none'`. |
| A display could flood commands | 30 commands per 10 s per display. |
| Anyone could fill the diagnostics store with fake compatibility reports | Capped at 20. |
| The pairing code was written to the log file | The log now shows the address without the code; the code goes only to a console and to `http://localhost:8790/setup`. **Older log lines from earlier runs still contain the old code.** |
| Short code (12 characters) | New installs get 22 characters. Replace yours any time with `uv run python -m deskhub --new-token` (then restart; every phone must pair again). |

Remaining risks you should know about (not fixed; they follow from "plain HTTP, no app"):
* Traffic is not encrypted. Someone who is on your Wi-Fi *and* can read its traffic could see the pairing code. Keep untrusted devices off the network the PC and phone share.
* A paired phone can trigger **every** shortcut tile you configured (your current tiles include opening a terminal, a screenshot and locking the PC). There is one code for all phones; revoking means replacing it.
* The server listens on all of the PC's network adapters (including the VirtualBox and WSL ones), protected by the Windows rule that allows only the Private profile and the local subnet.
* Weather, Steam art and the optional speed test contact outside services from the PC, as configured.

Consider replacing the pairing code once: the old one appeared in earlier log lines and in this conversation.

## 7. Original ESP32 compatibility

The board protocol test (`tests/fake_hub.py` against the companion with a `[hub]` section) still passes: layout, home, tiles, events, AI, Steam, covers, stats and media all arrive, with stats and media at the original 1 per second. The only addition for a board is a `weather` message, which the firmware ignores. The new loop pacing never slows a connected board. Not tested on real ESP32 hardware (none here).
