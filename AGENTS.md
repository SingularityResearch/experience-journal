# Facial-Recognition — guide for coding assistants and contributors

This is the one guide for anyone changing the code (Claude Code reads it through `CLAUDE.md`; Codex and others read it
directly). Keep it current when the layout, conventions or checks change.

Local face recognition for a USB webcam: learn specific people from a photo library, name/ignore faces
in a labeling tool, and show names + match confidence (+ optional expression) on faces live in the
browser. Everything runs on this machine; no data leaves it, except a face or photo the owner sends
on purpose with the labeling tool's **Web search** (face to Amazon, photo to Google; never automatic), and
photos sent to be described when the owner points **Describe photo** at a server on another device (Settings).

Goals, key decisions and research value: [`README.md`](README.md).
Full background, history, measured tuning values and gotchas: **see [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md).**
User-facing docs: [`face-recognizer/README.md`](face-recognizer/README.md).
Why expression reading is layered (the science): [`docs/WHY_LAYERED_EXPRESSION.md`](docs/WHY_LAYERED_EXPRESSION.md).
Expression design review (LM Studio export): [`Real-Time Facial Emotion Recognition.md`](Real-Time%20Facial%20Emotion%20Recognition.md).

## Layout

- `docs/` — background write-ups (`WHY_LAYERED_EXPRESSION.md`).
- `face-tracker/index.html` — original standalone MediaPipe tracker; double-click to open.
- `face-recognizer/` — the Python project. All programs share `face-recognizer/data/`:
  - `face_id.py` — core library + CLI (`scan`, `cluster`, `name`, `people`, `recognize`, `reembed`, `migrate`).
  - `paths.py` — `ROOT` (models\ and data\; `FACE_ROOT` overrides), `HOME` (`%APPDATA%\FaceLabels`; `FACE_HOME`
    overrides), `atomic_write`/`replace_file`. Every module takes its folders from here.
  - `labels.py` — labeling engine: per-face labels (`LabelDB`), auto-naming, duplicate-photo detection, undo history
    and clues for unnamed faces (`hints`: closest people, photo tags, same occasion). The rest of the engine is split
    into modules that `labels` re-exports (`labels.X` still works):
    - `photofiles.py` — content hashes, picture fingerprints, online-only cloud files, camera dates, photo folders.
    - `photofacts.py` — `PhotoFacts`: camera dates + people tags (XMP, Google Takeout), saved in `data/photo_facts.json`.
    - `relocate.py` — `migrate` (one-time upgrade to per-face labels) and `relocate` (finds photos that moved, e.g. a
      changed drive letter, at start).
    - `importer.py` — background photo/video `Importer` (videos: `face_id.video_faces`, ~1 frame/s, each person
      followed and their 3 clearest faces kept; frame numbers in `photos.json` `at`); one job at a time
      (`Importer.begin`); unreadable files kept with the reason (`note_problem`, shown by the page's **Why?**).
    Possible faces: each photo is also read with a low detector cut-off (`Importer.MORE_SCORE` 0.45, 4 sizes; sampled,
    not measured for accuracy); those faces are marked in `photos.json` `maybe` and listed apart from New faces.
  - `label_tool.py` + `label_ui.html` (layout) + `label_ui.js` (script) / `label.bat` — labeling web app on
    `http://127.0.0.1:8765`.
    The owner calls this "the recognizer".
  - `tracker.py` + `tracker_ui.html` + `tracker_ui.js` / `recognize.bat` — live tracker on `http://127.0.0.1:8766`.
    Its **Collect faces** option saves webcam snapshots + the tracker's verdict to `%APPDATA%\FaceLabels\webcam\`
    (`face_id.WEBCAM`); `label_tool.py` imports them by itself and shows the verdict as a clue.
  - `expression.js` — expression voting, state model, confidence flags, evidence, per-person usual look (browser;
    served by `tracker.py`). Tests: `node --test tests` from `face-recognizer\`.
  - `signals.js` — motion, talking, blinks, gaze, smile timing, webcam pulse, body posture, microphone voice features,
    each person's normal for every signal (`Baselines`, alone and in company),
    feeling-report summaries, fitted valence/arousal (browser; served by `tracker.py`; tests in `tests/`).
  - `app.py` / `build_app.bat` → `FaceRecognizer.exe` — one window (pywebview, WebView2) with Face tracking,
    Labeling and Settings tabs; starts both servers in one process (`tracker.bind/attach`, `label_tool.attach`), each
    still on its own port and page. The tab page itself (`app_ui.html` + `app_ui.js`, `{{VERSION}}` filled in) is
    served on `127.0.0.1:8764` (`/status`, `/update`, `/open-release`, `/paths`, `/open`). PyInstaller one-file build; uses
    `models\` and `data\` beside the .exe (`face_id.ROOT`); `VERSION` in `app.py` is the release number.
  - `websearch.py` — the labeling tool's **Web search**: Amazon Rekognition celebrity recognition + Google Cloud Vision web detection, combined into suggestions with a confidence level (on click only; US services, English results, each capped under $10/month; keys in `%APPDATA%\FaceLabels`, never in the repo).
  - `describe.py` — the labeling tool's **Describe photo**: a vision model in LM Studio on this computer
    (`127.0.0.1:1234`, `FACE_LLM_URL`; `reasoning_effort` none, ~3 s a photo) describes the photo and reads its text.
    The Settings tab can choose the describer (automatic / server only / built-in only), the server address (any
    OpenAI-style server, also on another device or the internet, with a warning), the model and an API key:
    `%APPDATA%\FaceLabels\describe.json`, never `data/`;
    saved per photo in `%APPDATA%\FaceLabels\descriptions.json`, never `data/`. Told not to identify anyone.
    Without LM Studio: `florence.py`, the built-in Florence-2 large (ONNX int8, CPU only: DirectML gave garbage;
    ~3 s a photo; plainer and less accurate), 0.8 GB downloaded on request from Hugging Face (pinned revision, SHA-256)
    into `models/florence2/` (not in git, not in `fetch_models.py`).
  - `settings_bridge.js` — the app window's **Settings** tab (`app.py`) reads and changes each page's settings over
    postMessage; each page lists its own (`SettingsBridge.init` at the end of its script) and applies changes through
    its own controls (`SettingsBridge.control(id, section)`) or its own get/set and actions. Served by both servers.
    Setting types: toggle, range, select, text, multi, info, button, form. The tab owns no settings itself.
  - `localguard.py` — what the three servers share: request checks (Host, `X-Face-Tool: 1`, Origin), the `Handler`
    base class (quiet, `send`/`send_json`, `refused`, framing headers, uncaught errors answered with a JSON 500;
    subclasses define `_get`/`_post`) and `bind` (no port sharing on Windows).
  - `setup.bat` — installs Python 3.12 (winget) and `requirements.txt` (pinned versions; OpenCV as
    `opencv-contrib-python` only, which mediapipe needs; setup removes a plain `opencv-python` if one is installed).
    `requirements-build.txt` adds PyInstaller for `build_app.bat`; `requirements-dev.txt` has pytest and ruff.
  - `fetch_models.py` — downloads missing models (or Git LFS placeholders): six from their publishers (OpenCV Zoo on Hugging
    Face, pinned; MediaPipe storage v1; ArcFace's bytes only, by range requests, from InsightFace's `buffalo_l.zip`),
    Wav2Small (and any fallback) from the GitHub Release `models-v1`,
    with SHA-256 checks; run by `setup.bat` and by the .exe on first start. `face_id.check_downloaded()` stops
    with "Model files weren't downloaded: install Git LFS and run git lfs pull" when it finds placeholders.
  - `models/` (Git LFS) — YuNet (detect), ArcFace R50 (recognize), SFace (fallback), eDifFIQA (quality),
    expression model, AdaFace (evaluated, unused; local only, made by `tools/get_adaface.py`, not in git),
    `npu/` (static ArcFace + VitisAI config/cache), `face_landmarker.task` (MediaPipe blendshape cues, optional),
    `wav2small.onnx` (voice arousal/dominance/valence, optional; made by `tools/get_wav2small.py`),
    `pose_landmarker_lite.task` (MediaPipe body posture, optional).
  - `tools/` — `eval_models.py`, `hw_bench.py`, `expr_check.py`, `expr_eval.py`, `get_adaface.py`, `get_wav2small.py`, `import_bench.py`, `websearch_check.py`, `webcam_eval.py` (live naming on confirmed webcam snapshots; measured the
    averaged-print rule the tracker uses via `/api/who`).
  - `tests/` — Node tests (`*.test.js`: `expression.js`, `signals.js`, `settings_bridge.js`, every page script parses
    and is served and packed) and Python tests (`test_*.py`, pytest: request checks, describe settings and where
    photos/keys go, Web search keys and caps, the model download against a local server, labeling and undo, the
    face-picture migration, the empty new-user start, and a tripwire on the measured thresholds). `conftest.py`
    points `FACE_ROOT`/`FACE_HOME` at a temp folder before anything is imported: no models, no real data.
  - `.github/workflows/checks.yml` — CI on every push/PR: Node tests, ruff, pyflakes and pytest (no LFS, no models).

## Running

```
face-recognizer\setup.bat        # once
face-recognizer\recognize.bat    # live tracker  (port 8766)
face-recognizer\label.bat        # labeling tool (port 8765)
face-recognizer\build_app.bat    # builds FaceRecognizer.exe: both apps in one window, two tabs
python face_id.py --help         # CLI pipeline (run from face-recognizer\)
```

Use the Python 3.12 the .bat files pick (`%LOCALAPPDATA%\Programs\Python\Python312\python.exe`). The
`python` on PATH (3.15) does not have OpenCV/onnxruntime installed.

## Checks before committing

```
cd face-recognizer
node --test tests                                   # browser code and page scripts
set PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
%PY% -m ruff check .                                 # ruff.toml; pyflakes rules plus likely bugs
%PY% -m pytest tests -q                              # Python tests (requirements-dev.txt)
```

CI runs all of these. Keep page code in the `.js` files (no inline `<script>` blocks: a test fails on them), and add
any new page file to its server and to `build_app.bat` (a test checks both). Change a measured threshold only together
with `tests/test_thresholds.py`, after re-measuring.
Test UI changes in the real app or a test copy, never against the owner's running app:
- The owner's app holds ports 8764-8766. Start a test copy from source on spare ports (tracker/labeling `--port`,
  or `app.start` with a port offset), with `APPDATA` pointed at a temp folder and `face_id.DATA` at an empty or copied
  folder, so it can't touch the real `data/` or `%APPDATA%\FaceLabels`.
- Headless Edge over CDP works for page checks. Kill leftover `msedge --remote-debugging-port` processes first:
  an old one keeps old tabs (and their errors) alive.
- Importing `face_id` works without models; each program calls `face_id.require_models()` when it starts, which
  stops with `NotDownloaded` (what to run) if they're missing.

## Security rules

- Every endpoint goes through `localguard.refuse_reason` (exact Host and port; POST needs `X-Face-Tool: 1` and its
  own Origin). The `app.py` shell uses it too: its GETs that do something (`/update`, `/open-release`, `/open`) need
  the header.
- Every answer carries `localguard.page_headers`: `frame-ancestors` lets only the page itself and the app's tab page
  (`localguard.FRAME_PARENTS`, 8764 or the shell's real port) frame it; the shell page can't be framed at all.
- Servers bind with `localguard.bind` (no address reuse on Windows, so a second copy fails instead of sharing the
  port) and wrap handlers in `localguard.answer_errors` (an uncaught error still gets a JSON 500).
- Anything put into `innerHTML` goes through `esc()` (names, paths, descriptions, web results, tags, errors).
  The Settings tab builds its rows with `textContent`/DOM properties only.
- Keys (Web search, describe API key) are never sent to the page: endpoints return only whether one is saved.
- Only the two fixed folders may be opened (`/open?what=data|private`); photos are addressed by face index, never by path.
- Downloads are pinned and checked by size and SHA-256 (`fetch_models.py`, `florence.py`).
- `settings_bridge.js` answers only its parent window, on `127.0.0.1`/`localhost`, and only when that is the origin
  the browser reports for the frame's parent (`location.ancestorOrigins`).
- Describe photo: the API key belongs to its server address (changing the address clears it; Test sends it only to
  that address); redirects aren't followed; answers are capped (`MAX_ANSWER`, `MAX_TEXT`).
- Background jobs (imports, possible-face scans, Describe all) start through `Importer.begin` (one at a time, under
  a lock). Shared caches and counters used by request threads need a lock.
- Open items from the 2026-11-09 review: `PROJECT_CONTEXT.md` section 10.

## Conventions and constraints

- Keep `face-recognizer/README.md` in sync with any user-visible change, and this file with layout or rule changes.
- A new option on the tracker or labeling page should also be listed in that page's `SettingsBridge.init` list,
  so it shows in the Settings tab. Options the user changes should be remembered (`remember`/`store.set`).
- Thresholds are **measured values** — don't change them without re-measuring on `data/`:
  `face_id.py` (`REC_MODELS[...]["match"/"cluster"]`, `Q_ENROLL`, `Q_EXPR`, `MAX_TURN`),
  `labels.py` (`AUTO`, `MARGIN`, `TOPK`, `DUP_BITS`), `tracker_ui.html` (strictness default 0.35),
  and `expression.js` (`X_SURE`, `X_MARGIN`, `X_MIN_VOTES`, vote windows).
- Not yet measured, so evidence only: `expression.js` `H_STAY` (state model) and every `signals.js` constant
  (`TALK_JAW_SD`, pulse, voice). The options that let them change the label (skip while talking, state model)
  stay off by default until `tools/expr_eval.py` shows they help on posed sessions. Same for the hand-on-face skip.
- `data/` is local only: the whole folder is in .gitignore and was purged from git history and releases
  (2026-11-09). Never commit anything from it, or personal details (names, paths, accounts) in docs. A fresh
  copy starts with an empty `data/` and every feature must work from there; `Store.thumb(i)` may be None.
- Labels live per face in `data/labels.json` (keyed by permanent face ID); change them through the
  labeling tool or `LabelDB`, not by hand-editing JSON. `cluster` group numbers are temporary.
- After switching recognition model: `python face_id.py reembed`.
- Name overlay belongs on the face near the top of the head (owner preference).
- The labeling tool stays a separate program from the tracker (owner preference): separate code, server and page.
  Since 2026-11-08 they can share one window as two tabs (`app.py`), but each still runs on its own.
- Camera opening on Windows: try `CAP_DSHOW` → `CAP_MSMF` → `CAP_ANY`, retry `cap.read()` while the webcam warms up.
- Face-shape cues are evidence only until fusion is measured with `tools/expr_eval.py` on posed sessions.
- Expression is display-only and never stored (except opt-in posed test sessions and feeling reports in `data/expr_eval/`,
  numbers only); microphone audio is analysed live and never stored; per-person baselines and usual looks live in the
  browser's storage only (never `data/`); keep README wording honest ("looks", not "feels").
- Describe photo is local by default. Pointing it at another device (Settings) sends each described photo there; the
  Settings tab must say so (`describe.where`). Descriptions and `describe.json` live in `%APPDATA%\FaceLabels`.
- Releases: the zip holds `FaceRecognizer.exe` and a new-user `README.txt` only, never `data\`.
- The presence log (who was in view, when) is opt-in, names and times only, in `%APPDATA%\FaceLabels\presence\`, never `data/`.
- Webcam faces named automatically don't enter the recognition gallery until confirmed (`LabelDB.gallery`).
- InsightFace ArcFace and audEERING Wav2Small weights are non-commercial; note this if the project is ever redistributed.
