import re
from pydantic import BaseModel

class DocumentMetadata(BaseModel):
    """Schema for extracted document fields."""
    sender: str
    recipient: str
    document_type: str
    date: str
    reference: str


# Common document label words the LLM sometimes includes verbatim
# Stripped as complete words (case-insensitive) before filename generation
LABEL_WORDS = {
    "name", "address", "from", "to", "sender", "recipient",
    "mr", "mrs", "ms", "dr", "prof",
    "attn", "attention", "contact"
}

def strip_label_words(text: str) -> str:
    """
    Removes common document label words that the LLM returns verbatim.
    e.g. "name Cameron Maclaine address" -> "Cameron Maclaine"
    """
    words = text.split()
    filtered = [w for w in words if w.lower() not in LABEL_WORDS]
    return " ".join(filtered)

def sanitize_extracted_field(field: str, max_length: int = 30) -> str:
    """
    Sanitizes extracted document text before it is used in filenames to prevent:
    - Path traversal (../../etc/passwd)
    - Injection attacks
    - Metadata poisoning
    - Overly long filenames from addresses or full descriptions
    - Stray label words from LLM output (name, address, from, etc.)
    """
    # 1. SPLIT CONCATENATED TITLE PREFIXES (e.g. "MrIA" -> "Mr IA")
    # This ensures titles are identified as separate words even if spaces are missing.
    sanitized = re.sub(r'\b(Mr|Mrs|Ms|Dr|Prof)([A-Z])', r'\1 \2', field, flags=re.IGNORECASE)

    # 2. REPLACE PUNCTUATION WITH SPACES TO PREVENT CONCATENATION:
    # e.g. "Mr.I.A. Anderson" -> "Mr I A Anderson"
    sanitized = re.sub(r'[./_:]', ' ', sanitized)
    
    # 3. ALLOW ONLY SAFE CHARACTERS: Alphanumeric, spaces, dashes only.
    sanitized = re.sub(r'[^a-zA-Z0-9\s\-]', '', sanitized)
    
    # 4. STRIP COMMON LABEL WORDS
    sanitized = strip_label_words(sanitized)

    # 5. NORMALISE WHITESPACE
    sanitized = " ".join(sanitized.split()).strip()

    # 4. SMART TRUNCATION: Cut at word boundary to avoid splitting mid-word
    if len(sanitized) > max_length:
        truncated = sanitized[:max_length]
        last_space = truncated.rfind(" ")
        if last_space > 0:
            sanitized = truncated[:last_space]
        else:
            sanitized = truncated
    
    return sanitized


def generate_pdf_filename(metadata: DocumentMetadata, content_hash: str = None) -> str:
    """
    Generates a secure PDF filename using sanitized metadata components.
    Target Format: "{recipient} - {sender} - {document_type} - {date} [REF-{reference}] [HASH].pdf"
    """
    
    # 1. SANITIZE EACH COMPONENT
    recipient = sanitize_extracted_field(metadata.recipient) or "UnknownRecipient"
    sender = sanitize_extracted_field(metadata.sender) or "UnknownSender"
    doc_type = sanitize_extracted_field(metadata.document_type) or "UnknownType"
    # Ensure date is safe for filenames
    date = sanitize_extracted_field(metadata.date) or "UnknownDate"

    # 2. CONSTRUCT FINAL FILENAME
    # Target format with reference to ensure uniqueness for audit trails
    raw_filename = f"{recipient} - {sender} - {doc_type} - {date}"
    
    # 3. APPEND REFERENCE IF AVAILABLE (Crucial for preventing overwriting)
    ref_id = sanitize_extracted_field(metadata.reference or "", max_length=15)
    if ref_id and ref_id.lower() != "none" and ref_id.strip():
        raw_filename += f" [REF {ref_id}]"

    # 4. APPEND OPTIONAL HASH (To guarantee uniqueness for bulk operations)
    if content_hash:
        raw_filename += f" [{content_hash[:6]}]"

    # 5. FINAL TRAVERSAL PROTECT: Double-check for path identifiers
    final_name = raw_filename.replace("..", "_").replace("/", "_").replace("\\", "_")

    return f"{final_name}.pdf"
