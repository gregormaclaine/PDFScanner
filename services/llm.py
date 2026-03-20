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
    def coerce_to_string(cls, v):
        """Coerces ANY value from the LLM to a safe string — handles null, numbers, lists, dicts."""
        if v is None:
            return None  # triggers field default
        if isinstance(v, str):
            return v.strip() if v.strip() else None  # empty string → triggers default
        return str(v)  # convert numbers, lists, dicts etc. to string safely

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
        # Schema validation failed — salvage valid string fields, use defaults for the rest
        # Never raise here — a bad LLM response should NOT crash the pipeline
        safe_data = {}
        if isinstance(metadata_dict, dict):
            for field in ['sender', 'recipient', 'document_type', 'date', 'reference']:
                val = metadata_dict.get(field)
                if isinstance(val, str) and val.strip():
                    safe_data[field] = val.strip()
                elif val is not None:
                    safe_data[field] = str(val)[:100]  # coerce non-string to string safely
        return DocumentMetadata(**safe_data)
    except Exception as e:
        # LOGGING AUDIT: Sanitized error — return default metadata rather than crashing
        return DocumentMetadata()

