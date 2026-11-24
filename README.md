# DeskHub for the Galaxy A10 (browser display)

A fork of the Windows companion from [zacharyinserra/deskhub](https://github.com/zacharyinserra/deskhub) (MIT) that
shows the dashboard in a **phone browser over Wi-Fi** instead of on the ESP32 board. No cable, no app, no root.

Pages: **Home** (your configured grid: stats, now playing, up next, weather, AI usage, internet), **Stats**,
**AI** (plan limits, tokens, 7-day chart), **Calendar**, **Weather** (now, 24 hours, 6 days), **Media** (cover, seek, controls),
**Timer** (works without the PC), **Internet** (latency, outages, data, speed test), **Keys** (your shortcut buttons),
**Printer** (up to 4 printers: state, progress, temperatures, filament colours), **Games** (what you play on Steam with its cover,
recent games, tap to launch after a confirmation) and **GitHub** (a year of contributions, streaks, top repositories), plus **Settings**.
Everything works in portrait and landscape. In portrait, Home stacks its cards in reading order (two small ones per row,
wide ones across) and the navigation moves to the bottom.
Printer, Games and GitHub show up only when they are set up on the PC (`uv run deskhub-printers`, Steam installed or `[[games]]`,
`uv run deskhub-setup github`). The navigation follows the order of `[pages] enabled` in `config.toml`; with all pages on it scrolls,
so list only the pages you want.

**Weather is off until you choose a place**: add `[weather]` with `city = "Your city"` to `config.toml` (see `config.example.toml`)
and restart the companion. The PC fetches it from open-meteo.com, so the phone makes no internet requests.

## Start it (Windows PC)

```powershell
cd deskhub-a10\companion
copy config.example.toml config.toml
uv run python -m deskhub
```

It prints a QR code and an address like `http://192.168.1.25:8787/#t=...`. For a larger QR, open
`http://localhost:8787/setup` in the PC's browser.

**First time only: Windows Firewall.** Windows asks whether to let Python reach the network. Allow it on **Private**
networks only. If it didn't ask (or you clicked Cancel), run this once in an **administrator** PowerShell; it opens
the port for your home network only:

```powershell
New-NetFirewallRule -DisplayName "DeskHub web display" -Direction Inbound -Protocol TCP -LocalPort 8787 -Profile Private -RemoteAddress LocalSubnet -Action Allow
```

Use the same number as `port` in `config.toml` (default 8787). If another program already uses the port, the companion
now says so and refuses to start the display, instead of letting that program answer the phone; pick another `port`
and use the same number in the command above.

If your Wi-Fi is set to *Public* in Windows (*Settings → Network & internet → Wi-Fi → your network → Network profile type*), change it to Private.

### Start with Windows (optional)

```powershell
cd deskhub-a10\companion; uv run deskhub-install            # start hidden at sign-in, icon near the clock
cd deskhub-a10\companion; uv run deskhub-install --remove   # undo
```

It adds one shortcut, "Desk Hub companion", to your Startup folder. The companion then runs without a window; its log is
`%USERPROFILE%\.deskhub\companion.log`. The icon near the clock opens the config, shows the log, restarts or quits it.
If the project folder moves, run the install command again. A phone that is open on the dashboard reconnects by itself when the companion starts.

Started this way, the companion is **guarded**: a small watcher process (about 25 MB, log `%USERPROFILE%\.deskhub\guardian.log`) runs it and starts it again
a few seconds after a crash or an "End task" (2 s, then 4 s, 8 s... up to 5 minutes between tries if it keeps failing). The tray's **Quit** really quits and
**Restart** restarts at once. Ending the watcher also ends the companion. Run with `--no-guardian` to turn this off; a plain console start (no `--tray`) is not guarded.

## Open it on the phone (touchscreen only)

1. Phone and PC on the same Wi-Fi (not a guest network).
2. Scan the QR code with the camera (Samsung's camera reads QR codes), tap the link. Or type the address into the browser.
3. On the pairing screen you can run the **Compatibility test** first (`/compat`). It sends the phone's Android version, browser
   version, screen size, speed and whether each feature works to the PC. See it on the PC at `http://localhost:8787/diag`.
4. Settings → **Fullscreen**. Chrome menu → **Add to Home screen** to relaunch with one tap.
5. Battery: leave **Eco** on (the default). Read [docs/LIMITATIONS.md](docs/LIMITATIONS.md) for what a browser cannot do.

## Power use

| Mode | Phone gets | Use when |
| --- | --- | --- |
| Eco (default) | stats every 5 s, media every 3 s (play/pause and track changes are instant), internet every 10 s; no animations; clock refreshes every 20 s | on battery |
| Battery saver | stats every 15 s, media every 5 s, internet every 30 s, a heartbeat every 20 s; nothing moves between updates | long stretches on battery |
| Normal | everything at the PC's own rate (1 s) | charging |
| Dark clock (after 2/5/10 min without touch, or PC screen asleep, or night hours from `config.toml`) | almost nothing: updates every 30 to 120 s | automatic |

When the screen turns off or the page is hidden, the dashboard **disconnects** so the radio can sleep, and reconnects on return.

## Something wrong? (all fixes work wirelessly)

| Symptom | Try |
| --- | --- |
| Phone cannot open the address | Same Wi-Fi? Try the other addresses listed on `/setup`. Check the firewall step above. Router "client isolation" / guest networks block phone-to-PC traffic. |
| "wrong code" | Scan the QR code again, or type the code from `%USERPROFILE%\.deskhub\web_token` on the PC. |
| Stuck or old page | Reload in the browser. The page asks for no caching, so a reload gets the newest version. |
| Want to start over | Settings → **Forget this PC**, then scan again. Or Chrome → Settings → Site settings → clear this site's data. |
| What does the PC see? | `http://localhost:8787/diag`: phones, power mode, last data age, errors from the phone, compatibility results. The companion log (`%USERPROFILE%\.deskhub\companion.log` when started hidden) has the same events. |
| Address changed after a router restart | Reserve an address for the PC in the router; or scan the new QR code. |

The companion follows the slowest connected display: when only a phone in Eco or Battery saver is connected, the PC polls Windows less often too,
and with nobody connected its loops rest (they wake the moment a display connects). The ESP32 board always gets full speed.

## Security in short

* Pairing needs the code in the QR address (22 random characters for new installs). Five message types can come back from a phone and nothing else:
  the PC looks up what a shortcut does in `config.toml` by its number, so a phone can never send a command line.
* Wrong codes are blocked after 8 tries a minute per address; pages from other websites cannot connect; the PC's own no-code trust
  applies only to requests that really address `localhost`; pages cannot be framed.
* Traffic is plain HTTP on your Wi-Fi, like the original DeskHub. Anyone who is on your Wi-Fi *and* can read its traffic could see the code, so do not
  put untrusted devices on the network the PC and phone share.
* New code (every phone must pair again): `uv run python -m deskhub --new-token`, then restart the companion. Details: [docs/AUDIT.md](docs/AUDIT.md).

## What changed from upstream

* `companion/deskhub/web_server.py` (new): HTTP + WebSocket server, pairing, power-mode throttling, diagnostics.
* `companion/deskhub/web/` (new): the dashboard (plain JavaScript, no build step): `ui.js` (shared toolkit: bars, rings, tweens,
  skeletons), `app.js` (connection, power, navigation, Home, Settings), `pages.js` (Stats, AI, Calendar, Weather, Media, Shortcuts, Timer)
  and `devices.js` (Printer, Games, GitHub), `homeedit.js` (the Home editor), plus `/compat` and `/diag`. `demo.js` only loads with `?demo=1`.
* **Customizable Home**: tap the pencil next to the date (or Settings → Home screen). Landscape: drag a card to move it (drop on a card of the
  same size to swap), drag its corner to resize, ✕ removes it, **+ Add** brings back any card, and Cols/Rows change the grid (3–6 by 2–4). Portrait:
  the cards stack in reading order, so each has ▲ ▼ arrows. The clock bar can be switched off. The layout is saved on that phone only; **PC layout**
  (tap twice) goes back to the `[home]` grid from `config.toml`.
* The look follows the upstream screenshots (same cards, colours and layouts). The Claude Code and Codex pages share one layout and differ
  only in accent colour and logo (the logos are simple drawings, not the official artwork). Motion: pages slide and fade, a pill glides
  between tabs, cards rise in, bars and rings animate, numbers count, and cards show a shimmer until data arrives. Only transform, opacity
  and tiny widths animate. Settings → Animations picks Full, Minimal or Off (a phone set to "reduce motion" starts on Minimal) and has a
  "Test smoothness" button that measures frame times on the device. Open `/?demo=1` to see every page with sample data (no connection made).
* `steam.py`: `web_art()` gives game covers as small JPEGs (`/steam/<appid>/header|cover`), only for games Steam reported.
* `companion/deskhub/weather.py` (new): Open-Meteo weather for the browser pages.
* `companion/deskhub/__main__.py`: messages now fan out to browsers (and the ESP32 board when a `[hub]` section exists);
  the new-client replay is shared (`snapshot_messages`).
* `media.py`, `text.py`: covers also as JPEG; with no board connected, titles keep their language (Cyrillic, CJK...) instead of being folded to ASCII.
* `tests/test_web.py` (new). Run everything: `cd companion; uv run python tests/run_all.py`.

The original ESP32 firmware is not part of this fork. Credit and licence: see [NOTICE](NOTICE) and [LICENSE](LICENSE).
