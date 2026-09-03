import os
import datetime
import gspread
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import re
import base64
SHEET_COLUMNS = ["Name", "Date", "Status", "Headline", "Short Description", "Image Link", "Linkedin", "Website Article Link"]

def append_to_sheet(sheet_id, data_list):
    """
    Appends a row to a Google Sheet.
    Requires a 'credentials.json' file (Service Account key) in the project directory.
    data_list MUST be 8 values in this exact order: SHEET_COLUMNS
    (Name, Date, Status, Headline, Short Description, Image Link, Linkedin, Website Article Link).
    """
    cred_path = "credentials.json"
    if not os.path.exists(cred_path):
        raise FileNotFoundError(f"{cred_path} not found. Cannot connect to Google Sheets.")
        
    gc = gspread.service_account(filename=cred_path)
    sheet = gc.open_by_key(sheet_id).sheet1
    
    sheet.append_row(data_list)
    return True

def update_sheet_row(sheet_id, row_index, data_list):
    """
    Updates a specific row in a Google Sheet (Columns A through E).
    Leaves other columns (like F) untouched.
    """
    cred_path = "credentials.json"
    if not os.path.exists(cred_path):
        raise FileNotFoundError(f"{cred_path} not found.")
        
    gc = gspread.service_account(filename=cred_path)
    sheet = gc.open_by_key(sheet_id).sheet1
    
    # Determine range based on length of data_list (e.g., 5 items -> A:E)
    end_col = chr(ord('A') + len(data_list) - 1)
    cell_range = f'A{row_index}:{end_col}{row_index}'
    
    sheet.update(cell_range, [data_list])
    return True
    
def upload_to_imgbb(file_path, api_key):
    """
    Uploads an image to ImgBB and returns the direct public URL.
    """
    url = "https://api.imgbb.com/1/upload"
    with open(file_path, "rb") as file:
        payload = {
            "key": api_key,
            "image": base64.b64encode(file.read()),
        }
        res = requests.post(url, data=payload)
        
    if res.status_code == 200:
        return res.json()['data']['url']
    else:
        raise Exception(f"ImgBB upload failed: {res.text}")

def upload_to_drive(file_path, folder_id_or_url):
    """
    Uploads a file to a specific Google Drive folder and returns the public view link.
    Requires 'credentials.json' and the folder to be shared with the Service Account.
    """
    # Extract ID if a full URL was passed
    folder_id = folder_id_or_url
    if "drive.google.com" in folder_id:
        match = re.search(r'folders/([a-zA-Z0-9_-]+)', folder_id)
        if match:
            folder_id = match.group(1)
            
    cred_path = "credentials.json"
    if not os.path.exists(cred_path):
        raise FileNotFoundError(f"{cred_path} not found.")
        
    creds = service_account.Credentials.from_service_account_file(
        cred_path, scopes=['https://www.googleapis.com/auth/drive']
    )
    service = build('drive', 'v3', credentials=creds)
    
    file_metadata = {
        'name': os.path.basename(file_path),
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, mimetype='image/jpeg', resumable=True)
    
    # Upload file
    file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    file_id = file.get('id')
    
    # Make it readable to anyone with the link
    service.permissions().create(
        fileId=file_id,
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()
    
    return file.get('webViewLink')

def post_to_linkedin(access_token, text_content, image_path=None):
    """
    Posts content to LinkedIn using the LinkedIn REST API.
    (Simplified text-only version; image upload requires a 3-step asset registration process in LinkedIn API).
    """
    if not access_token:
        raise ValueError("LinkedIn access token is missing.")
        
    # 1. Get the author's URN (User ID)
    profile_url = "https://api.linkedin.com/v2/userinfo"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    profile_resp = requests.get(profile_url, headers=headers)
    if profile_resp.status_code != 200:
        raise Exception(f"Failed to fetch LinkedIn profile: {profile_resp.text}")
        
    person_urn = f"urn:li:person:{profile_resp.json().get('sub')}"
    
    # 2. Create the post (Text only for this simple implementation)
    # Note: Full image attachment requires the /assets API, which is complex. 
    # For a robust solution, we often use a scheduler webhook (like Make.com) instead.
    post_url = "https://api.linkedin.com/v2/ugcPosts"
    post_data = {
        "author": person_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": text_content
                },
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }
    
    post_resp = requests.post(post_url, headers=headers, json=post_data)
    if post_resp.status_code == 201:
        return post_resp.json().get("id")
    else:
        raise Exception(f"Failed to post to LinkedIn: {post_resp.text}")

def get_article_url(author_name):
    """
    Fetches the article URL from xploreadmin.xlri.ac.in matching the author's name.
    """
    if not author_name or author_name.strip() == "Unknown" or author_name.strip() == "Unknown Student":
        return ""
        
    try:
        url = "https://xploreadmin.xlri.ac.in/wp-json/wp/v2/students-insight?acf_format=standard&_fields=id,title,slug,acf&per_page=100"
        page = 1
        target_name = author_name.strip().lower()
        
        while page <= 5: # Limit to 5 pages
            res = requests.get(f"{url}&page={page}").json()
            if not res or (isinstance(res, dict) and 'code' in res):
                break
            
            for item in res:
                acf_author = item.get('acf', {}).get('author_name', '').strip().lower()
                if not acf_author:
                    continue
                # Check for a match (target is in acf or acf is in target)
                if target_name in acf_author or acf_author in target_name:
                    return f"https://xplore.xlri.ac.in/students-insight/{item['slug']}"
            
            page += 1
    except Exception as e:
        print(f"Error fetching article URL from Xplore: {e}")
        
    return ""
