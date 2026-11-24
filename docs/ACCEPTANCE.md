# Final acceptance: what is verified, and your wireless checklist

Nothing below needs a USB cable. Date of the run: 2026-11-23. The PC was not rebooted, no Windows startup setting was changed and no credential was rotated during this run (the pairing code had been rotated earlier at your request).

## A. Verified results (measured on your PC and your Galaxy A10)

| # | Check | Result |
| --- | --- | --- |
| 1 | **Several displays at different power modes at once** (4 test displays + your phone, 90 s) | Each got exactly its own pace. Stats every **1.0 s** (Normal), **5.1 s** (Eco), **15.3 s** (Battery saver), **≥60 s** (dark clock). Media **1.0 / 3.0 / 5.1 / 30.1 s**. Internet **2.0 / 10.2 / 30.1 / ≥60 s**. The Normal display was not slowed by the slow ones. |
| 2a | **Wi-Fi drop, Normal mode** (simulated: all packets silently dropped, connection left open) | Noticed at 11 s; hung attempts abandoned after 10 s; online again 1–2 s after the link came back. |
| 2b | **Wi-Fi drop, Eco mode** (same simulation, 45 s) | Noticed at about 23–30 s; back online about 10 s after the link returned. |
| 2c | **Connection reset** | Online again in 3 s. |
| 3 | **Companion killed hard** (no clean shutdown), then started the way Windows does at sign-in | **Nothing restarted it by itself** (0 processes, port closed after 25 s). Once started, **your real phone reconnected by itself 4 s later**, without reloading the page (it had been open 569 s), with fresh data. The next start was not blocked. |
| 4 | **Battery measurement without USB** | `tools/phone_monitor.py` works: it read your phone's battery (45% → 44% in 4 min, discharging), temperature, Chrome memory and the page's own health, once a minute, over Wi-Fi. |
| 5 | **Pairing code and logs** | The current code (22 random characters) appears in no log file and not in `config.toml`; its file is readable only by you, Administrators and SYSTEM. The old code is refused. |
| 6 | **Tests** | Whole suite: 33 test files pass; ESP32 board protocol check passes. |

The 30-minute extended-use run on your phone is reported in section E.

## B. Not verified (needs your hands, or your approval)

| Check | Why I could not do it |
| --- | --- |
| Lock screen → unlock | Locking the phone by remote control could leave it locked behind your PIN. Observed passively only (section E). |
| Phone Wi-Fi off and on | Turning the phone's Wi-Fi off would cut the wireless link I use, and I could not turn it back on. |
| Windows sleep and wake | Putting this PC to sleep ends my session. |
| Real Android browser suspend (app switch, long idle) | Needs real use of the phone. |
| PC reboot / first sign-in after reboot | Not allowed without your approval. |
| Battery drain Eco vs Battery saver | Needs hours on a fixed brightness. The tool is ready (below). |
| Hours-long use of the A10's browser | I could only observe the minutes the phone stayed on during this run. |
| Real ESP32 board | None here. |

## C. Pairing-token security and the risk of your shortcuts

**The pairing code**
* 22 random characters (128 bits), compared in constant time, 8 wrong tries a minute per address, then blocked. Pages from other websites cannot use it.
* It is kept in `%USERPROFILE%\.deskhub\web_token` (readable only by you, Administrators, SYSTEM), and on the phone in the browser's saved data for the dashboard address. Anyone who can unlock your phone and open that browser can use it.
* It travels in clear text over your Wi-Fi (plain HTTP, like the original DeskHub). Risk: someone on your Wi-Fi who can read its traffic could copy it.
* It never expires and is the same for every phone. A lost or sold phone means replacing the code for everyone: `uv run python -m deskhub --new-token`, restart the companion, scan again.
* It is not logged. What a holder can see: now playing, calendar, AI usage, weather place, game names, your GitHub login if set up. They can press the shortcut tiles below.

