# Experience Journal: design and plan

Status: plan agreed 2026-11-10; the fusion engine (§6) is built and tested on simulated data; the rest isn't built yet. This document is the reference for what we're building, why,
and in what order. Change it when a decision changes.

## 1. What it is

A private, local-only research journal of **what each participant took in** (read, watched, heard, did) and **how
they reacted**, measured by every sensor they choose to switch on, on any of their devices. It is a research project
in behavioural analysis: every participant consents, and the sensor set is deliberately open (webcam, imported photos
and video, microphone and voice, wearables, phone, browser and content logs, and other systems through connectors).
It turns those measurements into:

- a **fused estimate** of a few dimensions (energized, pleasant, engaged, loaded) that always shows **how it got
  there**: each sensor's reading, its distance from the person's own normal, its weight, its trustworthiness;
- **daily reports**: what you experienced, how you reacted, how that compares with your normal;
- **patterns**: which kinds of input, times and situations come before changes in you;
- later, **predictions**, **well-timed prompts**, **coaching** for changes you choose, and **training**, including a
  separate experimental **subliminal** module, all measured for whether they actually work for you.

The face recognizer stays its own standalone program and repository; this repository aggregates it (a git subtree in
`facial-recognition/`, kept in step with its own repository) as the first sensor source. It can send its numbers to
the journal when that's switched on; it never depends on the journal.

## 2. Principles (non-negotiable)

1. **A research project; every participant consents.** Each participant enrols themselves and gives informed consent,
   recorded per sensor (what is measured, whether raw data is kept, what it is used for), which they can change or
   withdraw at any time. They see everything recorded about them, can switch any sensor off, and can export or delete
   any of their data. Nothing is recorded about anyone who hasn't consented: other faces and voices are ignored and
   never stored.
2. **Any sensor, by choice.** The sensor set is open: webcam, imported photos and video, microphone and voice,
   wearables, phone, browser and content logs, and other systems through connectors (§3). Each is switched on per
   participant; adding a new kind of sensor needs a connector and a consent entry, not a redesign.
3. **Local only.** Data stays on the project's own computers and local network. No cloud services, no accounts, no
   telemetry. The hub listens on the local network only for paired devices.
4. **Numbers by default, raw data by consent.** Sensors store measurements by default. Raw pictures, video or audio
   (and screenshots of content) are kept only for a participant who opted into keeping that sensor's raw data; it's
   recorded in their consent and shown on the Sensors page. Content logs store what was looked at (title, address,
   topic, time).
