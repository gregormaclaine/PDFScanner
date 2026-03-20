import io
import os
from google.cloud import vision
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()

# We check for environment variable path for service account
GOOGLE_CREDS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# Client logic initialized if needed, but per request we should also check credentials
def get_vision_client():
    # AUDIT: Using the EU regional endpoint for data residency (Belgium/europe-west1)
    client_options = {"api_endpoint": "eu-vision.googleapis.com"}
    
    if not GOOGLE_CREDS_PATH:
        # Fallback to default auth if path not set
        return vision.ImageAnnotatorClient(client_options=client_options)
    return vision.ImageAnnotatorClient.from_service_account_json(
        GOOGLE_CREDS_PATH, 
        client_options=client_options
    )

async def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """
    Pass the raw PDF bytes to Google Cloud Vision API for OCR. 
    Note: For PDF files, we should use async_batch_annotate_files for 
    a more robust OCR, but for a standard sync OCR on simple images/PDF, 
    one document can be extracted this way.
    For production, it's often better to convert PDF to high-quality 
    images in-memory if batch processing is not preferred.
    """
    client = get_vision_client()

    # Create the document representation for the API
    # Since we are using standard PDF as input, it must follow Vision API requirements 
    # for pdf/tiff. Google Cloud Vision requires a GCS source for PDF documents 
    # more than a few pages via async_batch_annotate.
    # To keep it stateless and avoid disk, we'll try for single page image if we convert 
    # it or use Vision's direct PDF support.
    
    # Actually, Google Cloud Vision's direct PDF support requires Google Cloud Storage.
    # For a completely stateless version without GCS, we can convert PDF pages to images.
    
    # I'll use PyMuPDF to convert PDF to images in memory before passing to Vision for individual OCR.
    import fitz # PyMuPDF
    
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_text = []

    for page in doc:
        # Convert page to image (pixmap)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) # higher resolution for better OCR
        img_bytes = pix.tobytes("png")
        
        # Call Vision for this image
        image = vision.Image(content=img_bytes)
        response = client.text_detection(image=image)
        
        if response.error.message:
            raise Exception(f"Vision API Error: {response.error.message}")
        
        texts = response.text_annotations
        if texts:
            all_text.append(texts[0].description) # [0] is the whole page text block
            
    doc.close()
    return "\n".join(all_text)
