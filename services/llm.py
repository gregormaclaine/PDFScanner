import json
import os
import logging
from openai import OpenAI
from pydantic import BaseModel, ValidationError, field_validator
from typing import Optional, Dict, Any

from dotenv import load_dotenv

load_dotenv()

# Audit: Check for LLM keys (Fail application in main.py)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")

client = OpenAI(api_key=OPENAI_API_KEY)

class DocumentMetadata(BaseModel):
    """Schema validation for extracted document fields."""
    sender: Optional[str] = "Unknown Sender"
    recipient: Optional[str] = "Unknown Recipient"
    document_type: Optional[str] = "Unknown Type"
    date: Optional[str] = "Unknown Date"
    reference: Optional[str] = "None"

    @field_validator('sender', 'recipient', 'document_type', 'date', 'reference', mode='before')
    @classmethod
    def coerce_null_to_default(cls, v):
        """Coerces None or empty string values from the LLM to safe fallback strings."""
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None  # Let the field default kick in
        return v

async def parse_document_metadata(ocr_text: str) -> DocumentMetadata:
    """
    Extracts structured metadata from OCR text while ensuring:
    - NO logging of document contents
    - Strict JSON output format
    - Schema validation via Pydantic
    - Resistance to malformed responses
    """
    
    # Prompt is slightly hardened to handle potential injection/messy text
    prompt = f"""
    You are a professional auditor for an accounting firm. 
    Analyze the provided OCR text and extract structured metadata.

    OCR TEXT BLOCK:
    \"\"\"
    {ocr_text}
    \"\"\"

    EXTRACT THE FOLLOWING FIELDS AS VALID JSON ONLY:
    - sender
    - recipient
    - document_type
    - date
    - reference

    RULES:
    - If a field is missing, use empty string "".
    - ONLY output the JSON object. No narrative or chat markers.
    """

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a professional accounting data extractor. Output JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0, # High audit-level precision
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Zero-length response from LLM provider")
        
        # 1. VALIDATE: JSON Structure
        metadata_dict = json.loads(content)
        
        # 2. VALIDATE: Schema adherence
        # This will raise a ValidationError if the LLM hallucinated keys
        validated_metadata = DocumentMetadata(**metadata_dict)
        
        return validated_metadata

    except ValidationError as ve:
        # LOGGING AUDIT: Do not log the 'content' or 've' if it contains OCR snippets
        raise Exception("LLM returned non-compliant metadata schema.")
    except Exception as e:
        # LOGGING AUDIT: Sanitized error
        raise Exception("Failure in document data parsing layer.")