5. **Shown, not asserted.** Every estimate shows its inputs. A line is named by what it was fitted to ("predicts your
   energized rating, 0.62 correlation on held-out days"), or else just "away from your normal". Readings describe
   signals ("looks", "moved away from your normal"), not feelings, unless check-ins back them up.
6. **Measured before trusted.** Every signal, fusion weight, prediction, prompt and training method is a hypothesis
   until our own data says it works (the method the face recognizer already uses). Results include the nulls.
7. **Visible control.** Every sensor and option is switchable per participant in the browser (§5). Every training or
   subliminal session is logged and visible to the participant it ran on.

## 3. Architecture

```
 devices (opt-in "sensor agents")                      hub (local PC)
 ┌──────────────────────────────┐                     ┌──────────────────────────────────────────┐
 │ PC: face recognizer tracker  │──numbers──┐         │ ingest  → timeline store (SQLite)          │
 │ PC/Mac/Linux: browser ext.   │──content──┤  paired │ baselines (per person, per situation)     │
 │ phone: check-ins, screen time│──────────►├─ token ─►│ fusion  (explainable, multi-window)       │
 │ watch/ring: HR, HRV, sleep   │──────────►│ (LAN)   │ patterns, predictions (later)              │
 │ Pi / connectors: any source  │──────────►┘         │ reports (local LLM via LM Studio)          │
 └──────────────────────────────┘                     │ interventions: prompts, coaching, training │
                                                      │   └ subliminal/ (separate module)          │
                                                      │ browser UI: people, sensors, timeline, why │
                                                      └──────────────────────────────────────────┘
```

- **Hub:** Python 3.12, standard library server plus SQLite (boring and dependable, like the face recognizer).
  Browser UI in plain HTML/JS files. The local LLM (LM Studio, already set up) writes report text from numbers it is
  given; the numbers are always shown beside its text.
- **Sensor agents and connectors:** small programs or pages per device type or source (webcam and photo/video import
  through the face recognizer, microphone and voice, browser extension, phone, wearables, or another system through a
  connector that translates its output), each pairing once with the hub (a code shown in the hub's browser UI) and
  then sending time-stamped measurements, plus raw files only where the participant consented to keeping them. All
  speak one small documented format, so a new kind of sensor is a new connector, not a change to the hub. Agents
  keep a short local buffer when the hub is away.
- **Time:** every measurement carries the device's UTC time plus a clock offset measured at each sync, so readings
  from different devices line up to within about a second.
- **Security:** the hub accepts data only from paired devices (a per-device token), only from the local network; the
  browser UI only from this computer (same request checks as the face recognizer: Host, custom header, Origin).
  Data folder in `.gitignore`; encryption at rest via BitLocker on the hub's drive.

## 4. Data model (first version)

| Table | Holds |
|---|---|
| `people` | enrolled participants, consent record (per sensor: what is measured, whether raw data is kept, what it's used for; when given, changed or withdrawn), per-person settings |
| `devices` | paired devices, owner, platform, token hash, last seen, clock offset |
| `sensors` | each sensor on each device: kind, signals it gives, units, on/off per person, raw data kept per person (only with consent), privacy class |
| `samples` | person, sensor, signal, time, value, quality (0-1) — the bulk of the data |
| `media` | raw pictures, video or audio a participant consented to keeping: person, sensor, time, file, hash |
| `content` | person, device, start/end, kind (page, video, app, audio), title, address, topic tags |
| `checkins` | person, time, answers (two 1-7 scales to start: pleasant, energized; optional note) |
| `baselines` | person, signal, situation (alone/company, time of day), mean, spread, updated |
| `estimates` | person, time, dimension, window, value, confidence, contributions (per sensor) |
| `interventions` | prompts, coaching steps, training and subliminal sessions: what ran, when, arm (active/sham) |

## 5. The browser UI

- **People:** enrol, consent (what each participant agreed to, per sensor, editable and withdrawable by them), each
  participant's data overview, export, delete.
- **Sensors:** every available sensor on every paired device, per person: on/off, live status, last reading,
  quality, exactly what is stored (numbers / titles / raw media / nothing), a "test" button, and "delete this sensor's data".
  New devices are paired here.
- **Timeline:** a person's day: content strip (what was taken in), the fused lines with confidence bands, and one
  strip per sensor showing its contribution.
- **Why (click any moment):** the breakdown table: sensor, raw value, your normal, z-score, weight, contribution,
  quality; the content at that moment; the nearest check-in.
- **Reports:** daily and weekly, with every claim linked to the data behind it.
- **Check-ins:** quick 1-7 scales; prompted at random times (experience sampling), never more often than chosen.
- **Training and Lab:** sessions, their arms, and the running results of each experiment (§7).

## 6. Fusion (the core)

Code: `fusion/` (implemented 2026-11-10, tested on simulated people; no real sensors yet). A three-layer model,
simple first, each extra step earning its place on held-out data.

### Layer 1: clean signals on each person's own scale (`baselines.py`, `windows.py`, `away.py`)
- **Robust normal** per person and signal: median and typical spread (MAD), not mean and SD, so rare spikes don't
  warp it; kept per situation (part of day x alone/company) with the overall normal as fallback until a situation has
  enough readings (`MIN_N`); slowly adapting (one reading per 30 s, last 5,000). The spread never collapses: a signal
  that is usually exactly 0 (a laugh, a blink count) uses the mean absolute deviation instead, and never less than
  the sensor's stated resolution.
- **Learning pauses per signal** while that signal's own 10-minute window is more than `FREEZE_Z` (3) spreads from
  its normal, so a bad stretch doesn't become the new normal and one moved or broken sensor doesn't stop the others
  learning. A pause lasts at most `MAX_PAUSE` (6 h, a guess); then the normal follows again and the Why view marks
  the signal "relearning: your normal may have changed".
- **z-score** of every reading against that normal, clipped to ±`Z_CLIP` (6) before smoothing so one glitch can't
  dominate (the Why view shows the unclipped value); **trust** 0-1 per reading (face visible, signal-to-noise,
  contact).
- **Windows**: trust-weighted exponential moving averages over 30 s (reactions), 10 min (moods) and a day (drift),
  correct for uneven gaps; each also reports its **support** (decayed trust), which falls while a sensor is silent.
  An hour of window values is kept so signals can be read a little back in time (**lags**), or at a moment that has
  passed, from the readings up to then only.
- **Time order:** a reading that arrives late (a device buffering while the hub was away) counts with the weight it
  would have left by then; a check-in's features are fixed only after `SETTLE` (2 min) of later readings, from the
  readings up to the check-in. Results don't depend on which arrived first.
- **"Away from your normal"** before any check-ins: the trust-weighted root mean square of the signals' 10-minute
  windows; each signal's share is exact (the contributions add up to score²). 1 means signals sat a whole reading's
  spread away for ten minutes, which is already unusual. Says how unusual a moment is, not what it means.

### Layer 2: the explained estimate, fitted to check-ins (`linear.py`, `engine.py`)
- Per dimension (energized, pleasant, ...): rating = the person's usual + sum of weight x feature, features being each
  signal's 30-second and 10-minute windows read at that signal's lag. Contributions add up exactly to the estimate;
  `importance()` gives how far a typical swing of each feature moves it (comparable across features), and
  `uncertainty()` how sure that is (a weight within about two of these of 0 isn't distinguishable from no effect).
- **Group model** (Bayesian, hierarchical): everyone's weights start at the group average and move only as far as
  their own check-ins justify. The strength of that pull (tau2) and the leftover noise are chosen together by marginal
  likelihood, with the group average integrated out; each person is pulled toward the average of the *others'*
  check-ins, so their own data counts once. Features are scaled to unit spread (where present) before fitting.
  Every estimate has an honest spread (leftover noise + weight uncertainty + the group average's own uncertainty),
  shown as a band; a new person starts from the group's weights with a wider band.
- **Missing sensors** count as "at normal" (0) in the estimate, and their uncertainty is added to the band (what the
  missing feature can still do given the present ones, times its weight): a silent sensor widens the band.
- **Why view:** each row shows the raw reading, the normal it was compared with, z, trust, whether its normal is
  learning, and each feature the model used (window value at the lag, its support, weight, contribution =
  weight x value), so every number can be checked by hand. It can explain now or the last hour; estimates for the
  timeline are stored when they are made (`estimates` table) rather than recomputed later.
- **Lags** chosen per signal from the check-ins (largest correlation of the 30-second window among 0, 1, 2, 5 min).
  Finding: with a slow mood and a few check-ins a day, delays under about 2 minutes are hard to tell apart from
  check-ins; they'll be measured from reactions to known moments (content start, phase 2).
- At every check-in the engine logs what each attached model predicted *before* seeing it (`prediction_log`), so
  models are compared on live, honest predictions.

### Layer 3: a Kalman filter over time (`kalman.py`) — optional, used only if it wins
- Hidden level pulled back to the person's usual (time constant 1 h); each sensor's 30-second window a noisy view
  (loading, noise from data), noise scaled by trust; check-ins a direct view. Handles sensors at different rates and
  dropouts (the band widens). Explainable: each update's move is credited to its sensor, credits decay with the level,
  and they add up exactly to the departure from usual.
- **Result on simulated fortnights (2026-11-10): it doesn't beat layer 2.** Fed every 30 s it lost clearly (error
  0.76 vs 0.63, its 70% band held only 54%): it treated strongly overlapping 30-second windows as independent views.
  Fed every 10 minutes (`FILTER_EVERY`), with an offset per sensor, it roughly ties over six seeds (live error
  0.59-0.67 vs 0.57-0.67 for layer 2; band 79-84%, a little wide). Still to try on real data: fitting the time
  constant and noise by the likelihood of each next reading, delays in the filter, and allowing for the noise in the
  check-ins the loadings are fitted to. Until it beats layer 2 on held-out weeks, layer 2 is the estimate shown.

### How it's measured (`evaluate.py`)
Forward chaining (fit on earlier days, predict the next; never shuffled), against "your average" and "your last
check-in", with the 70% band's coverage. Everything a fold uses (lags, feature scales, weights, normals) comes from
earlier data only. Simulated fortnights (2 people, 4 sensors, one of them irrelevant, 5 check-ins a day; the
simulator follows the model's own assumptions, so real data will do worse), six seeds (2026-11-10): layer 2 error
0.54-0.65 vs 0.88-1.07 for "your average" and 0.94-1.31 for "your last check-in", 70% band holds 68-86% (ratings are
whole numbers, which widens it a little); the irrelevant signal's weights stay within noise of 0. Tests check seed
0 and two others. `tools/demo_fusion.py` prints a "why" table.

## 7. Training, interventions and the subliminal module

- **Prompts and coaching:** visible, chosen by the person: if-then plans, habit cues at the right moment,
  biofeedback (breathing, heart rate), coaching steps an LLM helps structure from established behaviour-change methods.
  Measured with micro-randomized trials: at each eligible moment the app randomly decides whether to prompt, so the
  effect of prompting can be estimated per person.
- **Subliminal module (`subliminal/`, separate):** treated as craftsmanship and an experiment we learn from together.
  Rules:
  - its own module and its own data tables; nothing else imports it except the Lab page that runs it;
  - per-person opt-in specifically for it (separate from the rest), off by default, switchable any time;
  - every session logged and visible to that person (when, which material, which arm), even if the stimulus
    itself isn't consciously noticed;
  - blinded and randomized: active vs sham sessions the person can't tell apart, outcomes measured by the same
    sensors and check-ins, analysed before anyone looks at which was which;
  - expectations honest: published effects of subliminal priming are small and short-lived; the module exists to
    find out what, if anything, works for us, and to build the craft of designing and measuring it.

## 8. Phases

| # | Phase | Contents | Done when |
|---|---|---|---|
| 0 | Foundations | Repo, this design, AGENTS.md, CI (tests from day one), hub skeleton with request checks, SQLite schema, People and Sensors pages | Hub runs, a person can enrol and see the empty sensor list |
| 1 | First sensors + fusion | Face recognizer sends numbers (opt-in setting there), check-ins page, fusion steps 1-4 with the Why view | A day of real data; the Why table explains every movement |
| 2 | Content | Browser extension (Edge/Chrome): page and video titles, addresses, time, focus; topic tags by the local LLM | Content strip lines up with reactions |
| 3 | Reports | Daily/weekly report, every claim linked to its data | Reports read as accurate to the person |
| 4 | More devices | Watch/ring (HR, HRV, sleep), phone check-ins and screen time, Mac/Linux/Pi agents | Signals that track check-ins better than the webcam alone |
| 5 | Patterns, predictions | Within-person statistics on held-out weeks; predicted next check-in | Patterns that hold up; predictions beat a baseline |
| 6 | Interventions | Prompts and coaching with micro-randomized trials; training games; the subliminal Lab | Measured effects (or measured nulls) per person |

## 9. Open questions

- Which watches/rings and phones the participants use (decides phase 4's integrations).
- Whether any participants are minors (consent then also from a parent or guardian; their data visible to them too).
- Whether results will be published or shared outside the project: if so, a formal consent form and ethics review
  first, and only de-identified, aggregated numbers leave the local network, each time with the participants'
  agreement.
- Name of the project; whether it gets a private GitHub repository (code only; data never leaves home).
