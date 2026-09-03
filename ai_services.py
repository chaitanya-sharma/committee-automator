import os
import json
import requests
from google import genai

def generate_text_content(article_text):
    """
    Uses Google Gemini API (Free tier) to generate a title and summary.
    Requires GEMINI_API_KEY in environment.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment.")
        
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    You are an expert LinkedIn copywriter for the 'Xplore' business committee. Read the following article submitted by a student.
    Provide a JSON response with four keys: "author_name", "title", "summary", and "image_prompt".
    
    RULES FOR "author_name":
    - Extract the full name of the student who wrote the article. If you cannot find it in the text, return "Unknown".
    
    RULES FOR "title":
    - A punchy, engaging, thought-provoking title.
    - CRITICAL: The title MUST be strictly under 90 characters in total length.
    
    RULES FOR "summary":
    - MUST contain exactly 5 short paragraphs.
    - Para 1: A sharp hook or question based on the article's core theme.
    - Para 2 & 3: Deeper explanation of the core problem or insight.
    - Para 4: Exactly this sentence: "In this latest article, [AUTHOR_NAME] explores [briefly summarize what they explore based on the article]."
    - Para 5: Exactly this sentence: "Read the full article on the Xplore website and join the conversation."
    - CRITICAL: Do NOT use any hashtags whatsoever.
    
    RULES FOR "image_prompt":
    - Write an extensive, highly detailed visual narrative that captures the deepest nuances and broader themes of the article. 
    - This prompt should be about 20% to 30% longer than the LinkedIn summary to provide maximum context to the image generation model.
    - Translate the article's core arguments into a cohesive, highly descriptive, literal scene. Describe the specific subjects, environments, metaphors, and interactions in extreme detail.
    - Do NOT include calls to action or non-visual text (like "In this article..."). Focus entirely on setting a vivid, comprehensive scene.
    - MUST include these exact styling keywords at the very end: "8k resolution, ultra-crisp, sharp, highly professional corporate editorial illustration, flat vector style, vibrant vivid colors, balanced composition, perfectly representative, absolutely NO text."
    Article:
    {article_text}
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        data = json.loads(response.text)
        return data.get("title", "Generated Title"), data.get("summary", "Generated Summary"), data.get("image_prompt", "Corporate background"), data.get("author_name", "Unknown")
    except json.JSONDecodeError:
        print("Failed to parse JSON from LLM. Raw output:", response.text)
        return "New Student Article", "Read the latest article from our committee.", "Professional corporate background", "Unknown"
    except Exception as e:
        print(f"Failed LLM generation (Quota/Network error: {e}). Using mock fallback.")
        return "Mock: Committee AI Strategy", "Mock summary since Gemini quota is exceeded.", "Mock background of a tech startup office", "Unknown"

import subprocess
import json
import time
import shutil

NLM_BIN = shutil.which("nlm") or os.path.expanduser("~/.local/bin/nlm")

# Validated against 10 style/focus combinations tested by hand (see project notes).
# Both families produce zero-text, LinkedIn-appropriate art; anything outside
# these two failed review (dense infographic text, cartoon panels, nudity, or
# literal toy/LEGO rendering). Each family has two focus-wording variants so
# repeated runs don't all look identical.
NLM_VARIANTS = [
    {
        "label": "editorial_ink_a",
        "style": "editorial",
        "detail": "concise",
        "focus": "Single bold visual metaphor, ink and watercolor editorial illustration style, muted elegant palette. Zero text of any kind, no captions, no labels, no words.",
    },
    {
        "label": "editorial_ink_b",
        "style": "editorial",
        "detail": "concise",
        "focus": "Single striking visual metaphor rendered as a fine-line ink and wash illustration, restrained sepia and slate palette, magazine-editorial quality. Absolutely zero text, no captions, no labels.",
    },
    {
        "label": "fullbleed_scene_a",
        "style": "auto_select",
        "detail": "standard",
        "focus": "Single cohesive full-canvas illustrated scene, professional editorial style, balanced composition, rich detail filling the frame. Absolutely zero text, no captions, no labels, no words anywhere.",
    },
    {
        "label": "fullbleed_scene_b",
        "style": "auto_select",
        "detail": "standard",
        "focus": "Single dramatic full-frame conceptual illustration, cinematic lighting, sophisticated corporate-editorial mood, composition filling the entire canvas. Absolutely zero text, no words, no labels anywhere.",
    },
]


def _nlm(args, timeout=120):
    """Run an `nlm` CLI subcommand and return its parsed --json output."""
    result = subprocess.run(
        [NLM_BIN] + args + ["--json"],
        capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"nlm {' '.join(args)} failed: {result.stdout}\n{result.stderr}")
    return json.loads(result.stdout)


def _wait_for_artifact(notebook_id, artifact_id, poll_interval=15, max_wait=300):
    waited = 0
    while waited < max_wait:
        statuses = _nlm(["studio", "status", notebook_id, "--artifact-id", artifact_id])
        if statuses and statuses[0].get("status") == "completed":
            return True
        time.sleep(poll_interval)
        waited += poll_interval
    return False


def generate_background_candidates(article_text, output_dir, base_name, num_variants=4):
    """
    Creates a NotebookLM notebook from the article, generates `num_variants`
    zero-text infographic candidates (drawn from NLM_VARIANTS), and returns
    their local file paths for review/selection. Requires `nlm` to be
    installed and authenticated (see: nlm login).
    """
    os.makedirs(output_dir, exist_ok=True)
    variants = NLM_VARIANTS[:num_variants]

    notebook = _nlm(["notebook", "create", f"Committee Auto - {base_name}"])
    notebook_id = notebook["notebook_id"]
    try:
        src_path = os.path.join(output_dir, f".{base_name}_source.txt")
        with open(src_path, "w") as f:
            f.write(article_text)
        _nlm(["source", "add", notebook_id, "--file", src_path,
              "--title", "Student Article", "--wait"], timeout=180)
        os.remove(src_path)

        artifact_ids = []
        for i, v in enumerate(variants):
            if i > 0:
                time.sleep(30)  # NotebookLM rate-limits rapid infographic creation
            created = None
            for attempt in range(6):
                try:
                    created = _nlm(["infographic", "create", notebook_id,
                                     "--orientation", "square",
                                     "--detail", v["detail"],
                                     "--style", v["style"],
                                     "--focus", v["focus"],
                                     "--confirm"])
                    break
                except RuntimeError as e:
                    if "Rate limited" in str(e) and attempt < 5:
                        wait_s = 180
                        print(f"   -> [Rate limited on '{v['label']}', waiting {wait_s}s before retry ({attempt+1}/5)...]")
                        time.sleep(wait_s)
                    else:
                        raise
            artifact_ids.append((v["label"], created["artifact_id"]))

        candidates = []
        for label, artifact_id in artifact_ids:
            if not _wait_for_artifact(notebook_id, artifact_id):
                print(f"   -> [Variant '{label}' timed out, skipping]")
                continue
            out_path = os.path.join(output_dir, f"{base_name}_{label}.png")
            for dl_attempt in range(3):
                dl = subprocess.run(
                    [NLM_BIN, "download", "infographic", notebook_id,
                     "--id", artifact_id, "--output", out_path, "--no-progress"],
                    capture_output=True, text=True, timeout=60
                )
                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    break
                print(f"   -> [Download attempt {dl_attempt+1} failed for '{label}': {dl.stdout} {dl.stderr}]")
                time.sleep(10)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                candidates.append({"label": label, "path": out_path})
            else:
                print(f"   -> [Giving up on downloading '{label}' after 3 attempts]")

        return candidates, notebook_id
    except Exception:
        raise


def generate_background_poster(article_text, image_prompt, output_path, num_variants=4):
    """
    Generates several background candidates via NotebookLM and picks one.
    NOTE: automated selection here is a placeholder (first candidate) --
    for real batch runs, review generate_background_candidates()'s output
    and pick manually before compositing.
    """
    output_dir = os.path.dirname(output_path) or "."
    base_name = os.path.splitext(os.path.basename(output_path))[0]
    try:
        candidates, _ = generate_background_candidates(article_text, output_dir, base_name, num_variants)
        if not candidates:
            raise RuntimeError("No candidates generated")
        shutil.copy(candidates[0]["path"], output_path)
        return output_path
    except Exception as e:
        print(f"   -> [NotebookLM Generation Failed: {e}]. Using fallback...")
        from main import create_mock_base_poster
        create_mock_base_poster(output_path)
        return output_path
