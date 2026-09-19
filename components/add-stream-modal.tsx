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
import { Video, Loader2, Camera } from "lucide-react";
import { fetchApi } from "@/lib/api";

interface AddStreamModalProps {
  isOpen: boolean;
  onClose: () => void;
  onStreamCreated: (newStream: any) => void;
}

export function AddStreamModal({ isOpen, onClose, onStreamCreated }: AddStreamModalProps) {
  const [title, setTitle] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    setErrorMsg("");
    setIsSubmitting(true);

    try {
      const res = await fetchApi("http://localhost:4000/api/streams", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });

      const data = await res.json();
      if (data.success) {
        onStreamCreated(data.data);
        resetAndClose();
      } else {
        setErrorMsg(data.message || "Failed to start webcam session.");
      }
    } catch (err) {
      setErrorMsg("Failed to start session. Backend might be offline.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const resetAndClose = () => {
    setTitle("");
    setErrorMsg("");
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) resetAndClose(); }}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-hidden p-0 bg-background border-border/60 shadow-2xl flex flex-col">
        {/* Scrollable Form Body */}
        <div className="p-6 pb-2 overflow-y-auto flex flex-col gap-5">
          <DialogHeader className="border-b border-border/40 pb-3">
            <DialogTitle className="text-xl font-bold font-heading flex items-center gap-2">
              <Camera className="h-5 w-5 text-primary" /> Start Webcam Session
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground mt-0.5">
              Launch a live webcam analysis session. A new Case will be created automatically.
            </DialogDescription>
          </DialogHeader>

          {errorMsg && (
            <div className="p-3 text-xs text-red-500 bg-red-500/10 border border-red-500/20 rounded-md">
              {errorMsg}
            </div>
          )}

          <form id="add-stream-form" onSubmit={handleSubmit} className="flex flex-col gap-5">
            <div className="space-y-1.5">
              <Label htmlFor="session-title" className="text-xs font-medium">Session Title (Optional)</Label>
              <Input
                id="session-title"
                placeholder="e.g. Identity Verification - John Doe"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="bg-background/50 text-sm"
              />
            </div>
          </form>
        </div>

        {/* Dialog Footer Flush at Bottom */}
        <DialogFooter className="m-0 px-6 py-4 rounded-b-xl border-t bg-muted/50 flex flex-row justify-end gap-2">
          <Button type="button" variant="outline" onClick={resetAndClose} disabled={isSubmitting} className="cursor-pointer">
            Cancel
          </Button>
          <Button type="submit" form="add-stream-form" disabled={isSubmitting} className="gap-2 cursor-pointer">
            {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Camera className="h-4 w-4" />}
            {isSubmitting ? "Starting..." : "Start Session"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
