#!/usr/bin/env bash
# Sets up a virtual environment (first run only) and starts the demo UI.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
export SSL_CERT_FILE=$(python -c "import certifi; print(certifi.where())")
pip install -q -r requirements.txt
streamlit run app.py
