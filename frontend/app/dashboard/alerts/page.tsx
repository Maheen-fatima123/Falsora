"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AlertTriangle, Info, AlertCircle, ShieldAlert } from "lucide-react";
import { PageHeader } from "@/components/page-header";

const alerts = [
  { id: 1, type: "critical", title: "High Confidence Deepfake Detected", desc: "Live Stream 'Unknown RTMP Source' (STR-003) spiked to 98% forgery probability.", time: "2 minutes ago" },
  { id: 2, type: "warning", title: "Unusual Frame Rate Variance", desc: "Case CAS-141 exhibits irregular frame pacing, suggesting possible temporal manipulation.", time: "1 hour ago" },
  { id: 3, type: "info", title: "Analysis Completed", desc: "Batch job #4022 finished analyzing 54 images. 2 items flagged.", time: "3 hours ago" },
  { id: 4, type: "critical", title: "System Overload", desc: "GPU Cluster A is running at 99% capacity. Consider scaling up for live processing.", time: "5 hours ago" },
];

export default function AlertsPage() {
  return (
    <div className="flex flex-col gap-6">
      <Card className="bg-background/60 backdrop-blur border-border/50">
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          {alerts.map((alert) => (
            <div key={alert.id} className="flex gap-4 items-start relative group">
              {/* Timeline line */}
              <div className="absolute left-[19px] top-10 bottom-[-24px] w-px bg-border group-last:hidden" />
              
              {/* Icon */}
              <div className={`mt-1 flex-shrink-0 h-10 w-10 rounded-full flex items-center justify-center border-2 border-background shadow-sm z-10 ${
                alert.type === "critical" ? "bg-destructive/20 text-destructive" :
                alert.type === "warning" ? "bg-orange-500/20 text-orange-500" :
                "bg-blue-500/20 text-blue-500"
              }`}>
                {alert.type === "critical" ? <AlertTriangle className="h-4 w-4" /> :
                 alert.type === "warning" ? <AlertCircle className="h-4 w-4" /> :
                 <Info className="h-4 w-4" />}
              </div>
              
              {/* Content */}
              <div className="flex-1 bg-card border border-border/50 rounded-lg p-4 shadow-sm group-hover:border-border transition-colors">
                <div className="flex justify-between items-start gap-4">
                  <div>
                    <h4 className="font-semibold leading-none mb-2">{alert.title}</h4>
                    <p className="text-sm text-muted-foreground">{alert.desc}</p>
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">{alert.time}</span>
                </div>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
