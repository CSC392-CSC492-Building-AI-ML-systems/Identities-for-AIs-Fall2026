# Model Change Monitor (demo UI)

A small Streamlit app that showcases the model-change detection system.
The UI is **not part of the system**. It only demonstrates how the system behaves.

## What it shows
The app has two pages, switched in the sidebar.

**Check a chatbot**
- Pick the model running behind a company's chatbot (all 11 known models, plus newer models the system has never seen, if their data is available).
- Click **Ask the chatbot six questions** to load that model's real collected answers, or paste in answers from any chatbot.
- Click **Check chatbot** to see:
  - a status: Verified, Identified, Drift detected, Needs review or Unknown model
  - the fit score (how well the answers match), with the 70% minimum marked
  - the developer, family and version the system found
  - a note when the result is handed off to the next method (LoRA, then random forest)
  - why the system decided this
  - the model card for the chosen domain (compliance, governance, evaluation or risk)
- Pick an **approved chatbot** in the sidebar to turn on the drift check. The system then says whether the model behind it has changed.

**Register a chatbot**
- Give a chatbot a name, pick its approved model and a bank system prompt (BK1 to BK4), and click **Register chatbot**.
- This saves the chatbot's baseline (how its approved model normally answers the six questions). It then appears in the sidebar under **Approved chatbot**.
- It uses our collected answers (`--replay`), so it is free and makes no API calls.

## Requirements
- Python 3.10 or newer
- These folders side by side in the repo: `agent/`, `cards/`, `collector/` and `demo_ui/`
- The collected data in `collector/data/raw/<model>/`. The model dropdown only lists models that have data, and the demo needs it to load answers and to register chatbots.
- `pyyaml` and `streamlit` in `demo_ui/requirements.txt` (the agent code needs pyyaml)
- For real detection (not test mode): `GEMINI_API_KEY` in `collector/.env`. Never commit this file.

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

Run `streamlit run app.py` from inside `demo_ui/`, so the theme file is found.

## Test mode vs real mode
- **Test mode** (on by default, checkbox in the sidebar) uses a fake judge. No API calls, no cost, but the results are not real detection. The page shows a notice while it is on.
- **Real mode**: untick Test mode. This calls the Gemini judge (about $0.008 per check).

## Drift check
The drift check tells you if the model behind a registered chatbot has been swapped.

1. Open the **Register a chatbot** page and register one, for example `northshore` with Llama 3.1 8B and BK1.
2. Go back to **Check a chatbot** and choose it under **Approved chatbot (drift check)**.
3. In step 1, pick a *different* model and load its answers.
4. Click **Check chatbot**. You should see **Drift detected**.

Picking the same model should show **Verified**. The persona the Check page loads (`DEMO_PERSONA` in `app.py`, set to BK1) should match the persona you registered with.

You can also register from the command line, from the `agent/` folder:

    python check_chatbot.py register --deployment northshore --model llama3.1-8b --persona BK1 --replay

## Suggested demo run
1. A known model, no approved chatbot: should show **Identified** with the exact version and its model card.
2. A swap with the drift check on: should show **Drift detected**.
3. A never-seen model (for example Claude Haiku 5.5): should show the right developer, version **Unknown**, and the developer card.

## Tests: is the UI showing the right results?
`test_ui.py` checks that the UI sends the right things to Tiana's system and shows the right things back. It does not test the model's accuracy; Tiana's own tests do that (`agent/run_all_tests.sh`). Each test has a comment saying what it proves.

From `demo_ui/`, in the same Python environment as the app:

    pip install pytest
    python -m pytest test_ui.py -v                 # everything (live tests run only if GEMINI_API_KEY is set)
    python -m pytest test_ui.py -v -m "not live"   # free tests only
    python -m pytest test_ui.py -v -m live         # live tests only

There are three kinds:
- **Plumbing** (free, no data): the six questions match the system's, the inputs reach the system unchanged, test mode picks the right judge, every status is handled, bad chatbot names are rejected.
- **Offline** (free, needs collected data): Tiana's real code runs with a fixed judge. Checks that loaded answers come from the right model's file, the result has every field the page draws, the card has the shape the page expects, Register works, no-swap gives no false alarm, and a swap gives Drift detected.
- **Live** (a few cents, needs `GEMINI_API_KEY`): the real judge. Checks the developer is right for known models, most exact versions are right (Tiana measured 81%), a swap is detected (97%), and a never-seen model gets version Unknown.

Tests that need data skip themselves if the data is missing. Live results can vary a little because the judge is not perfectly repeatable, so re-run a failing live test before assuming something is broken.

A quick manual check as well: save the answers from the page as `answers.json` and run `python identify_api.py answers.json --domain compliance --judge-provider mock` from `agent/`. The result should match what the page shows.

## Look and theme
The page uses a light theme with a navy and blue palette. The theme is set in `.streamlit/config.toml` (copy it to `demo_ui/.streamlit/config.toml`), and extra styling is in the `CSS` block at the top of `app.py`. Fonts (IBM Plex Sans and Source Serif 4) load from Google Fonts. Without internet the page falls back to system fonts.

## Files
- `app.py`: the Streamlit app (both pages and all styling)
- `backend.py`: calls the system (`agent/identify_api.py`), lists the models and registered chatbots, loads collected answers, and registers chatbots
- `test_ui.py`: tests for the UI (see above)
- `.streamlit/config.toml`: forces the light theme
- `requirements.txt`: Python dependencies (must include `streamlit` and `pyyaml`; add `pytest` to run the tests)
- `run_demo.sh`: one-command setup and launch

## Troubleshooting
- **"No answers found for this model"**: that model's data is not in `collector/data/raw/<model>/`. Check the folder name against `VERSION_TO_KEY` in `backend.py`.
- **A model is missing from the dropdown**: same cause. The dropdown hides models with no data.
- **The approved chatbot list is empty**: register one on the Register page.
- **Register fails**: open the Details box on the page to see the message. Common causes are missing data for that model and persona, or `pyyaml` missing from the environment running Streamlit.
- **Error about `yaml`**: add `pyyaml` to `requirements.txt` and reinstall.
- **Error about the API key**: add `GEMINI_API_KEY` to `collector/.env`, or turn on Test mode.
- **Tests skip a lot**: the collected data is missing or in a different folder than `collector/data/raw/`.