import os
from dotenv import load_dotenv
from eml_parser import parse_eml
from composer import compose_poster
from ai_services import generate_text_content, generate_background_poster
from operations import append_to_sheet, post_to_linkedin, upload_to_imgbb
def run_pipeline(eml_file_path):
    # Load environment variables from .env file
    load_dotenv()
    
    print(f"--- Starting Pipeline for {eml_file_path} ---")
    output_dir = "output"
    
    # 1. Parse EML
    print("\n1. Parsing EML...")
    parsed_data = parse_eml(eml_file_path, output_dir)
    print(f"   -> Extracted Text length: {len(parsed_data['text'])} chars")
    print(f"   -> Found LinkedIn URL: {parsed_data['linkedin_url']}")
    print(f"   -> Saved Photo Attachment to: {parsed_data['photo_path']}")
    
    # 2. LLM Summarization & Title Generation
    print("\n2. Generating Title and Summary via Gemini LLM...")
    if os.getenv("GEMINI_API_KEY"):
        generated_title, generated_summary, image_prompt, extracted_name = generate_text_content(parsed_data['text'])
        print(f"   -> Generated Title: {generated_title}")
    else:
        print("   -> [MOCK FALLBACK] GEMINI_API_KEY not found. Using mock text.")
        generated_title = "Building Multi-Agent Systems for Committee Automation"
        generated_summary = "An exploration of how AI and procedural code can automate tedious data entry and asset creation tasks for student committees. #AI #Automation"
    
    # 3. Image Generation (Base Poster)
    print("\n3. Generating Base Poster via Hugging Face...")
    base_poster_path = os.path.join(output_dir, "base_poster.jpg")
    if os.getenv("GEMINI_API_KEY"): # If AI is active, try to generate the poster
        try:
            generate_background_poster(parsed_data['text'], image_prompt, base_poster_path)
            print("   -> Fetched background successfully.")
        except Exception as e:
            print(f"   -> [Generation Error] {e}. Falling back to clean background.")
            create_mock_base_poster(base_poster_path)
    else:
        print("   -> [MOCK FALLBACK] Missing API keys. Using clean background.")
        create_mock_base_poster(base_poster_path)
    
    # 4. Compose Final Digital Poster
    print("\n4. Compositing final image...")
    final_poster_path = os.path.join(output_dir, "final_linkedin_post.jpg")
    author_name = parsed_data.get('author_name', 'Unknown')
    compose_poster(
        base_image_path=base_poster_path,
        profile_image_path=parsed_data['photo_path'],
        title=generated_title,
        author_name=author_name,
        output_path=final_poster_path
    )
    
    # 5. Operations & Publishing (Google Sheets & LinkedIn)
    print("\n5. Updating Google Sheets & Scheduling on LinkedIn...")
    
    # Google Sheets Integration
    sheet_id = os.getenv("SHEET_ID")
    if sheet_id and os.path.exists("credentials.json"):
        try:
            # ImgBB Upload
            imgbb_key = os.getenv("IMGBB_API_KEY")
            poster_url = final_poster_path
            if imgbb_key:
                print("   -> Uploading poster to ImgBB...")
                poster_url = upload_to_imgbb(final_poster_path, imgbb_key)
                print(f"   -> Uploaded successfully: {poster_url}")

            data = [
                author_name,
                generated_title,
                generated_summary,
                poster_url,
                parsed_data.get('linkedin_url', ''),
                "" # Website Article Link
            ]
            append_to_sheet(sheet_id, data)
            print(f"   -> Successfully appended {author_name}'s record to Google Sheet.")
        except Exception as e:
            print(f"   -> [Sheets Error] {e}")
    else:
        print("   -> [MOCK FALLBACK] Google Sheets credentials missing. Skipping live Sheet update.")
        print(f"      (Would have appended: {generated_title} | {parsed_data['linkedin_url']})")

    # LinkedIn Publishing Integration
    li_token = os.getenv("LINKEDIN_ACCESS_TOKEN")
    full_post_text = f"{generated_summary}\n\nRead more from our author: {parsed_data['linkedin_url']}"
    if li_token:
        try:
            post_id = post_to_linkedin(li_token, full_post_text, final_poster_path)
            print(f"   -> Successfully posted to LinkedIn! (ID: {post_id})")
        except Exception as e:
            print(f"   -> [LinkedIn Error] {e}")
    else:
        print("   -> [MOCK FALLBACK] LINKEDIN_ACCESS_TOKEN missing. Skipping live LinkedIn post.")
        print(f"      (Would have posted text:\n{full_post_text}\n      )")
    
    print("\n--- Pipeline Complete ---")

def create_mock_base_poster(path):
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (1080, 1080), color = (73, 109, 137))
    d = ImageDraw.Draw(img)
    d.text((100, 400), "BASE BACKGROUND (Mocked)", fill=(255, 255, 255))
    img.save(path)

if __name__ == "__main__":
    test_eml = "test_data/sample.eml"
    if not os.path.exists(test_eml):
        print(f"Please place a test EML file at {test_eml} to run the pipeline.")
    else:
        run_pipeline(test_eml)
