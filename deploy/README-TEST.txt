Experience Journal - test build
================================

A build made by GitHub Actions from the experience-journal repository after every check passed. It is for hands-on
testing on this computer. BUILD-INFO.json says which commit it is; SHA256SUMS.txt lists every file's SHA-256.

What's here
  FaceRecognizer.exe        the face recognizer (live tracker, labeling tool, alerts, Settings)
  Start-FaceRecognizer.cmd  starts it with the TEST folders (face-root, face-home), never your own library, on
                            ports 9764-9766, so it runs beside your usual copy (8764-8766)
  Run-FusionDemo.cmd        the journal's fusion on simulated people (needs Python 3.12 with numpy)
  journal\                  the journal's code and docs (the hub and its pages aren't built yet)

First start
  FaceRecognizer.exe downloads its models (about 196 MB) into face-root\models, once for all test builds.
  The test library starts empty: add photos in the Labeling tab, or install with
    deploy_local.ps1 -SeedFrom <your face-recognizer folder>
  to copy your models and library into the test folders once.

What to check
  See the commit's changes on GitHub (BUILD-INFO.json "commit"), then try them in the app. Report what you see.
