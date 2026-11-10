# Experience Journal: design and plan

Status: plan agreed 2026-11-10; nothing built yet. This document is the reference for what we're building, why,
and in what order. Change it when a decision changes.

## 1. What it is

A private, local-only journal of **what each of us took in** (read, watched, heard, did) and **how we reacted**,
measured by every sensor we choose to switch on, on any of our devices. It turns those measurements into:

- a **fused estimate** of a few dimensions (energized, pleasant, engaged, loaded) that always shows **how it got
  there**: each sensor's reading, its distance from the person's own normal, its weight, its trustworthiness;
- **daily reports**: what you experienced, how you reacted, how that compares with your normal;
- **patterns**: which kinds of input, times and situations come before changes in you;
- later, **predictions**, **well-timed prompts**, **coaching** for changes you choose, and **training**, including a
  separate experimental **subliminal** module, all measured for whether they actually work for you.

The face recognizer (`facial-recognition`) stays its own standalone program. It can send its numbers to the journal
when that's switched on; it never depends on the journal.

## 2. Principles (non-negotiable)

1. **For our family only, everyone consenting.** Each person enrols themselves, sees everything recorded about them,
   can switch any sensor off and delete any of their data. Nothing is recorded about anyone not enrolled: other
   faces and voices are ignored and never stored.
2. **Local only.** Data stays on our own computers and home network. No cloud services, no accounts, no telemetry.
   The hub listens on the home network only for paired devices.
3. **Numbers by default.** Sensors store measurements, not pictures or audio. Content logs store what you looked at
   (title, address, topic, time), never screenshots, unless a person explicitly turns more on for themselves.
4. **Shown, not asserted.** Every estimate shows its inputs. A line is named by what it was fitted to ("predicts your
   energized rating, 0.62 correlation on held-out days"), or else just "away from your normal". Readings describe
   signals ("looks", "moved away from your normal"), not feelings, unless check-ins back them up.
5. **Measured before trusted.** Every signal, fusion weight, prediction, prompt and training method is a hypothesis
   until our own data says it works (the method the face recognizer already uses). Results include the nulls.
6. **Visible control.** Every sensor and option is switchable per person in the browser (§5). Every training or
   subliminal session is logged and visible to the person it ran on.

## 3. Architecture

```
 devices (opt-in "sensor agents")                      hub (home PC, local)
 ┌──────────────────────────────┐                     ┌──────────────────────────────────────────┐
 │ PC: face recognizer tracker  │──numbers──┐         │ ingest  → timeline store (SQLite)          │
 │ PC/Mac/Linux: browser ext.   │──content──┤  paired │ baselines (per person, per situation)     │
 │ phone: check-ins, screen time│──────────►├─ token ─►│ fusion  (explainable, multi-window)       │
 │ watch/ring: HR, HRV, sleep   │──────────►│ (LAN)   │ patterns, predictions (later)              │
 │ Pi / other: any sensor       │──────────►┘         │ reports (local LLM via LM Studio)          │
 └──────────────────────────────┘                     │ interventions: prompts, coaching, training │
                                                      │   └ subliminal/ (separate module)          │
                                                      │ browser UI: people, sensors, timeline, why │
                                                      └──────────────────────────────────────────┘
```

- **Hub:** Python 3.12, standard library server plus SQLite (boring and dependable, like the face recognizer).
  Browser UI in plain HTML/JS files. The local LLM (LM Studio, already set up) writes report text from numbers it is
  given; the numbers are always shown beside its text.
- **Sensor agents:** small programs or pages per device type, each pairing once with the hub (a code shown in the hub's
  browser UI) and then sending time-stamped measurements. Agents keep a short local buffer when the hub is away.
- **Time:** every measurement carries the device's UTC time plus a clock offset measured at each sync, so readings
  from different devices line up to within about a second.
- **Security:** the hub accepts data only from paired devices (a per-device token), only from the home network; the
  browser UI only from this computer (same request checks as the face recognizer: Host, custom header, Origin).
  Data folder in `.gitignore`; encryption at rest via BitLocker on the hub's drive.

## 4. Data model (first version)

| Table | Holds |
|---|---|
| `people` | enrolled family members, consent record (what each agreed to, when), per-person settings |
| `devices` | paired devices, owner, platform, token hash, last seen, clock offset |
| `sensors` | each sensor on each device: kind, signals it gives, units, on/off per person, privacy class |
| `samples` | person, sensor, signal, time, value, quality (0-1) — the bulk of the data |
| `content` | person, device, start/end, kind (page, video, app, audio), title, address, topic tags |
| `checkins` | person, time, answers (two 1-7 scales to start: pleasant, energized; optional note) |
| `baselines` | person, signal, situation (alone/company, time of day), mean, spread, updated |
| `estimates` | person, time, dimension, window, value, confidence, contributions (per sensor) |
| `interventions` | prompts, coaching steps, training and subliminal sessions: what ran, when, arm (active/sham) |

## 5. The browser UI

- **People:** enrol, consent (what each person agreed to, editable by them), each person's data overview, export,
  delete.
- **Sensors:** every available sensor on every paired device, per person: on/off, live status, last reading,
  quality, exactly what is stored (numbers / titles / nothing), a "test" button, and "delete this sensor's data".
  New devices are paired here.
- **Timeline:** a person's day: content strip (what was taken in), the fused lines with confidence bands, and one
  strip per sensor showing its contribution.
- **Why (click any moment):** the breakdown table: sensor, raw value, your normal, z-score, weight, contribution,
  quality; the content at that moment; the nearest check-in.
- **Reports:** daily and weekly, with every claim linked to the data behind it.
- **Check-ins:** quick 1-7 scales; prompted at random times (experience sampling), never more often than chosen.
- **Training and Lab:** sessions, their arms, and the running results of each experiment (§7).

## 6. Fusion (the core)

1. **Personal scale.** Each signal becomes a z-score against that person's own normal for the situation (time of day,
   alone/company), learned continuously (the face recognizer's `signals.js` `Baselines` already does this).
2. **Trust.** Each reading carries a quality 0-1 (face visible and frontal, light, mic signal-to-noise, watch contact);
   low quality counts for less or nothing.
3. **Windows.** Exponentially weighted moving averages at about 30 seconds (reactions), 10 minutes (moods,
   episodes) and a day (drift).
4. **Dimensions.** Weighted sums of the z-scores, with weights fitted per person to their check-ins (ridge
   regression). Contribution of a sensor = weight x z, so contributions add up exactly to the estimate.
5. **Later:** a state-space model (Kalman filter) for missing sensors and confidence bands, kept only if it beats
   step 4 on held-out check-ins. Agreement between independent sensors is shown and raises confidence.

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

- Which watches/rings and phones the family uses (decides phase 4's integrations).
- Whether any family members are minors (consent then also from a parent; their data visible to them too).
- Name of the project; whether it gets a private GitHub repository (code only; data never leaves home).
