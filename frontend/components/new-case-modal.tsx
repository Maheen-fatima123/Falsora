"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Upload, FileImage, CheckCircle2, Loader2, AlertCircle, Info } from "lucide-react";
import { toast } from "sonner";

interface NewCaseModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCaseCreated?: (newCase: any) => void;
  /** Default true — go to case detail after a successful DB save */
  redirectToCase?: boolean;
}

export function NewCaseModal({
  isOpen,
  onClose,
  onCaseCreated,
  redirectToCase = true,
}: NewCaseModalProps) {
  const router = useRouter();
  const [subject, setSubject] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [errorMsg, setErrorMsg] = useState("");

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setErrorMsg("Only image files are supported (PNG, JPG, JPEG, WEBP).");
      return;
    }
    setErrorMsg("");
    setSelectedFile(file);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setErrorMsg("Only image files are supported (PNG, JPG, JPEG, WEBP).");
      return;
    }
    setErrorMsg("");
    setSelectedFile(file);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setErrorMsg("Please select an image to upload.");
      return;
    }
    if (selectedFile.size > 10 * 1024 * 1024) {
      setErrorMsg("Image must be 10MB or smaller.");
      return;
    }

    setErrorMsg("");
    setIsUploading(true);
    setUploadProgress(25);

    const formData = new FormData();
    formData.append("media", selectedFile);
    formData.append("title", subject || selectedFile.name || "Untitled Investigation");
    formData.append("mediaType", "image");

    try {
      setUploadProgress(65);
      let res = await fetch("http://localhost:4000/api/cases/upload", {
        method: "POST",
        credentials: "include",
        body: formData,
      });

      if (res.status === 401) {
        const refreshRes = await fetch("http://localhost:4000/api/auth/refresh", {
          method: "POST",
          credentials: "include",
        });
        if (refreshRes.ok) {
          res = await fetch("http://localhost:4000/api/cases/upload", {
            method: "POST",
            credentials: "include",
            body: formData,
          });
        }
      }

      setUploadProgress(90);
      const data = await res.json();

      if (res.ok && data.success && data.data?.id) {
        setUploadProgress(100);
        toast.success(
          data.isDuplicate
            ? data.message || "Opened your existing analysis for this image."
            : "Case saved — opening analysis…"
        );
        const created = {
          ...data.data,
          mediaUrl: data.data.mediaUrl || data.data.mediaPath,
          subject: data.data.subject || data.data.title,
        };
        onCaseCreated?.(created);
        setIsUploading(false);
        setSubject("");
        setSelectedFile(null);
        onClose();
        if (redirectToCase) {
          router.push(`/dashboard/cases/${created.id}`);
        }
      } else {
        const detail =
          data.validation?.reason ||
          data.message ||
          data.error ||
          "Failed to upload";
        setErrorMsg(detail);
        throw new Error(detail);
      }
    } catch (err: any) {
      console.error("Upload error:", err);
      toast.error(err.message || "Failed to upload investigation media.");
      setIsUploading(false);
      setUploadProgress(0);
    }
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-hidden p-0 bg-background border-border/60 shadow-2xl flex flex-col">
        <div className="p-6 pb-2 overflow-y-auto flex flex-col gap-5">
          <DialogHeader className="border-b border-border/40 pb-3">
            <DialogTitle className="text-xl font-bold font-heading">
              Check an image
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground mt-0.5">
              Upload a still image for deepfake / tampering analysis.
            </DialogDescription>
          </DialogHeader>

          {errorMsg && (
            <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 text-red-500 rounded-md text-xs">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          <div className="flex items-start gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2.5 text-xs text-muted-foreground">
            <Info className="h-4 w-4 text-primary shrink-0 mt-0.5" />
            <p>
              <span className="font-medium text-foreground">Images only for this release.</span>{" "}
              Upload PNG, JPG, JPEG, or WEBP (max 10MB). Files are checked by content
              (not just extension), then resized for analysis. Video and audio are not
              available in the current showcase.
            </p>
          </div>

          <form id="new-case-form" onSubmit={handleSubmit} className="flex flex-col gap-5">
            <div className="space-y-1.5">
              <Label htmlFor="subject" className="text-xs font-medium">
                Title (optional)
              </Label>
              <Input
                id="subject"
                placeholder="e.g. Suspicious social media photo"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="bg-background/50 text-sm"
              />
            </div>

            <div
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragOver(true);
              }}
              onDragLeave={() => setIsDragOver(false)}
              onDrop={handleFileDrop}
              className={`border-2 border-dashed rounded-lg p-6 flex flex-col items-center justify-center text-center transition-all cursor-pointer ${
                isDragOver
                  ? "border-primary bg-primary/10"
                  : selectedFile
                    ? "border-emerald-500/50 bg-emerald-500/5"
                    : "border-border/60 hover:border-primary/50 bg-muted/20"
              }`}
              onClick={() => document.getElementById("dialog-file-input")?.click()}
            >
              <input
                id="dialog-file-input"
                type="file"
                className="hidden"
                onChange={handleFileSelect}
                accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
              />

              {selectedFile ? (
                <div className="flex flex-col items-center gap-2">
                  <CheckCircle2 className="h-8 w-8 text-emerald-500" />
                  <span className="text-sm font-medium text-foreground truncate max-w-xs">
                    {selectedFile.name}
                  </span>
                  <span className="text-xs text-muted-foreground font-mono">
                    {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
                  </span>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center mb-1">
                    <FileImage className="h-5 w-5 text-muted-foreground" />
                  </div>
                  <p className="text-sm font-medium">Drag & drop an image here</p>
                  <p className="text-xs text-muted-foreground">
                    PNG, JPG, JPEG, WEBP · Max 15MB
                  </p>
                </div>
              )}
            </div>

            {isUploading && (
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Saving to database…</span>
                  <span>{uploadProgress}%</span>
                </div>
                <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all duration-300"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              </div>
            )}
          </form>
        </div>

        <DialogFooter className="m-0 px-6 py-4 rounded-b-xl border-t bg-muted/50 flex flex-row justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={isUploading}
            className="cursor-pointer"
          >
            Cancel
          </Button>
          <Button
            type="submit"
            form="new-case-form"
            disabled={isUploading || !selectedFile}
            className="gap-2 cursor-pointer"
          >
            {isUploading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            {isUploading ? "Uploading…" : "Start analysis"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
