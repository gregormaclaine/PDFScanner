import { useState, useCallback, useRef, DragEvent, ChangeEvent } from "react";
import { useNavigate } from "react-router-dom";
import { uploadDocument, clearToken, type UploadResult, type DocumentMetadata } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Upload, FileText, CheckCircle2, AlertCircle, LogOut, Download, Loader2 } from "lucide-react";

type Status = "idle" | "uploading" | "processing" | "success" | "error";

const Dashboard = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");
  const [result, setResult] = useState<UploadResult | null>(null);
  const [editMeta, setEditMeta] = useState<DocumentMetadata | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const logout = () => {
    clearToken();
    navigate("/login", { replace: true });
  };

  const reset = () => {
    setFile(null);
    setStatus("idle");
    setError("");
    setResult(null);
    setEditMeta(null);
  };

  const handleFile = (f: File) => {
    if (f.type !== "application/pdf") {
      setError("Only PDF files are accepted");
      return;
    }
    setError("");
    setFile(f);
    setStatus("idle");
    setResult(null);
    setEditMeta(null);
  };

  const onDrop = useCallback((e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFile(dropped);
  }, []);

  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) handleFile(selected);
  };

  const process = async () => {
    if (!file) return;
    setStatus("uploading");
    setError("");

    try {
      setStatus("processing");
      const res = await uploadDocument(file);
      setResult(res);

      if (res.metadata && Object.keys(res.metadata).length > 0) {
        setEditMeta({ ...res.metadata });
        setStatus("success");
      } else {
        // No metadata — auto-download
        triggerDownload(res.blob, res.filename);
        setStatus("success");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Processing failed");
      setStatus("error");
    }
  };

  const triggerDownload = (blob: Blob, filename: string) => {
    if (blob.size === 0) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const confirmDownload = () => {
    if (result) {
      triggerDownload(result.blob, result.filename);
    }
  };

  const updateMeta = (key: string, value: string) => {
    setEditMeta((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  const isProcessing = status === "uploading" || status === "processing";
  const metaFields: { key: keyof DocumentMetadata; label: string }[] = [
    { key: "sender", label: "Sender" },
    { key: "recipient", label: "Recipient" },
    { key: "document_type", label: "Document Type" },
    { key: "date", label: "Date" },
  ];

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-2xl items-center justify-between px-4 py-3">
          <h1 className="text-lg font-semibold text-foreground">Document Processor</h1>
          <Button variant="ghost" size="sm" onClick={logout} className="text-muted-foreground">
            <LogOut className="mr-1.5 h-4 w-4" />
            Sign out
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-2xl px-4 py-8">
        {/* Upload Area */}
        {status !== "success" && (
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => !isProcessing && fileInputRef.current?.click()}
            className={`
              group relative cursor-pointer rounded-lg border-2 border-dashed p-12 text-center
              transition-colors duration-200
              ${dragOver
                ? "border-primary bg-primary/5"
                : file
                  ? "border-border bg-card"
                  : "border-border hover:border-primary/40 hover:bg-muted/50"
              }
              ${isProcessing ? "pointer-events-none opacity-60" : ""}
            `}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              className="hidden"
              onChange={onFileChange}
              disabled={isProcessing}
            />

            {isProcessing ? (
              <div className="flex flex-col items-center gap-3">
                <Loader2 className="h-10 w-10 text-primary animate-spin" />
                <p className="text-sm font-medium text-foreground">
                  {status === "uploading" ? "Uploading…" : "Processing document…"}
                </p>
                <p className="text-xs text-muted-foreground">This may take a moment</p>
              </div>
            ) : file ? (
              <div className="flex flex-col items-center gap-3">
                <FileText className="h-10 w-10 text-primary" />
                <p className="text-sm font-medium text-foreground">{file.name}</p>
                <p className="text-xs text-muted-foreground">
                  {(file.size / 1024 / 1024).toFixed(1)} MB — Click to change
                </p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3">
                <Upload className="h-10 w-10 text-muted-foreground group-hover:text-primary transition-colors" />
                <p className="text-sm font-medium text-foreground">
                  Drop a PDF here or click to browse
                </p>
                <p className="text-xs text-muted-foreground">PDF files only</p>
              </div>
            )}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mt-4 flex items-start gap-2 rounded-lg bg-destructive/10 px-4 py-3">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <p className="text-sm text-destructive">{error}</p>
          </div>
        )}

        {/* Process Button */}
        {file && status === "idle" && (
          <div className="mt-4">
            <Button onClick={process} className="w-full" size="lg">
              <Upload className="mr-2 h-4 w-4" />
              Upload &amp; Process
            </Button>
          </div>
        )}

        {/* Success with Metadata */}
        {status === "success" && editMeta && (
          <div className="mt-4 space-y-4">
            <div className="flex items-center gap-2 rounded-lg bg-success/10 px-4 py-3">
              <CheckCircle2 className="h-5 w-5 text-success" />
              <p className="text-sm font-medium text-foreground">Document processed successfully</p>
            </div>

            <div className="rounded-lg border border-border bg-card p-5 space-y-3">
              <h2 className="text-sm font-semibold text-foreground">Extracted Information</h2>
              {metaFields.map(({ key, label }) => (
                <div key={key} className="space-y-1">
                  <Label htmlFor={`meta-${key}`} className="text-xs text-muted-foreground">
                    {label}
                  </Label>
                  <Input
                    id={`meta-${key}`}
                    value={editMeta[key] || ""}
                    onChange={(e) => updateMeta(key as string, e.target.value)}
                    className="h-9"
                  />
                </div>
              ))}
            </div>

            <div className="flex gap-3">
              <Button onClick={confirmDownload} className="flex-1" size="lg">
                <Download className="mr-2 h-4 w-4" />
                Confirm &amp; Download
              </Button>
              <Button onClick={reset} variant="outline" size="lg">
                New Upload
              </Button>
            </div>
          </div>
        )}

        {/* Success without metadata */}
        {status === "success" && !editMeta && (
          <div className="mt-4 space-y-4">
            <div className="flex items-center gap-2 rounded-lg bg-success/10 px-4 py-3">
              <CheckCircle2 className="h-5 w-5 text-success" />
              <p className="text-sm font-medium text-foreground">
                Document processed — download started
              </p>
            </div>
            <Button onClick={reset} variant="outline" className="w-full" size="lg">
              Process Another Document
            </Button>
          </div>
        )}

        {/* Error retry */}
        {status === "error" && (
          <div className="mt-4 flex gap-3">
            <Button onClick={process} className="flex-1" size="lg">
              Retry
            </Button>
            <Button onClick={reset} variant="outline" size="lg">
              Start Over
            </Button>
          </div>
        )}
      </main>
    </div>
  );
};

export default Dashboard;