**Your 8 shortcut tiles** (what a phone with the code can trigger; a phone can send only the tile's number, never a command line):

| Tile | What happens on the PC | Worst case |
| --- | --- | --- |
| Mute mic, Mute sound, Vol −, Vol + | Changes Windows audio | Annoying; muting the mic silently during a call |
| Screenshot | Presses Win+Shift+S | The snipping overlay appears; harmless |
| **Terminal** | Opens Windows Terminal (`wt.exe`) | A terminal window opens on your screen. The phone cannot type into it, so this alone cannot run commands. It matters only if someone is at the PC. |
| Downloads | Opens your Downloads folder | Shows the folder on your screen (no way to read files from the phone) |
| Lock PC | Locks Windows | Interrupts you. It cannot unlock. |

Overall: a leaked code lets someone read what the dashboard shows and annoy you. It does not give remote command execution, file access or an unlock. The one tile I would reconsider is **Terminal**, if other people can see your screen. Anyone who can edit `config.toml` on the PC can of course define a `run` tile with any command, which is a local-file risk, not a phone risk.

Not built (and not needed unless you want it): per-tile confirmation on the phone, per-phone codes, expiring codes, HTTPS.

## D. If the companion process dies

**Before:** a killed companion stayed down until the next sign-in. **Now (added at your request, option A):** when started hidden with `--tray` — exactly what your unchanged Startup shortcut does — a small guardian runs the companion and restarts it. Verified on the real companion:

| Check | Result |
| --- | --- |
| Kill the companion hard (like a crash or "End task") | Dashboard down **2.3 s**, answering again **3.4 s** after the kill. The guardian log shows the exit code and the restart. |
| Start a second copy while it runs | Refused ("already running"). |
| Kill only the guardian | The companion stops by itself **3.8 s** later; no orphan, port 8790 free. |
| Clean Quit / tray Restart / growing pauses / long-run reset / "already running" | Covered by `tests/test_guardian.py` (fake and real processes). |
| Whole suite and the ESP32 board check | Pass. |
| Startup shortcut | Unchanged. Memory cost of the guardian: about 25 MB (its launcher and itself). |

Not verified live (needs the tray icon, see checklist test 8): the tray's **Quit** and **Restart** buttons.

Rules: exit code 0 (tray Quit) ends everything; the Restart code restarts at once; anything else restarts after 2 s, then 4, 8 … up to 5 minutes between tries if it keeps failing, starting over after a 2-minute run. Turn it off with `--no-guardian`.

## E. Extended use and battery (the 30-minute monitor)

I ran the monitor from 22:52 to 23:09 (17 rows, `acceptance_phone_log.csv`), stopping it early because the phone's screen turned itself off. What it recorded on your real A10, discharging the whole time:

* **Screen on, dashboard connected, Eco mode: 10 minutes (22:52–23:02).** The page's JavaScript memory stayed flat at 9.5 MB; Chrome's total memory went 116 → 112 MB; the companion used 1.3–2.4% of one core. No reconnects were needed except the one caused by my deliberate crash test (the monitor shows the single "companion unreachable" row at 22:57, and the page recovered with no reload).
* **The screen then timed out by itself at about 23:03** (Android's 10-minute screen timeout; "stay awake" is off). The dashboard disconnected on purpose and Chrome released about 10 MB (112 → 102 MB). This is the passive "screen off" observation. I could not observe the unlock side, which needs you (test 1).
* **Battery:** 45% → 43% in 16 minutes (about 10 minutes screen on, 6 minutes screen off). The phone reports whole percents only, so this is far too coarse to rank Eco against Battery saver: that needs the one-hour runs in section F.
* **What this does *not* show:** hours of use on the A10. The screen timeout ends a hands-off run after 10 minutes, so that test needs you to touch the phone or enable "Keep screen on" (section F, battery runs).

The monitor tool had one flaw this run exposed: after the companion was restarted it kept reading the dead process (showing 0.00% CPU). Fixed; the CSV above still has the flat 0.00 rows after 22:58, so ignore the companion CPU column from then on.

## F. Your wireless checklist

Do these in order. Total about 40 minutes plus the battery runs. All steps use only the phone's touchscreen and this PC.

### Preparation (once)
1. On the phone: Settings → Developer options → **Wireless debugging** on. Note the **IP address & Port** (changes when you switch it off and on; pairing stays). Optional but useful: it lets the monitor read the battery.
2. On the PC, a PowerShell window to watch connections live (leave it open):
   ```powershell
   Get-Content "$env:USERPROFILE\.deskhub\companion.log" -Wait -Tail 0
   ```
   You will see lines like `[web 192.168.1.42] connected (low power)` and `disconnected after 183 s`, each with a time.
3. In a second PowerShell window, start the monitor (60 minutes; replace the address):
   ```powershell
   cd "C:\Users\atana\Music\DAILY THINNGS\deskhub-a10\companion"
   uv run python ..\tools\phone_monitor.py --minutes 60 --adb 192.168.1.42:40967 --out ..\phone_log.csv
   ```
4. On the phone open the dashboard and leave it in the mode you are testing (Settings → Power).

### Tests (tick each; "log" means the live window from step 2)
| # | Do | Expect | Pass if |
| --- | --- | --- | --- |
| 1 | Lock the phone (power button). Wait 2 min. Unlock. | log: `disconnected` within seconds of locking; `connected` within seconds of unlocking. Fresh numbers on screen. | Back online in 10 s or less, no tap needed. |
| 2 | Open another app for 3 min. Come back. | Same as 1. | Same. |
| 3 | Turn the phone's Wi-Fi off for 30 s, then on. | Dashboard shows "PC not reachable" while off. | Online again within 45 s of Wi-Fi returning, no tap. |
| 4 | PC: Start → Power → Sleep. Wake it after 2 min. | The phone shows "PC not reachable" while the PC sleeps. | Online again within 60 s of the PC waking (Windows has to reconnect its Wi-Fi first). |
| 5 | Phone in Battery saver: watch the numbers. | They change about every 15 s, nothing moves in between. | Yes. |
| 6 | Tap a harmless tile (Vol +). | Volume changes on the PC at once. | Yes. |
| 8 | Tray icon near the clock → **Restart**. Then, later, tray icon → **Quit**. | Restart: the dashboard blinks and is back in a few seconds. Quit: it stays off (the guardian ends too). | Yes. (Start it again with the Startup shortcut or at the next sign-in.) |
| 9 | Task Manager → "End task" on the big `pythonw.exe` (about 110 MB). | The guardian starts a new one within about 3 s and the phone reconnects. | Yes. |
| 7 | **Only with your OK:** restart the PC, sign in, wait 2 min. | The companion is running and the phone reconnects with no action from you. | Yes; otherwise send me `companion.log`. |

### Battery runs (the real answer to "which mode is best")
1. Unplug the phone. Same brightness (say 30%), same screen timeout, Wi-Fi on, nothing else open.
2. To keep the screen on without touching it, one-time and optional: in the phone's Chrome open `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, add `http://192.168.1.25:8790`, set it to Enabled, relaunch Chrome. Then Settings → **Keep screen on: yes** on the dashboard. (Otherwise Android turns the screen off after the screen timeout; touch it every few minutes.)
3. Run the monitor for 60 minutes in **Eco**, note `battery X% -> Y%` at the end. Repeat for 60 minutes in **Battery saver**. Compare %/hour. The screen will dominate both.
4. In `phone_log.csv` look for a slowly rising `page_heap_mb` or `chrome_pss_mb` (a leak) and for `reconnects` increasing without a reason.

### If something fails
* `http://localhost:8790/diag` on the PC shows connected displays, their mode, last errors and the compatibility test.
* No reconnect after a PC wake: check the PC's address is still `192.168.1.25`; if not, give the PC a fixed address in the router and pair again at `http://localhost:8790/setup`.
* The log file is `%USERPROFILE%\.deskhub\companion.log`.
