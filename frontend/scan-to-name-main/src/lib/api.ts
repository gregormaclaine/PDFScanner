import { BACKEND_URL, API_KEY } from "@/config";

const TOKEN_KEY = "ht_jwt_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

async function handleResponse(res: Response) {
  if (res.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new Error("Session expired");
  }
  if (res.status === 403) {
    throw new Error("Access denied");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(text || `Request failed (${res.status})`);
  }
  return res;
}

function authHeaders(): HeadersInit {
  return {
    Authorization: `Bearer ${getToken()}`,
    "x-api-key": API_KEY,
  };
}

export async function login(email: string, password: string): Promise<string> {
  const res = await fetch(`${BACKEND_URL}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Invalid credentials");
  }

  const data = await res.json();
  const token = data.access_token || data.token;
  if (!token) throw new Error("No token received");
  setToken(token);
  return token;
}

export interface DocumentMetadata {
  sender?: string;
  recipient?: string;
  document_type?: string;
  date?: string;
  filename?: string;
  [key: string]: string | undefined;
}

export interface UploadResult {
  blob: Blob;
  filename: string;
  metadata?: DocumentMetadata;
}

export async function uploadDocument(file: File): Promise<UploadResult> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${BACKEND_URL}/upload`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });

  await handleResponse(res);

  // Try to get metadata from a custom header
  const metaHeader = res.headers.get("x-document-metadata");
  let metadata: DocumentMetadata | undefined;
  if (metaHeader) {
    try {
      metadata = JSON.parse(metaHeader);
    } catch {
      // ignore
    }
  }

  // Get filename from content-disposition or metadata
  let filename = "processed-document.pdf";
  const disposition = res.headers.get("content-disposition");
  if (disposition) {
    const match = disposition.match(/filename[^;=\n]*=[\\"']?([^\\"';\n]*)[\\"']?/);
    if (match?.[1]) filename = match[1];
  } else if (metadata?.filename) {
    filename = metadata.filename;
  }

  const contentType = res.headers.get("content-type") || "";

  // If JSON response, metadata is in body and PDF might be in a follow-up
  if (contentType.includes("application/json")) {
    const json = await res.json();
    metadata = json.metadata || json;
    filename = json.filename || filename;

    // If the JSON contains a download URL
    if (json.download_url) {
      const dlRes = await fetch(`${BACKEND_URL}${json.download_url}`, {
        headers: authHeaders(),
      });
      await handleResponse(dlRes);
      const blob = await dlRes.blob();
      return { blob, filename, metadata };
    }

    // Otherwise return empty blob — caller should handle
    return { blob: new Blob(), filename, metadata };
  }

  const blob = await res.blob();
  return { blob, filename, metadata };
}
