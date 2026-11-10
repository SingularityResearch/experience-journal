#!/bin/sh
# Starts the face recognizer: the live tracker and the labeling tool in one window (app.py), on macOS or Linux.
#   ./start.sh             in its own window
#   ./start.sh --browser   in your web browser instead
# Run ./setup.sh once first.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Run ./setup.sh first (it installs the libraries and models)."
  exit 1
fi
exec .venv/bin/python app.py "$@"
