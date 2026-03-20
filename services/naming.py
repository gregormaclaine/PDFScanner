import re
from pydantic import BaseModel

class DocumentMetadata(BaseModel):
    """Schema for extracted document fields."""
    sender: str
    recipient: str
    document_type: str
    date: str
    reference: str

def sanitize_extracted_field(field: str, max_length: int = 30) -> str:
    """
    Sanitizes extracted document text before it is used in filenames to prevent:
    - Path traversal (../../etc/passwd)
    - Injection attacks
    - Metadata poisoning
    - Overly long filenames from addresses or full descriptions
    """
    if not field:
        return ""
    
    # 1. ALLOW ONLY SAFE CHARACTERS: Alphanumeric, spaces, dashes only.
    sanitized = re.sub(r'[^a-zA-Z0-9\s\-]', '', field)
    
    # 2. NORMALISE WHITESPACE
    sanitized = " ".join(sanitized.split()).strip()

    # 3. SMART TRUNCATION: Cut at word boundary to avoid splitting mid-word
    if len(sanitized) > max_length:
        truncated = sanitized[:max_length]
        # Step back to the last complete word
        last_space = truncated.rfind(" ")
        if last_space > 0:
            sanitized = truncated[:last_space]
        else:
            sanitized = truncated
    
    return sanitized

def generate_pdf_filename(metadata: DocumentMetadata) -> str:
    """
    Generates a secure PDF filename using sanitized metadata components.
    Target Format: "{recipient} - {sender} - {document_type} - {date}.pdf"
    """
    
    # 1. SANITIZE EACH COMPONENT
    recipient = sanitize_extracted_field(metadata.recipient) or "UnknownRecipient"
    sender = sanitize_extracted_field(metadata.sender) or "UnknownSender"
    doc_type = sanitize_extracted_field(metadata.document_type) or "UnknownType"
    date = sanitize_extracted_field(metadata.date) or "UnknownDate"

    # 2. CONSTRUCT FINAL FILENAME
    raw_filename = f"{recipient} - {sender} - {doc_type} - {date}"

    # 3. FINAL TRAVERSAL PROTECT: Double-check for path identifiers
    final_name = raw_filename.replace("..", "_").replace("/", "_").replace("\\", "_")

    return f"{final_name}.pdf"
