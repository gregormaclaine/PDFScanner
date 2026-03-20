import requests
import sys
import os

# --- CONFIGURATION ---
BASE_URL = "http://127.0.0.1:8000"
INTERNAL_API_KEY = "your-super-secret-api-key"
EMAIL = "test@harrisandtrotter.co.uk"
PASSWORD = "H&T" # Swap to H&Tadmin to test admin privileges

def upload_pdf(pdf_path: str):
    if not os.path.exists(pdf_path):
        print(f"[-] Error: Could not find file at {pdf_path}")
        sys.exit(1)

    print(f"\n[*] 1. Authenticating as {EMAIL}...")
    login_res = requests.post(f"{BASE_URL}/login", json={"email": EMAIL, "password": PASSWORD})
    
    if login_res.status_code != 200:
        print(f"[-] Login failed: {login_res.text}")
        sys.exit(1)
        
    token = login_res.json().get("access_token")
    print("[+] Login successful! JWT Token acquired.")

    print(f"\n[*] 2. Uploading {os.path.basename(pdf_path)}...")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "X-API-Key": INTERNAL_API_KEY
    }
    
    with open(pdf_path, "rb") as f:
        # Pass the file explicitly as application/pdf under the form key 'file'
        files = {"file": (os.path.basename(pdf_path), f, "application/pdf")}
        upload_res = requests.post(f"{BASE_URL}/upload", headers=headers, files=files)

        if upload_res.status_code == 200:
            print("[+] Document Processed Successfully!")
            
            # Print extracted LLM metadata if the server exposes it in headers
            metadata = upload_res.headers.get("X-Document-Metadata")
            if metadata:
                print(f"[+] Extracted Metadata: {metadata}")

            # Look for the new sanitized filename in Content-Disposition
            content_disp = upload_res.headers.get("Content-Disposition", "")
            if "filename=" in content_disp:
                new_filename = content_disp.split("filename=")[-1].strip('"')
            else:
                new_filename = f"processed_{os.path.basename(pdf_path)}"
                
            # Save the processed bytes directly to disk
            output_path = os.path.join(os.path.dirname(pdf_path), new_filename)
            with open(output_path, "wb") as out_pdf:
                out_pdf.write(upload_res.content)
            
            print(f"[+] Processed file saved directly to: {output_path}\n")
            
        else:
            print(f"[-] Upload failed (Status: {upload_res.status_code}): {upload_res.text}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python upload_tool.py <path_to_your_pdf>")
    else:
        upload_pdf(sys.argv[1])
