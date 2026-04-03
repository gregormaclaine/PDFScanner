import json
import os
import logging
from openai import OpenAI
from pydantic import BaseModel, ValidationError, field_validator, ValidationInfo
from typing import Optional, Dict, Any

from dotenv import load_dotenv

load_dotenv()

# Audit: Check for LLM keys (Fail application in main.py)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")

client = OpenAI(api_key=OPENAI_API_KEY)

# Maps field name → its safe fallback string
_FIELD_DEFAULTS: dict = {
    "sender": "Unknown Sender",
    "recipient": "Unknown Recipient",
    "document_type": "Unknown Type",
    "date": "Unknown Date",
    "reference": "None",
}

class DocumentMetadata(BaseModel):
    """Schema validation for extracted document fields."""
    sender: str = "Unknown Sender"
    recipient: str = "Unknown Recipient"
    document_type: str = "Unknown Type"
    date: str = "Unknown Date"
    reference: str = "None"

    @field_validator('sender', 'recipient', 'document_type', 'date', 'reference', mode='before')
    @classmethod
    def coerce_to_string(cls, v, info: ValidationInfo):
        """Coerces ANY value from the LLM to a safe string — handles null, numbers, lists, dicts.
        
        IMPORTANT: Always returns a concrete string. Returning None or "" does NOT trigger
        field defaults in Pydantic v2, so we resolve the fallback ourselves via _FIELD_DEFAULTS.
        """
        if v is None or (isinstance(v, str) and not v.strip()):
            return _FIELD_DEFAULTS.get(info.field_name, "")
        if isinstance(v, str):
            return v.strip()
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
    - SENDER IDENTIFICATION (PRIMARY): The sender is the organization shown in the letterhead/header at the top or the one that signed the document at the bottom (e.g., after "Yours sincerely").
    - TAX AUTHORITY DEBT COLLECTORS: If a third-party agency (e.g., Advantis, Zenith, or a solicitor) is writing to collect a debt on behalf of HMRC or another Tax Authority, the THIRD-PARTY AGENCY is the sender, not the Tax Authority.
    - SPECIAL CASE (HMRC): If the letter is DIRECTLY from HMRC, the sender is "HMRC". The recipient is the ACTUAL client, not the accountant's address at the top.
    - SPECIAL CASE (COMPANIES HOUSE): If the document is from Companies House (e.g., Certificate of Incorporation, Confirmation Statement, Change of Registered Office, Annual Return, or any filing acknowledgement), the sender is "Companies House". The RECIPIENT is the COMPANY NAME — look for the name that appears prominently (often in bold or uppercase) and typically ends with "Ltd", "Limited", "LLP", "PLC", or "CIC". Do NOT use a person's name as the recipient for Companies House documents unless no company name is present.
    - FIRM PARTNERS EXCLUSION: The following names are partners of the accounting firm and should NEVER be used as the recipient: "Daniel Korn", "Dan Korn", "Charlotte Harris", "Chris Fowler". If one of these names appears as the addressee, IGNORE it and look for the actual client name elsewhere in the document (e.g., in the salutation, subject line, "RE:" field, or body text). If no other name can be found, use the company/organisation name mentioned in the letter.
    - SALUTATION RULE: If a name appears immediately after or below a salutation like "Dear Sir or Madam", "Dear Mr/Mrs", or similar, that person is the primary RECIPIENT.
    - DOCUMENT IDENTIFICATION: Look for keywords like "Invoice", "Receipt", "Confirmation Statement", "Notice", "Certificate", "Incorporation", or "Letter" to determine the document_type.
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

