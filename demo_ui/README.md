# Model Change Monitor (demo UI)

A small Streamlit page that showcases the model-change detection system.
The UI is **not part of the system**. It only demonstrates how the system behaves.

## What it shows
- Pick the model a company says it uses.
- Paste a chatbot answer, or load a real collected answer written by one of our models.
- Click **Check** to see whether the answer matches the declared model, the family and version guess with confidence, and the model card.

## Requirements
- Python 3.10 or newer
- The `cards/` folder from this repo (the demo imports the team's model card code)
- Optional: the collected data in `collector/data/raw/` for the "Load sample answer" button

## Install and run
From the repo root:

    ./demo_ui/run_demo.sh

This creates a virtual environment in `demo_ui/.venv`, installs `demo_ui/requirements.txt`, and starts the app. Open http://localhost:8501 if it does not open automatically.

Manual steps, if you prefer:

    cd demo_ui
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    streamlit run app.py

## Current status
The detection step is a **placeholder**. `identify()` in `backend.py` returns a fixed result until the real identifier is plugged in.
Do not read the match/mismatch result as real detection yet.

## Files
- `app.py`: the Streamlit page
- `backend.py`: calls the system and builds the model card
- `requirements.txt`: Python dependencies
- `run_demo.sh`: one-command setup and launch
