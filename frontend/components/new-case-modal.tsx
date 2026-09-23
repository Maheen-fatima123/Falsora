"use client";

import React, { useState } from "react";
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
import { Upload, FileVideo, FileImage, FileAudio, CheckCircle2, Loader2, AlertCircle } from "lucide-react";
import { toast } from "sonner";

interface NewCaseModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCaseCreated: (newCase: any) => void;
}

export function NewCaseModal({ isOpen, onClose, onCaseCreated }: NewCaseModalProps) {
  const [subject, setSubject] = useState("");
  const [mediaType, setMediaType] = useState<"video" | "image" | "audio">("image");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [errorMsg, setErrorMsg] = useState("");

  const mediaConfig = {
    image: {
      accept: "image/jpeg,image/png,image/webp",
      dragText: "Drag & drop human face image evidence here",
      supportText: "Supports PNG, JPG, JPEG, WEBP (Max 15MB)",
    },
    video: {
      accept: "video/mp4,video/quicktime,video/webm",
      dragText: "Drag & drop video evidence here",
      supportText: "Supports MP4, MOV, WEBM (Max 100MB)",
    },
    audio: {
      accept: "audio/mpeg,audio/wav,audio/aac,audio/m4a",
      dragText: "Drag & drop audio evidence here",
      supportText: "Supports MP3, WAV, AAC, M4A (Max 50MB)",
    },
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setSelectedFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile && !subject) {
      setErrorMsg("Please select a file or enter an investigation subject.");
      return;
    }

    setErrorMsg("");
    setIsUploading(true);
    setUploadProgress(25);

    const formData = new FormData();
    if (selectedFile) formData.append("media", selectedFile);
    formData.append("title", subject || selectedFile?.name || "Untitled Investigation");
    formData.append("mediaType", mediaType);

    try {
      setUploadProgress(65);
      const res = await fetch("http://localhost:4000/api/cases/upload", {
        method: "POST",
        credentials: "include",
        body: formData,
      });

      setUploadProgress(90);
      const data = await res.json();

      if (res.ok && data.success) {
        setUploadProgress(100);
        toast.success("New investigation case created & evidence uploaded!");
        setTimeout(() => {
          onCaseCreated(data.data);
          setIsUploading(false);
          setSubject("");
          setSelectedFile(null);
          onClose();
        }, 400);
      } else {
        throw new Error(data.message || "Failed to upload");
      }
    } catch (err: any) {
      console.error("Upload error:", err);
      toast.error(err.message || "Failed to upload investigation media.");
      // Client-side fallback
      const fallbackCase = {
        id: `CAS-${Math.floor(100 + Math.random() * 900)}`,
        subject: subject || selectedFile?.name || "Untitled Investigation",
        status: "Analyzing",
        date: new Date().toISOString().split("T")[0],
        confidence: "...",
      };
      onCaseCreated(fallbackCase);
      setIsUploading(false);
      onClose();
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-hidden p-0 bg-background border-border/60 shadow-2xl flex flex-col">
        {/* Scrollable Form Body */}
        <div className="p-6 pb-2 overflow-y-auto flex flex-col gap-5">
          <DialogHeader className="border-b border-border/40 pb-3">
            <DialogTitle className="text-xl font-bold font-heading">Initiate New Investigation</DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground mt-0.5">
              Upload media evidence for AI deepfake and manipulation analysis.
            </DialogDescription>
          </DialogHeader>

          {errorMsg && (
            <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 text-red-500 rounded-md text-xs">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          <form id="new-case-form" onSubmit={handleSubmit} className="flex flex-col gap-5">
            {/* Subject Title */}
            <div className="space-y-1.5">
              <Label htmlFor="subject" className="text-xs font-medium">Investigation Subject / Title</Label>
              <Input
                id="subject"
                placeholder="e.g. Political Speech Deepfake Analysis"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="bg-background/50 text-sm"
              />
            </div>

            {/* Media Type Selector */}
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">Media Type</Label>
              <div className="grid grid-cols-3 gap-2">
                <Button
                  type="button"
                  variant={mediaType === "video" ? "default" : "outline"}
                  size="sm"
                  onClick={() => { setMediaType("video"); setSelectedFile(null); }}
                  className="gap-2 text-xs cursor-pointer"
                >
                  <FileVideo className="h-4 w-4" /> Video
                </Button>
                <Button
                  type="button"
                  variant={mediaType === "image" ? "default" : "outline"}
                  size="sm"
                  onClick={() => { setMediaType("image"); setSelectedFile(null); }}
                  className="gap-2 text-xs cursor-pointer"
                >
                  <FileImage className="h-4 w-4" /> Image
                </Button>
                <Button
                  type="button"
                  variant={mediaType === "audio" ? "default" : "outline"}
                  size="sm"
                  onClick={() => { setMediaType("audio"); setSelectedFile(null); }}
                  className="gap-2 text-xs cursor-pointer"
                >
                  <FileAudio className="h-4 w-4" /> Audio
                </Button>
              </div>
            </div>

            {/* Drag & Drop Upload Zone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
              onDragLeave={() => setIsDragOver(false)}
              onDrop={handleFileDrop}
              className={`border-2 border-dashed rounded-lg p-6 flex flex-col items-center justify-center text-center transition-all cursor-pointer ${
                isDragOver ? "border-primary bg-primary/10" : selectedFile ? "border-emerald-500/50 bg-emerald-500/5" : "border-border/60 hover:border-primary/50 bg-muted/20"
              }`}
              onClick={() => document.getElementById("dialog-file-input")?.click()}
            >
              <input
                id="dialog-file-input"
                type="file"
                className="hidden"
                onChange={handleFileSelect}
                accept={mediaConfig[mediaType].accept}
              />

              {selectedFile ? (
                <div className="flex flex-col items-center gap-2">
                  <CheckCircle2 className="h-8 w-8 text-emerald-500" />
                  <span className="text-sm font-medium text-foreground truncate max-w-xs">{selectedFile.name}</span>
                  <span className="text-xs text-muted-foreground font-mono">{(selectedFile.size / (1024 * 1024)).toFixed(2)} MB</span>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center mb-1">
                    <Upload className="h-5 w-5 text-muted-foreground" />
                  </div>
                  <p className="text-sm font-medium">{mediaConfig[mediaType].dragText}</p>
                  <p className="text-xs text-muted-foreground">{mediaConfig[mediaType].supportText}</p>
                </div>
              )}
            </div>

            {/* Upload Progress Bar */}
            {isUploading && (
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Ingesting Media...</span>
                  <span>{uploadProgress}%</span>
                </div>
                <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                  <div className="h-full bg-primary transition-all duration-300" style={{ width: `${uploadProgress}%` }} />
                </div>
              </div>
            )}
          </form>
        </div>

        {/* Dialog Footer Flush at Bottom */}
        <DialogFooter className="m-0 px-6 py-4 rounded-b-xl border-t bg-muted/50 flex flex-row justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={isUploading} className="cursor-pointer">
            Cancel
          </Button>
          <Button type="submit" form="new-case-form" disabled={isUploading} className="gap-2 cursor-pointer">
            {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            {isUploading ? "Uploading..." : "Start Analysis"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
