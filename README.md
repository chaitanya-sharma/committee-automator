# Committee Automator

Turns student article submissions (`.eml` files) into ready-to-post LinkedIn posters, fully automatically:

`.eml` file → parse text + extract photo → Gemini writes a title/summary → NotebookLM generates a background illustration → Python composites a poster (photo + title + byline) → poster uploaded → row appended to a Google Sheet.

This document is the full setup guide: what each piece does, the exact folder layout the code expects, every prerequisite, and step-by-step instructions to get it running on a new machine — including the NotebookLM piece, which is the least standard part of the stack.

---

## 1. How it fits together

```
 .eml file
    │
    ▼
eml_parser.py   ──▶  plain text, author name, LinkedIn URL, photo file
    │
    ▼
ai_services.py  ──▶  Gemini: title, 5-paragraph summary, image prompt
    │            ──▶  NotebookLM (via the `nlm` CLI): background illustration (PNG)
    ▼
composer.py     ──▶  Pillow + OpenCV: crops the photo to a face-centered circle,
    │                 lays a banner + title + byline over the background,
    │                 outputs a single 1080x1080 poster
    ▼
operations.py   ──▶  uploads the poster to ImgBB, appends a row to Google Sheets
    ▼
batch_run.py    ──▶  the orchestrator: loops this over every .eml in Article EMLs/,
                      moves each one to Article EMLs/Completed/ when done
```

Each `.py` file is a single-responsibility module — `batch_run.py` is the only one you actually run; the rest are imported by it.

---

## 2. Folder structure (and why it's named this way)

```
committee-automator/
├── batch_run.py              # entry point — run this
├── eml_parser.py              # .eml → text/photo/LinkedIn extraction
├── ai_services.py             # Gemini text gen + NotebookLM image gen
├── composer.py                # image compositing (face crop, layout, typography)
├── operations.py              # Google Sheets / ImgBB / (optional) Drive / LinkedIn
├── main.py                    # single-file pipeline runner + mock-poster fallback
├── requirements.txt
├── .env.example                # copy to .env and fill in your keys
├── credentials.example.json    # copy to credentials.json (Google service account)
├── assets/
│   ├── haarcascade_frontalface_default.xml   # OpenCV face-detection model
│   └── Roboto-Bold.ttf                       # font used for poster titles/bylines
├── Article EMLs/               # DROP YOUR .eml FILES HERE
│   └── Completed/              # processed files get moved here automatically
└── output/                     # generated photos/posters land here
```

**Naming convention — this matters, the code has these paths hardcoded (not configurable via env vars):**

| Name | Exactly as-typed | Why |
|---|---|---|
| `Article EMLs` | Capital A, capital E, with a space | `batch_run.py` does `os.path.join(..., "Article EMLs")` — rename it and the pipeline finds nothing to process |
| `Article EMLs/Completed` | Capital C | Where finished `.eml` files are moved so re-running the script doesn't reprocess them |
| `output` | lowercase | Where extracted photos and generated posters are written; created automatically if missing |
| `assets` | lowercase | Fixed relative path `assets/Roboto-Bold.ttf` and `assets/haarcascade_frontalface_default.xml` used by `composer.py` |
| `credentials.json` | exact filename, project root | Google service-account key; `operations.py` opens this literal filename |
| `.env` | project root | Loaded by `python-dotenv`; must sit next to `batch_run.py` |

If you're scripting a replica of this setup (including via a coding agent), **preserve these exact names and their location at the project root** — don't nest them in a `src/` folder or rename them, or every relative path in the code breaks.

---

## 3. Prerequisites

### System
- **Python 3.11+** (developed/tested on 3.14)
- **macOS, Linux, or Windows** — no OS-specific code, but the NotebookLM auth step (below) needs a real desktop browser
- **Node.js is *not* required** — earlier prototypes of this project used an npm-based NotebookLM MCP server; the current pipeline does not

### Accounts / API keys you'll need
| Service | What it's for | Where to get it |
|---|---|---|
| Google Gemini | Title/summary/image-prompt generation | https://aistudio.google.com/apikey — free tier works, has a 5 req/min limit |
| Google Cloud service account | Writing to the Google Sheet | https://console.cloud.google.com/ → IAM & Admin → Service Accounts → create key (JSON) |
| A Google Sheet | Where results get logged | Any Sheet you own — share it with the service account's `client_email` as an Editor |
| ImgBB | Free public image hosting for the poster | https://api.imgbb.com/ — free API key, no card required |
| A personal Google account with NotebookLM access | Generates the background art | See §5 below — this is the unusual one |

---

## 4. Install

