"use client";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { 
  AreaChart, 
  Area, 
  BarChart, 
  Bar, 
  PieChart, 
  Pie, 
  Cell, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer, 
  Legend 
} from "recharts";

// Mock Data
const monthlyTrendData = [
  { month: "Jan", authentic: 1200, deepfake: 450, suspicious: 180 },
  { month: "Feb", authentic: 1400, deepfake: 520, suspicious: 210 },
  { month: "Mar", authentic: 1100, deepfake: 680, suspicious: 310 },
  { month: "Apr", authentic: 1600, deepfake: 890, suspicious: 240 },
  { month: "May", authentic: 1850, deepfake: 1120, suspicious: 290 },
  { month: "Jun", authentic: 2100, deepfake: 1450, suspicious: 340 },
];

const forgeryTypeData = [
  { category: "Face Swap", count: 1420 },
  { category: "Voice Synthesis", count: 890 },
  { category: "Frame Splicing", count: 640 },
  { category: "Diffusion Artifacts", count: 510 },
  { category: "Metadata Tampering", count: 320 },
];

const sourceOriginData = [
  { name: "Social Media", value: 42, color: "#8884d8" },
  { name: "CCTV / Security", value: 28, color: "#82ca9d" },
  { name: "Live RTMP Streams", value: 18, color: "#ffc658" },
  { name: "Direct Uploads", value: 12, color: "#ff8042" },
];

const modelAccuracyData = [
  { model: "EfficientNet-V2", accuracy: 99.1 },
  { model: "MesoNet-4", accuracy: 94.6 },
  { model: "Wav2Vec2 Audio", accuracy: 97.8 },
  { model: "ResNet-50 ELA", accuracy: 92.3 },
  { model: "XceptionNet", accuracy: 98.4 },
];

export default function AnalyticsPage() {
  return (
    <div className="flex flex-col gap-6">
      {/* Key Metric Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="bg-background/60 backdrop-blur border-border/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Detection Accuracy</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold font-mono">98.4%</div>
            <p className="text-xs text-emerald-500 mt-1 font-medium">+0.4% from last month</p>
          </CardContent>
        </Card>
        
        <Card className="bg-background/60 backdrop-blur border-border/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Total Scanned Media</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold font-mono">14,290</div>
            <p className="text-xs text-emerald-500 mt-1 font-medium">+2,450 this month</p>
          </CardContent>
        </Card>

        <Card className="bg-background/60 backdrop-blur border-border/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Avg Processing Speed</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold font-mono">1.12s</div>
            <p className="text-xs text-muted-foreground mt-1">GPU cluster latencies</p>
          </CardContent>
        </Card>

        <Card className="bg-background/60 backdrop-blur border-border/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">False Positive Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold font-mono">0.6%</div>
            <p className="text-xs text-emerald-500 mt-1 font-medium">-0.1% optimization</p>
          </CardContent>
        </Card>
      </div>

      {/* Chart Row 1: Detection Trends (Area) + Source Origin (Pie) */}
      <div className="grid gap-6 md:grid-cols-3">
        {/* Detection Trends Area Chart (2 Cols) */}
        <Card className="md:col-span-2 bg-background/60 backdrop-blur border-border/50 flex flex-col">
          <CardHeader>
            <CardTitle>Monthly Forensic Detection Trends</CardTitle>
            <CardDescription>Volume of scanned media categorized by classification outcome.</CardDescription>
          </CardHeader>
          <CardContent className="flex-1 min-h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={monthlyTrendData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorAuthentic" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorDeepfake" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorSuspicious" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                <XAxis dataKey="month" stroke="#888888" fontSize={12} />
                <YAxis stroke="#888888" fontSize={12} />
                <Tooltip 
                  contentStyle={{ backgroundColor: "#0f172a", borderColor: "#1e293b", borderRadius: "8px", fontSize: "12px" }}
                />
                <Legend wrapperStyle={{ paddingTop: "10px" }} />
                <Area type="monotone" dataKey="authentic" name="Authentic Media" stroke="#10b981" fillOpacity={1} fill="url(#colorAuthentic)" />
                <Area type="monotone" dataKey="deepfake" name="Deepfake Flagged" stroke="#ef4444" fillOpacity={1} fill="url(#colorDeepfake)" />
                <Area type="monotone" dataKey="suspicious" name="Suspicious / Needs Review" stroke="#f59e0b" fillOpacity={1} fill="url(#colorSuspicious)" />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Source Origin Pie Chart (1 Col) */}
        <Card className="bg-background/60 backdrop-blur border-border/50 flex flex-col">
          <CardHeader>
            <CardTitle>Media Source Distribution</CardTitle>
            <CardDescription>Breakdown by origin platform.</CardDescription>
          </CardHeader>
          <CardContent className="flex-1 min-h-[300px] flex items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={sourceOriginData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={85}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {sourceOriginData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{ backgroundColor: "#0f172a", borderColor: "#1e293b", borderRadius: "8px", fontSize: "12px" }}
                />
                <Legend wrapperStyle={{ fontSize: "12px" }} />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Chart Row 2: Forgery Types (Bar Chart) + Model Ensemble Accuracy (Horizontal Bar) */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Forgery Techniques Bar Chart */}
        <Card className="bg-background/60 backdrop-blur border-border/50 flex flex-col">
          <CardHeader>
            <CardTitle>Detected Forgery Techniques</CardTitle>
            <CardDescription>Total count by manipulation category.</CardDescription>
          </CardHeader>
          <CardContent className="flex-1 min-h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={forgeryTypeData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                <XAxis dataKey="category" stroke="#888888" fontSize={11} />
                <YAxis stroke="#888888" fontSize={12} />
                <Tooltip 
                  contentStyle={{ backgroundColor: "#0f172a", borderColor: "#1e293b", borderRadius: "8px", fontSize: "12px" }}
                />
                <Bar dataKey="count" name="Incidents Detected" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Model Ensemble Accuracy Bar Chart */}
        <Card className="bg-background/60 backdrop-blur border-border/50 flex flex-col">
          <CardHeader>
            <CardTitle>AI Model Ensemble Accuracy</CardTitle>
            <CardDescription>Evaluation scores across specialized models.</CardDescription>
          </CardHeader>
          <CardContent className="flex-1 min-h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={modelAccuracyData} layout="vertical" margin={{ top: 5, right: 30, left: 40, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                <XAxis type="number" domain={[80, 100]} stroke="#888888" fontSize={12} />
                <YAxis dataKey="model" type="category" stroke="#888888" fontSize={11} width={100} />
                <Tooltip 
                  contentStyle={{ backgroundColor: "#0f172a", borderColor: "#1e293b", borderRadius: "8px", fontSize: "12px" }}
                />
                <Bar dataKey="accuracy" name="Accuracy %" fill="#14b8a6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
