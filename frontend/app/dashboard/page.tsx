import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FolderOpen, AlertTriangle, ShieldCheck, Activity } from "lucide-react";
import { PageHeader } from "@/components/page-header";

export default function DashboardOverview() {
  return (
    <div className="flex flex-col gap-8">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="bg-background/60 backdrop-blur border-border/50">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Cases</CardTitle>
            <FolderOpen className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">142</div>
            <p className="text-xs text-muted-foreground">+12 since last week</p>
          </CardContent>
        </Card>
        <Card className="bg-background/60 backdrop-blur border-border/50">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Verified Genuine</CardTitle>
            <ShieldCheck className="h-4 w-4 text-emerald-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">89</div>
            <p className="text-xs text-muted-foreground">62% of total media</p>
          </CardContent>
        </Card>
        <Card className="bg-background/60 backdrop-blur border-border/50">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Manipulated</CardTitle>
            <AlertTriangle className="h-4 w-4 text-destructive" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">34</div>
            <p className="text-xs text-muted-foreground">Deepfakes & Splices</p>
          </CardContent>
        </Card>
        <Card className="bg-background/60 backdrop-blur border-border/50">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Live Streams</CardTitle>
            <Activity className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">3</div>
            <p className="text-xs text-muted-foreground">Monitoring in real-time</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
        <Card className="col-span-4 bg-background/60 backdrop-blur border-border/50">
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
          </CardHeader>
          <CardContent className="h-[300px] flex items-center justify-center text-muted-foreground border-t border-border/50">
            [Activity Chart Placeholder]
          </CardContent>
        </Card>
        <Card className="col-span-3 bg-background/60 backdrop-blur border-border/50">
          <CardHeader>
            <CardTitle>Recent Flags</CardTitle>
          </CardHeader>
          <CardContent className="h-[300px] flex flex-col gap-4 border-t border-border/50 pt-4">
            <div className="flex items-center gap-4">
              <div className="h-10 w-10 rounded-full bg-destructive/20 flex items-center justify-center text-destructive">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-medium leading-none">High Forgery Score (98%)</p>
                <p className="text-sm text-muted-foreground">Case #142 - video_evidence.mp4</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="h-10 w-10 rounded-full bg-orange-500/20 flex items-center justify-center text-orange-500">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-medium leading-none">Metadata Mismatch</p>
                <p className="text-sm text-muted-foreground">Case #140 - image_03.jpg</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
