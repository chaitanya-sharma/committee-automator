import email
import re
import os
import email.utils
from email import policy


def _ensure_pil_readable(image_path):
    """
    PIL can't open HEIC/HEIF (common for iPhone photo attachments) without
    a plugin. If the attachment is one of those, convert it to JPEG so
    composer.py's face-crop/compositing step doesn't silently skip the
    photo. Any other format is returned unchanged.
    """
    ext = os.path.splitext(image_path)[1].lower()
    if ext not in (".heic", ".heif"):
        return image_path
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        from PIL import Image
        converted_path = os.path.splitext(image_path)[0] + ".jpg"
        Image.open(image_path).convert("RGB").save(converted_path, "JPEG", quality=95)
        return converted_path
    except Exception as e:
        print(f"   -> [Could not convert HEIC photo {image_path}: {e}]")
        return image_path


def parse_eml(file_path, output_dir):
    """
    Parses an EML file, extracts the text content, LinkedIn URL, and the first image attachment.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(file_path, 'rb') as f:
        msg = email.message_from_binary_file(f, policy=policy.default)
        
    from_header = msg.get('From', '')
    author_name = email.utils.parseaddr(from_header)[0] or "Unknown Student"

    date_header = msg.get('Date', '')
    email_date = ""
    parsed_dt = email.utils.parsedate_to_datetime(date_header) if date_header else None
    if parsed_dt:
        email_date = parsed_dt.strftime("%d %b %Y")

    body_text = ""
    linkedin_url = None
    photo_path = None
    
    markdown_attachment_text = ""
    for part in msg.walk():
        content_type = part.get_content_type()
        content_disposition = str(part.get_content_disposition())

        # Extract Text
        if content_type == "text/plain" and "attachment" not in content_disposition:
            body_text += part.get_content()
        elif content_type == "text/html" and "attachment" not in content_disposition and not body_text:
             # Fallback if no plain text
             body_text += part.get_content()
        elif content_type in ("text/markdown", "text/x-markdown") and "attachment" in content_disposition:
            # Some submissions send the article as a .md attachment instead of the email body
            markdown_attachment_text += part.get_content()

        # Extract Image Attachment
        if "image" in content_type and part.get_filename():
            filename = part.get_filename()
            # Save the first image found as the student photo
            if not photo_path:
                raw_path = os.path.join(output_dir, filename)
                with open(raw_path, 'wb') as img_f:
                    img_f.write(part.get_payload(decode=True))
                photo_path = _ensure_pil_readable(raw_path)

    # If the email body is just a short cover note, prefer the markdown attachment as the article
    if markdown_attachment_text and len(markdown_attachment_text) > len(body_text):
        body_text = markdown_attachment_text
                    
    # Find LinkedIn URL in text
    # Basic regex for linkedin profiles (protocol and www. are both optional in source text)
    li_match = re.search(r'((?:https?://)?(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+)', body_text)
    if li_match:
        linkedin_url = li_match.group(1)
        if not linkedin_url.startswith('http'):
            linkedin_url = 'https://' + linkedin_url
        
    return {
        "author_name": author_name,
        "text": body_text,
        "linkedin_url": linkedin_url,
        "photo_path": photo_path,
        "email_date": email_date,
        "email_datetime": parsed_dt
    }
