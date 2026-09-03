import os
import glob
import shutil
import time
from dotenv import load_dotenv
from eml_parser import parse_eml
from ai_services import generate_text_content, generate_background_poster
from composer import compose_poster
from operations import append_to_sheet, upload_to_imgbb, get_article_url

def run_batch():
    load_dotenv()
    sheet_id = os.getenv("SHEET_ID")
    imgbb_key = os.getenv("IMGBB_API_KEY")
    
    input_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Article EMLs")
    completed_dir = os.path.join(input_dir, "Completed")
    os.makedirs(completed_dir, exist_ok=True)
    
    # Get all .eml files in the main directory (ignores those already moved to Completed)
    eml_files = glob.glob(os.path.join(input_dir, "*.eml"))
    
    if not eml_files:
        print("No new EML files found to process.")
        return
        
    print(f"Found {len(eml_files)} articles to process.\n")
    
    for eml_path in eml_files:
        filename = os.path.basename(eml_path)
        print(f"=== Processing: {filename} ===")
        try:
            # 1. Parse Email
            output_dir = "output"
            parsed_data = parse_eml(eml_path, output_dir)
            
            # 2. AI Content Generation
            print("   -> Extracting details & writing summary via Gemini...")
            title, summary, image_prompt, extracted_name = generate_text_content(parsed_data['text'])
            
            # Smart Name Fallback: If Gemini didn't find a name, use the email 'From' header
            final_name = extracted_name if extracted_name and extracted_name.strip() != "Unknown" else parsed_data.get('author_name', 'Unknown Student')
            print(f"   -> Author: {final_name}")
            
            # 3. AI Poster Generation
            print("   -> Generating Studio Infographic via NotebookLM...")
            base_poster = os.path.join(output_dir, f"base_{final_name.replace(' ', '_')}.jpg")
            try:
                generate_background_poster(parsed_data['text'], image_prompt, base_poster)
            except Exception as e:
                print(f"   -> [API Error] {e}. Using mock background.")
                from main import create_mock_base_poster
                create_mock_base_poster(base_poster)
            
            # 4. Compose Final Poster
            print("   -> Running facial recognition crop & applying master layout grid...")
            final_poster = os.path.join(output_dir, f"final_{final_name.replace(' ', '_')}.jpg")
            compose_poster(
                base_image_path=base_poster, 
                profile_image_path=parsed_data['photo_path'], 
                title=title, 
                author_name=final_name, 
                output_path=final_poster
            )
            
            # 5. Upload to ImgBB
            poster_url = final_poster
            if imgbb_key:
                print("   -> Uploading poster to ImgBB...")
                poster_url = upload_to_imgbb(final_poster, imgbb_key)
            
            # 5.5 Fetch Article URL
            print("   -> Fetching Article URL from Xplore Website...")
            article_url = get_article_url(final_name)
            if article_url:
                print(f"   -> Found URL: {article_url}")
            else:
                print(f"   -> No matching URL found for {final_name}")

            # 6. Append to Google Sheet (New Row at the Bottom)
            print("   -> Appending new row to Google Sheet...")
            # Column order (see operations.SHEET_COLUMNS): Name, Date, Status, Headline, Short Description, Image Link, Linkedin, Website Article Link
            email_date = parsed_data.get('email_date', '')
            data = [final_name, email_date, '', title, summary, poster_url, parsed_data.get('linkedin_url', ''), article_url]
            append_to_sheet(sheet_id, data)
            
            # 7. Move to Completed Folder
            shutil.move(eml_path, os.path.join(completed_dir, filename))
            print(f"✅ Successfully processed {final_name} and moved file to 'Completed' folder.\n")
            
            print("⏳ Waiting 1 second before next article...")
            time.sleep(1)
            
        except Exception as e:
            print(f"❌ Critical Error processing {filename}: {e}\n")

if __name__ == "__main__":
    run_batch()