```bash
git clone <this-repo-url>
cd committee-automator
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Then:
```bash
cp .env.example .env
cp credentials.example.json credentials.json
```
Fill in `.env` with your real `GEMINI_API_KEY`, `SHEET_ID`, and `IMGBB_API_KEY`. Replace `credentials.json` with your actual downloaded service-account key (same filename, project root).

**Never commit `.env` or `credentials.json` with real values** — both are in `.gitignore` for this reason.

---

## 5. Setting up NotebookLM (the `nlm` CLI)

The background-art generation step doesn't call a conventional API — NotebookLM has no public API. It works by driving your own logged-in NotebookLM session through a CLI tool (`notebooklm-mcp-cli`, binary name `nlm`). This means **each person running this pipeline needs their own Google account authenticated locally** — credentials can't be shared as an API key, and this step can't run unattended on a shared server.

### 5.1 Install `nlm`

The cleanest install method is [pipx](https://pipx.pypa.io/) (keeps it isolated from your system Python):

```bash
# macOS
brew install pipx
pipx ensurepath

# then, any OS with pipx installed:
pipx install notebooklm-mcp-cli
```

Alternative: `pip install --user notebooklm-mcp-cli` (or plain `pip install` inside a venv), but pipx is recommended so it doesn't collide with this project's own venv packages.

Confirm it installed:
```bash
nlm --version
```

### 5.2 Log in

```bash
nlm login
```
This opens a real Chrome window. Sign into the Google account you want NotebookLM to run as. Once you land on notebooklm.google.com successfully, cookies are saved locally and you won't need to log in again on that machine.

Verify:
```bash
nlm notebook list
```
should list your NotebookLM notebooks (or an empty list, not an auth error) if login succeeded.

### 5.3 What the pipeline actually calls

`ai_services.py` shells out to `nlm` as a subprocess (see `_nlm()` in that file) to:
1. `nlm notebook create` — one notebook per article
2. `nlm source add --file ...` — uploads the article text as a source
3. `nlm infographic create` — generates the background art, using one of a fixed set of style/prompt combinations tuned to produce **zero-text, LinkedIn-appropriate illustrations** (see the style list in `ai_services.py`'s `NLM_VARIANTS`)
4. `nlm studio status` — polls until the artifact is ready
5. `nlm download infographic` — downloads the PNG

No notebook cleanup is automatic — old test/working notebooks will accumulate in your NotebookLM library over time; delete them from notebooklm.google.com periodically if that bothers you.

### 5.4 Known limitation: rate limits

NotebookLM enforces an undocumented rate limit on infographic generation — in practice, roughly a dozen-plus generations in a short window will get you a `Rate limited (RESOURCE_EXHAUSTED)` error that does **not** clear in the "1-2 minutes" the error message claims; it's closer to an hourly/daily cap. `ai_services.py` already retries with backoff (up to several minutes per attempt), but if you're batch-processing many articles, expect to occasionally need to stop and resume later. There's no way around this without a different (paid) image-generation backend.

---

## 6. Running it

Drop `.eml` files into `Article EMLs/`, then:

```bash
python batch_run.py
```

Each article gets parsed, generates its own NotebookLM notebook + artwork, gets composited into a poster, uploaded to ImgBB, and appended as a row to your Google Sheet — then the source `.eml` moves to `Article EMLs/Completed/`.

`main.py` is an alternate single-file entry point (`run_pipeline(path)`) that also has LinkedIn-posting and Google Drive upload wired in, both optional/unused by default — see the commented-out env vars in `.env.example`.

---

## 7. Troubleshooting

- **`ModuleNotFoundError: No module named 'cv2'`** — you're not running inside the venv, or `opencv-python-headless` didn't install. Re-run `pip install -r requirements.txt` inside the activated venv.
- **Poster background is a plain dark rectangle** — the background image download from NotebookLM failed silently or the generation itself failed; check the console output from `ai_services.py`, it prints `[NotebookLM Generation Failed: ...]` when this happens and falls back to a mock background.
- **Photo circle shows the wrong part of the face (tie, collar, etc.)** — OpenCV's Haar cascade occasionally false-positives on a small region. `composer.py`'s `get_face_bbox()` filters out detections smaller than 15% of the image's shorter dimension for exactly this reason; if it still happens on some photo, that photo may need retaking or a manual crop.
- **`gspread.exceptions.APIError: [503]` or `[502]`** — transient Google API hiccup, just retry.
- **NotebookLM step hangs or errors with "Rate limited"** — see §5.4.

---

## 8. What's intentionally *not* in this repo

This repo contains only the working pipeline. It does not include: real `.env`/`credentials.json` values, any actual student submissions or generated posters (personal data), or the various one-off experiment/debug scripts from earlier development (Hugging Face FLUX attempts, Pollinations.ai tests, several abandoned NotebookLM-MCP integration attempts, sheet-inspection scripts, etc.) — those aren't part of the working system and would only add confusion for a new setup.
