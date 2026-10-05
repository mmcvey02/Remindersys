# RemindersSys

Smart notifications for **Apple Calendar** and **Apple Reminders** on **macOS and Windows**.

RemindersSys runs in the menu bar / system tray. It reads your calendars and reminders, works out
what matters and how long it takes to get there, and notifies you **early enough to arrive on
time**. Routine items go into a **daily summary at startup** and a **weekly summary of major tasks**
instead of a stream of pings.

## What it does

| | |
|---|---|
| **Syncs with Apple** | macOS: reads Calendar and Reminders directly through EventKit, so every account synced to the Mac is included. Windows: connects to iCloud over CalDAV with an app-specific password. |
| **Scores priority** | Each item gets a 0–100 score from explainable signals and lands in one of four tiers: Critical, High, Normal or Low. |
| **Travel-aware alerts** | Finds the event's location, estimates the drive, transit, walk or ride from home (or from your previous event), allows for rush hour and parking, and tells you when to leave. |
| **Daily summary** | Shown when the computer starts, or when it wakes on a new day: today's schedule, tasks due, overdue items, important undated tasks and a heads-up for tomorrow. |
| **Weekly summary** | Major items for the next 7 days, grouped by day, on the first startup of the week (the day is configurable). |
| **Quiet hours** | Non-urgent alerts wait until morning. "Leave now" and Critical alerts still come through. |

### Notification policy

| Tier | Timed events | Reminders with a due time | All-day items |
|---|---|---|---|
| **Critical** | Heads-up 24 h before · "leave in 1 h" · **"leave now"** (stays on screen) | 24 h and 2 h before | Evening before and morning of |
| **High** | "Leave in 30 min" · "leave now" | 1 h before | Summary |
| **Normal** | One alert 10 min before you need to leave | Summary only | Summary |
| **Low** | Summary only | Summary only | Summary |

**Leave time** = start − travel time − arrival buffer (10 min by default). For virtual meetings
(Zoom, Teams, Meet and others) and events with no location, you get a single alert 5 minutes
before the start.

If the computer was off or asleep, missed alerts are caught up. Only the most recent alert for
each item is sent, and anything that no longer matters (the event has already started) is
dropped.

### How priority is scored

The score starts from a base value. Each of these signals moves it up or down:

- **Explicit priority** from Reminders (`!!!`, `!!`, `!`) or iCalendar `PRIORITY`.
- **Keywords**, matched as whole words.
  - High-stakes words raise the score: *flight, interview, exam, surgery, doctor, deadline, rent, tax, presentation, court, wedding…*
  - Chore words lower it: *groceries, laundry, clean, someday…*
  - You can add your own in either direction.
- **Context**:
  - Raises the score: physical location (travel is needed), number of attendees, an alert you set yourself, an overdue reminder.
  - Lowers the score: recurring items, all-day items.
- **Calendar weight**: holiday, birthday and Siri-suggestion calendars count for less. Set your own, for example `{"Work": 10, "Kids": 20}`.

To see the score and the reasons behind it for every item, run `RemindersSys -v sync`. In the
HTML summary, hover over an item's tier badge.

## Install

