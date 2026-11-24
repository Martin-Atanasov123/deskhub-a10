# What a browser cannot do on the Galaxy A10

The dashboard runs in the phone's own browser, over Wi-Fi, with nothing installed. That choice has limits.
Each one below says what happens, what you can do **from the phone's touchscreen**, and what only
native software could fix.

Status: written from how Android and browsers work, **not yet confirmed on your A10**. Run `/compat` on the phone
(link on the pairing screen) and these notes will be checked against its real answers.

| # | Limit | What you get instead | Needs native software to remove? |
| --- | --- | --- | --- |
| 1 | **The screen cannot be kept on while the phone is on battery.** The browser's wake-lock API only exists on secure pages, and `http://<PC address>` is not one. Android switches the screen off after its screen timeout. | Set *Settings → Display → Screen timeout* to the longest value. Eco mode keeps the radio and CPU quiet so a long timeout costs less. Optional, **while charging only**: enable Developer options (*Settings → About phone → Software information*, tap *Build number* 7 times) and turn on *Stay awake*. Optional, Chrome only: `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, add the PC address, relaunch Chrome; the dashboard's *Keep screen on* switch then works. | Yes: a kiosk app or a wrapper app can hold a screen-on flag. |
| 2 | **A web page cannot change screen brightness.** | *Dim the picture* darkens the image only. On an LCD like the A10's, that **does not lower backlight power**; use the phone's brightness slider (swipe down from the top) for real savings. | Yes. |
| 3 | **No auto-start.** After the phone restarts or the browser is closed, nothing reopens the dashboard. | Add the page to the home screen (Chrome menu → *Add to Home screen*), reopen it with one tap. | Yes (start on boot). |
| 4 | **Fullscreen needs a tap** each time, and swipe gestures can leave it. | Settings page → *Fullscreen*. Android's *Pin windows* (search for it in Settings) stops accidental exits. | Yes, for a true locked kiosk. |
| 5 | **Nothing runs while the screen is off.** Browsers pause pages in the background. | The dashboard disconnects on purpose when hidden (saves battery) and reconnects the moment the screen is back. Alerts cannot wake the phone. | Yes (a background service with notifications). |
| 6 | **`deskhub.local`-style names are unreliable on Android browsers.** | Use the PC's address (the QR code has it). Give the PC a fixed address in the router, otherwise the address can change and the phone must be paired again. | Partly (apps can discover the PC). |
| 7 | **Plain http, no install as an app, no offline mode.** Service workers and "install app" need https. | Works on the home network only. Traffic is unencrypted, like the original DeskHub: use a network you trust. The pairing code keeps other devices from driving your shortcuts. | Not needed; https needs a certificate the phone would have to trust. |
| 8 | **Battery level is probably not readable** (the browser's Battery API also needs a secure page). | Eco mode is the default. The Settings page shows the level when the browser allows it. | No, but the app could read it. |
| 9 | **Shortcut keys act on the PC, not the phone**, and a stuck or sleeping PC cannot run them. | Same as the original project. | n/a |
| 10 | **The timer cannot ring while the screen is off.** Browsers freeze pages and block sound in the background. | The timer keeps its end time, so when the screen comes back it shows "Time's up" at once (and rings only if it ended within the last two minutes). It rings and vibrates when the screen is on; the first tap on a preset allows the sound. Use the phone's own alarm for anything that must wake you. | Yes (a native alarm). |

## Things that are not limits

* **Reconnect after wake or resume:** the page reconnects on screen-on, tab-visible, back-online and when data stops arriving.
* **Pairing and setup:** QR code or a typed code, on the touchscreen only.
* **Diagnostics:** `/diag` on the PC shows connected phones, their power mode, errors they report and compatibility results.
