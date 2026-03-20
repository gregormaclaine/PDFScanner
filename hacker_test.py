import requests
import time

class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    BRIGHT = '\033[1m'

BASE_URL = "http://127.0.0.1:8000"
VALID_EMAIL = "test@harrisandtrotter.co.uk"
VALID_PASSWORD = "password123"
INVALID_EMAIL = "hacker@evil.com"
BAD_PASSWORD = "wrongpassword"
API_KEY = "your-super-secret-api-key"

def print_banner(test_name):
    print(f"\n{Colors.CYAN}{Colors.BRIGHT}[*] RUNNING TEST: {test_name}{Colors.RESET}")

def verify(condition, success_msg, fail_msg):
    if condition:
        print(f"{Colors.GREEN}[+] SUCCESS: {success_msg}{Colors.RESET}")
        return True
    else:
        print(f"{Colors.RED}[-] FAILURE: {fail_msg}{Colors.RESET}")
        return False

print(f"{Colors.MAGENTA}{Colors.BRIGHT}--- SECURE API HACKER AUDIT ---{Colors.RESET}")

# 1. Health check (Should be open)
print_banner("Unauthenticated Health Check")
try:
    res = requests.get(f"{BASE_URL}/health")
    verify(res.status_code == 200, "Health endpoint reachable without auth.", f"Health endpoint blocked (Status: {res.status_code}).")
except Exception as e:
    print(f"{Colors.RED}[-] ERROR connecting to server: {e}{Colors.RESET}")
    exit(1)

# 2. Login with malicious domain
print_banner("Login - Invalid Domain Email (Validation Check)")
res = requests.post(f"{BASE_URL}/login", json={"email": INVALID_EMAIL, "password": VALID_PASSWORD})
verify(res.status_code == 422, f"Caught invalid domain (Status: {res.status_code}, Expected 422).", f"Failed to catch invalid domain (Status: {res.status_code}).")

# 3. Login with incorrect password
print_banner("Login - Wrong Password")
res = requests.post(f"{BASE_URL}/login", json={"email": VALID_EMAIL, "password": BAD_PASSWORD})
verify(res.status_code == 401, f"Rejected wrong password (Status: {res.status_code}, Expected 401).", f"Failed to reject wrong password (Status: {res.status_code}).")

# 4. Auth flow and extracting token
print_banner("Login - Extracting JWT Token")
# Using random real IP to bypass active limits if we hit them in previous tests
import uuid
res = requests.post(f"{BASE_URL}/login", json={"email": VALID_EMAIL, "password": VALID_PASSWORD}, headers={"X-Forwarded-For": f"10.0.0.{uuid.uuid4().int % 255}"})

token = None
if res.status_code == 200:
    token = res.json().get("access_token")
    verify(True, "Obtained valid JWT Token.", "")
elif res.status_code == 429:
    print(f"{Colors.YELLOW}[!] Getting rate limited (429). Generating a new spoofed IP header...{Colors.RESET}")
    # Retry once more with different ip
    for _ in range(3):
        res = requests.post(f"{BASE_URL}/login", json={"email": VALID_EMAIL, "password": VALID_PASSWORD}, headers={"X-Forwarded-For": f"10.0.1.{uuid.uuid4().int % 255}"})
        if res.status_code == 200:
            token = res.json().get("access_token")
            verify(True, "Obtained valid JWT Token after spoofed retry.", "")
            break

if not token:
    verify(False, "", f"Could not obtain JWT token. Status: {res.status_code}, Response: {res.text}")

# 5. Upload without Auth
print_banner("Upload - Missing Authentication")
res = requests.post(f"{BASE_URL}/upload", files={"file": ("test.pdf", b"%PDF-1.4...", "application/pdf")})
verify(res.status_code == 401, "Blocked unauthenticated upload.", f"Allowed unauthenticated upload: {res.status_code}")

if token:
    # 6. Upload without API Key
    print_banner("Upload - Missing Internal API Key")
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.post(f"{BASE_URL}/upload", headers=headers, files={"file": ("test.pdf", b"%PDF-1.4...", "application/pdf")})
    verify(res.status_code == 401, f"Blocked missing X-API-Key (Status: {res.status_code}).", f"Allowed missing X-API-Key: {res.status_code}")

    # 7. Upload malicious file (Fake MIME)
    print_banner("Upload - File Signature Bypass (Malicious Executable disguised as PDF)")
    headers = {"Authorization": f"Bearer {token}", "X-API-Key": API_KEY}
    # Send an executable file disguised as PDF (incorrect magic bytes)
    fake_exe_content = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xFF\xFF\x00\x00 This is malware"
    res = requests.post(f"{BASE_URL}/upload", headers=headers, files={"file": ("virus.pdf", fake_exe_content, "application/pdf")})
    verify(res.status_code == 400, f"Blocked invalid file signature (Magic Bytes check passed. Status: {res.status_code}).", f"Allowed invalid file signature: {res.status_code}")

    # 8. Rate Limiting testing (bursting requests)
    print_banner("Rate Limit Test - Upload (Bursting 15 requests)")
    blocked = False
    for i in range(15):
        res = requests.post(f"{BASE_URL}/upload", headers=headers, files={"file": ("test.pdf", b"%PDF-1.4... magic bytes here but not really valid enough", "application/pdf")})
        if res.status_code == 429:
            blocked = True
            break
    verify(blocked, "Upload rate limited (429 Too Many Requests).", "Rate limit failed. Burst attack allowed.")

print(f"\n{Colors.MAGENTA}{Colors.BRIGHT}--- AUDIT SUMMARY COMPLETE ---{Colors.RESET}")
