import io
import os
import magic
import base64
import unicodedata
from urllib.parse import quote
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse, RedirectResponse
from dotenv import load_dotenv


# --- Local Security, Middleware & Auth Layer ---
from security.auth import (
    create_access_token, verify_password, require_secure_role, 
    LoginRequest, Token, ADMIN_PASSWORD_HASH, USER_PASSWORD_HASH
)
from security.middleware import SecurityAuditMiddleware
from security.rate_limit import setup_rate_limiting, limiter

# --- Local Service Layer ---
from services.ocr import extract_text_from_pdf_bytes
from services.llm import parse_document_metadata, DocumentMetadata
from services.naming import generate_pdf_filename

# LOAD ENVIRONMENT
load_dotenv()

# --- STEP 1: FAIL-FAST AUDIT (Ensure all production secrets are loaded) ---
REQUIRED_VARS = [
    "INTERNAL_API_KEY", "JWT_SECRET", 
    "OPENAI_API_KEY", "ADMIN_PASSWORD_HASH", "USER_PASSWORD_HASH"
]
missing_vars = [v for v in REQUIRED_VARS if not os.getenv(v)]
if missing_vars:
    # We raise a RuntimeError to prevent server from starting without critical security settings
    raise RuntimeError(f"Audit Critical Failure: Missing security environment variables: {', '.join(missing_vars)}")

# --- APP INITIALIZATION ---
app = FastAPI(
    title="Secure Document Processing API - Audit Hardened",
    description="Accounting Firm PDF Processor (Stateless, Production-Ready Security Layer)",
    version="2.0.0",
    docs_url="/docs", # Automated OpenAPI
    redoc_url=None,   # Disabled for extra security
    debug=False       # Force debug mode OFF for production safety
)

# --- STEP 2: AUDIT - CORS LOCKDOWN ---
# Multiple allowed origins can be comma-separated in the environment variable
raw_origins = os.getenv("ALLOWED_ORIGIN", "http://localhost:3000")
allowed_origins_list = [o.strip() for o in raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    allow_credentials=True,
)

# --- STEP 3: AUDIT - SECURITY & AUDIT MIDDLEWARE ---
# Handles security headers (nosniff, HSTS, frame-options), structured logging, and ID tracking
app.add_middleware(SecurityAuditMiddleware)

# --- STEP 4: AUDIT - PER-IP RATE LIMITING ---
setup_rate_limiting(app)

# Configuration settings
MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25MB Enforcement (Increased for large files)
MAX_TEXT_SIZE = 300_000  # Arbitrary limit (characters) to prevent LLM overload (can be adjusted based on needs)

# --- ROOT & FAVICON REDIRECTS ---

@app.get("/", include_in_schema=False)
async def root():
    """Redirects to documentation for better internal developer experience."""
    return RedirectResponse(url="/docs")

@app.get("/health", tags=["System"])
async def health_check():
    """Simple status check - unauthenticated."""
    return {"status": "OK", "message": "Secure pipeline is operational"}

# --- STEP 5: AUDIT - AUTHENTICATION (POST /login) ---

@app.post("/login", 
          response_model=Token, 
          tags=["Authentication"])
@limiter.limit("5 per minute")
async def login(request: Request, login_data: LoginRequest):
    """
    Secure login endpoint for internal staff.
    - Rate limited to prevent brute force.
    - Domain restricted to @harrisandtrotter.co.uk.
    - Password verified against hashed environment secret.
    """
    role = None
    if USER_PASSWORD_HASH and verify_password(login_data.password, USER_PASSWORD_HASH):
        role = "user"
    elif ADMIN_PASSWORD_HASH and verify_password(login_data.password, ADMIN_PASSWORD_HASH):
        role = "admin"
    else:
        # Generic 401 response to prevent credential enumeration
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Generate 1-hour JWT with the assigned role
    access_token = create_access_token(data={"email": login_data.email, "role": role})
    return {"access_token": access_token, "token_type": "bearer"}

# --- STEP 6: AUDIT - SECURE PROCESSING (POST /upload) ---

@app.post("/upload", 
          tags=["Document Processing"],
          dependencies=[Depends(require_secure_role(["user", "admin"]))]) # Requires JWT AND X-API-KEY
@limiter.limit("200 per minute") # Increased to allow bulk processing
async def upload_pdf(request: Request, file: UploadFile = File(...)):
    """
    Accepts PDF, extracts metadata, renames, and returns in-memory.
    
    Security Controls:
    - 2-factor auth (Bearer Token + X-API-Key header)
    - Rate limited per IP
    - Strict MIME & Signature (Magic Bytes) validation
    - Sanitized LLM extractions
    - NO disk persistence
    - NO document content logging
    """

    # 1. AUDIT - MIME TYPE VALIDATION
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Forbidden file type. Only application/pdf allowed."
        )
    
    # 2. AUDIT - SIZE VALIDATION
    if file.size is None or file.size > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds strictly enforced 10MB limit."
        )

    # 3. READ CONTENT ONCE (Memory-only)
    pdf_content = await file.read()

    # 4. AUDIT - DEEP SIGNATURE VALIDATION (Magic Bytes)
    mime_detector = magic.Magic(mime=True)
    detected_mime = mime_detector.from_buffer(pdf_content[:2048]) # Check first 2kb
    if detected_mime != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File signature mismatch. Document is not a valid PDF."
        )

    try:
        # 5. OCR EXTRACTION (Stateless)
        ocr_text = await extract_text_from_pdf_bytes(pdf_content)
        
        if not ocr_text or len(ocr_text.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="OCR extraction failure. Ensure the PDF is not encrypted or blank."
            )
        
        if len(ocr_text) > MAX_TEXT_SIZE: # Arbitrary limit to prevent LLM overload
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="OCR text exceeds maximum allowed length for processing."
            )

        # 7. LLM METADATA PARSING (Strict Schema)
        metadata: DocumentMetadata = await parse_document_metadata(ocr_text)

        # 8. SECURE NAMING (Input Sanitized)
        sanitized_filename = generate_pdf_filename(metadata)

        # 9. RESPONSE CONSTRUCTION (Security headers)
        # 1. Create a safe-ASCII fallback for legacy/simple clients
        ascii_fallback = unicodedata.normalize('NFKD', sanitized_filename).encode('ascii', 'ignore').decode('ascii')
        
        # 2. Modern UTF-8 encoding (RFC 5987) for complex characters
        safe_filename = quote(sanitized_filename)
        
        # 3. Base64 encode metadata (same as before)
        encoded_metadata = base64.b64encode(metadata.model_dump_json().encode('utf-8')).decode('utf-8')

        headers = {
            "Content-Disposition": f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{safe_filename}',
            "X-Document-Metadata": encoded_metadata,
            "Access-Control-Expose-Headers": "Content-Disposition, X-Document-Metadata"
        }

        # Return original bytes with new secure filename (STATLESS, NO DISK)
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers=headers
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        # Errors are handled by the SecurityAuditMiddleware to shield details
        raise e

# --- STEP 7: AUDIT - ADMIN ENDPOINTS (GET /admin/test) ---

@app.get("/admin/test", 
         tags=["Admin"],
         dependencies=[Depends(require_secure_role(["admin"]))])
async def admin_dashboard():
    """
    Placeholder endpoint to test admin-only access logic.
    """
    return {"message": "Welcome Admin! You have sufficient privileges."}

if __name__ == "__main__":
    import uvicorn
    # Use environment vars for host/port; defaults to Localhost for security
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", 8000))
    # reload=False for production feel and prevent reload logging
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