Download the installer for your platform from the
[Releases](https://github.com/mmcvey02/remindersys/releases) page or from the latest
[Actions build](https://github.com/mmcvey02/remindersys/actions):

| Platform | File |
|---|---|
| Windows 10/11 | `RemindersSys.exe` (single file, no install needed) |
| macOS 11+ Apple Silicon | `RemindersSys-macOS-arm64.dmg` |
| macOS 11+ Intel | `RemindersSys-macOS-x86_64.dmg` |

### macOS

1. Open the `.dmg` and drag **RemindersSys** to **Applications**.
2. The app is not notarized, so the first time you must **right-click it → Open → Open**.
3. Allow access to **Calendars** and **Reminders** when macOS asks.
4. Notifications are delivered through AppleScript. If none appear, open **System Settings →
   Notifications → Script Editor** and allow them.
5. A bell icon appears in the menu bar. RemindersSys registers itself to start at login.

### Windows

1. Create an Apple **app-specific password** at [appleid.apple.com](https://appleid.apple.com)
   → *Sign-In and Security* → *App-Specific Passwords*.
2. Run `RemindersSys.exe`. If SmartScreen warns you, choose **More info → Run anyway**.
3. In the Settings window, enter your Apple ID, the app-specific password and your home address.
   **Test iCloud** checks the connection.
4. The password is stored in **Windows Credential Manager**, never in plain text. A bell icon
   appears in the system tray, and the app starts automatically at login.

> **Windows and Reminders:** Apple only exposes Reminders lists over CalDAV if they haven't been
> upgraded to the newer Reminders format (iOS 13+). On most current iCloud accounts, calendar
> events sync fully on Windows but reminders may not appear. Calendar events still get full
> travel-aware alerts. On macOS, both work fully through EventKit.

## Using it

Tray / menu-bar menu: **Today's summary**, **This week**, **Sync now**, **Settings…**,
**Start at login**, **Open log folder**, **Quit**.

Command line (the same executable):

```
RemindersSys                          # start in the tray (default)
RemindersSys run --headless           # no tray icon
RemindersSys setup                    # settings window
RemindersSys -v sync                  # list items with scores, reasons and planned alerts
RemindersSys summary daily|weekly     # build and open a summary now
RemindersSys autostart enable|disable|status
RemindersSys --demo ...               # try it with built-in sample data
```

### Configuration

Settings live in `config.json`, in:

- macOS: `~/Library/Application Support/RemindersSys/`
- Windows: `%APPDATA%\RemindersSys\`

The same folder holds the log, saved HTML summaries and state. The Settings window covers the
common options. Advanced options can be edited in the file, and the running app picks up
changes automatically.

| Key | Default | Meaning |
|---|---|---|
| `source` | `auto` | `auto`, `eventkit` (Mac), `caldav` (iCloud), `demo` |
| `home_address` | `""` | Where trips start from |
| `travel_mode` | `driving` | `driving`, `transit`, `walking`, `cycling` |
| `arrival_buffer_minutes` | `10` | Aim to arrive this early |
| `default_travel_minutes` | `20` | Used when a location can't be found |
| `use_online_routing` | `true` | Use OpenStreetMap (Nominatim and OSRM) for geocoding and routes |
| `quiet_hours_start` / `_end` | `22:00` / `07:00` | Hold non-urgent alerts during these hours |
| `daily_summary_on_startup` | `true` | Send the daily summary when the computer starts |
| `daily_summary_fallback_time` | `08:00` | Send it at this time if the computer stayed on overnight |
| `weekly_summary_weekday` | `0` | 0 = Monday … 6 = Sunday |
| `calendars_include` / `calendars_exclude` | `[]` | Filter by calendar or list name |
| `extra_high_priority_keywords` / `extra_low_priority_keywords` | `[]` | Your own keywords |
| `calendar_weights` | `{}` | Score adjustment per calendar, e.g. `{"Work": 10}` |
| `modal_alert_for_critical` | `true` | macOS: also show a dialog for Critical "leave now" alerts |

### Privacy

- Your calendar data stays on your computer.
- The only network calls are to Apple (iCloud CalDAV, Windows only) and, when online routing is
  on, to OpenStreetMap's public Nominatim and OSRM services. Those receive event **location
  strings and coordinates only**. Results are cached.
- Set `use_online_routing` to `false` to keep everything offline. Travel time then uses
  `default_travel_minutes`.

## Building from source

Requires Python 3.10+.

```bash
pip install -r requirements-dev.txt
python -m pytest                      # unit tests
python -m remindersys --demo sync     # try it
```

Packages can only be built on their target OS:

```bash
# macOS -> dist/RemindersSys.app and dist/RemindersSys-macOS-<arch>.dmg
bash packaging/build_macos.sh
```

```powershell
# Windows -> dist\RemindersSys.exe
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

GitHub Actions (`.github/workflows/build.yml`) runs the tests on Windows, macOS and Linux. It then
builds the `.exe` and both `.dmg` files and smoke-tests each one. Pushing a `v*` tag attaches the
binaries to a GitHub Release.

### Project layout

```
remindersys/
  sources/        eventkit.py (macOS) · caldav_source.py (iCloud) · demo.py
  priority.py     scoring engine
  travel.py       geocoding, routing, travel-time heuristics
  scheduler.py    tiers → concrete alert times, catch-up, quiet hours
  summaries.py    daily/weekly digests (text + HTML)
  app.py          sync/notify/summary loop, sleep/wake handling
  notifier.py     native notifications (WinRT toast, Notification Center, notify-send)
  tray.py         menu bar / system tray UI
  setup_ui.py     settings window
  autostart.py    login item (Registry Run key / LaunchAgent)
packaging/        PyInstaller spec, icon generator, build scripts
tests/
```

### Limitations

- Travel times come from OpenStreetMap routing with a rush-hour multiplier, not live traffic.
  Transit, walking and cycling times are distance-based estimates.
- The builds are unsigned. To distribute without Gatekeeper or SmartScreen warnings:
  - macOS: set `CODESIGN_IDENTITY` to a Developer ID and notarize the app.
  - Windows: sign the `.exe` with a code-signing certificate.
