import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, PieChart, Pie, Cell, ResponsiveContainer } from "recharts";

export default function Analytics() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    fetch("http://localhost:8000/api/analytics/dashboard")
      .then(r => r.json())
      .then(data => setStats(data));
  }, []);

  if (!stats) return <p>Loading...</p>;

  const riskData = [
    { name: "Authentic", value: stats.by_risk_level.Authentic, color: "#1abc9c" },
    { name: "Uncertain", value: stats.by_risk_level.Uncertain, color: "#f39c12" },
    { name: "High-Risk", value: stats.by_risk_level["High-Risk"], color: "#e74c3c" },
  ];

  return (
    <div style={{ padding: 24 }}>
      <h2>Analytics Dashboard</h2>

      <div style={{ display: "flex", gap: 16, marginBottom: 24 }}>
        {[
          { label: "Total Cases", value: stats.total_cases },
          { label: "High-Risk", value: stats.by_risk_level["High-Risk"] },
          { label: "Authentic", value: stats.by_risk_level.Authentic },
        ].map(card => (
          <div key={card.label} style={{ flex: 1, padding: 20, background: "#f8f9fa",
                                         borderRadius: 12, border: "1px solid #e0e0e0" }}>
            <p style={{ margin: 0, color: "#666", fontSize: 13 }}>{card.label}</p>
            <p style={{ margin: "4px 0 0", fontSize: 28, fontWeight: 500 }}>{card.value}</p>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", gap: 24 }}>
        <div style={{ flex: 2 }}>
          <h3>Cases per day (last 7 days)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={stats.daily_trend}>
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis />
              <Tooltip />
              <Bar dataKey="count" fill="#2a78d6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div style={{ flex: 1 }}>
          <h3>Risk level breakdown</h3>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={riskData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label>
                {riskData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}