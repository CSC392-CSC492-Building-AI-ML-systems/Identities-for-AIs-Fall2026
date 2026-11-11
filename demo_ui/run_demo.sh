#!/usr/bin/env bash
# Sets up a virtual environment (first run only) and starts the demo UI.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
streamlit run app.py
