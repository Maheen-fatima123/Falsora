"use client";

import React, { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Play, Pause, Activity, AlertTriangle, ShieldCheck, Plus, Trash2, Radio } from "lucide-react";
import { AddStreamModal } from "@/components/add-stream-modal";
import { fetchApi } from "@/lib/api";

const initialStreams: any[] = [];

export default function StreamsPage() {
  const [streams, setStreams] = useState(initialStreams);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    fetchApi("http://localhost:4000/api/streams")
      .then((res) => res.json())
      .then((data) => {
        if (data.success && Array.isArray(data.data) && data.data.length > 0) {
          setStreams(data.data);
        }
      })
      .catch((err) => console.log("Backend offline, using mock stream sources:", err));
  }, []);

  const handleStreamCreated = (newStream: any) => {
    setStreams((prev) => [newStream, ...prev]);
  };

  const handleEndSession = (id: string) => {
    fetchApi(`http://localhost:4000/api/streams/${id}/end`, { method: "POST" })
      .then((res) => res.json())
      .then((data) => {
        if (data.success) {
          setStreams((prev) =>
            prev.map((s) => (s.id === id ? { ...s, status: "ENDED" } : s))
          );
        }
      })
      .catch(() => {});
  };

  const handleRemoveStream = (id: string) => {
    setStreams((prev) => prev.filter((s) => s.id !== id));
    fetchApi(`http://localhost:4000/api/streams/${id}`, { method: "DELETE" }).catch(() => {});
  };

  return (
    <div className="flex flex-col gap-6">
      <AddStreamModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onStreamCreated={handleStreamCreated}
      />

      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {streams.map((stream) => (
          <Card key={stream.id} className="overflow-hidden bg-background/60 backdrop-blur border-border/50 group pt-0 flex flex-col justify-between">
            <div>
              <div className="relative aspect-video bg-muted flex items-center justify-center border-b border-border/50 overflow-hidden">
                <div className="absolute inset-0 bg-black/40 group-hover:bg-black/20 transition-colors z-10" />
                
                {stream.status === "ACTIVE" && (
                  <button
                    onClick={() => handleEndSession(stream.id)}
                    className="z-20 h-12 w-12 rounded-full bg-red-500/80 hover:bg-red-600 backdrop-blur flex items-center justify-center shadow-lg transition-colors cursor-pointer opacity-0 group-hover:opacity-100"
                    title="End Session"
                  >
                    <Pause className="h-6 w-6 text-white transition-colors fill-current" />
                  </button>
                )}
                
                {/* Badges Overlay */}
                <div className="absolute top-3 left-3 z-20 flex gap-2">
                  <Badge variant="secondary" className={`backdrop-blur-md border-none text-white ${stream.status === 'ENDED' ? "bg-amber-500/80" : "bg-red-500/80"}`}>
                    <Activity className={`h-3 w-3 mr-1 ${stream.status === 'ACTIVE' ? "animate-pulse" : ""}`} />
                    {stream.status === 'ACTIVE' ? "Live" : "Ended"}
                  </Badge>
                  <Badge variant="secondary" className="bg-black/60 text-white backdrop-blur-md border-none font-mono text-[10px]">
                    Webcam
                  </Badge>
                </div>
              </div>
              <CardContent className="p-4">
                <div className="flex justify-between items-start gap-4">
                  <div className="overflow-hidden">
                    <h3 className="font-semibold text-sm leading-tight truncate">
                      {stream.caseRef?.title || "Webcam Session"}
                    </h3>
                    <p className="text-[11px] text-muted-foreground font-mono mt-0.5 truncate">
                      Started: {new Date(stream.startedAt).toLocaleString()}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleRemoveStream(stream.id)}
                    className="h-8 w-8 shrink-0 text-muted-foreground hover:text-red-400 hover:bg-red-500/10 cursor-pointer"
                    title="Delete Session Record"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </div>
          </Card>
        ))}
        
        {/* Add New Stream Card Trigger */}
        <Card 
          onClick={() => setIsModalOpen(true)}
          className="overflow-hidden bg-background/30 border-dashed border-border/50 hover:border-primary/50 hover:bg-accent/30 transition-all cursor-pointer flex flex-col items-center justify-center min-h-[240px] p-6 text-center group"
        >
          <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center mb-3 group-hover:scale-110 group-hover:bg-primary/10 group-hover:text-primary transition-all">
            <Plus className="h-6 w-6 text-muted-foreground group-hover:text-primary transition-colors" />
          </div>
          <h3 className="font-semibold text-muted-foreground group-hover:text-foreground transition-colors">Start Webcam Session</h3>
          <p className="text-xs text-muted-foreground mt-1">Open browser webcam for real-time analysis</p>
        </Card>
      </div>
    </div>
  );
}
