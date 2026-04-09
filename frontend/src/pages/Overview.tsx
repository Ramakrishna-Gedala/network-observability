import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { fetchAlerts, fetchStats, Alert } from "../lib/api";
import { usePipelineStore } from "../stores/pipelineStore";

function Card({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-slate-900 border border-slate-800 p-4 rounded">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
    </div>
  );
}

export default function Overview() {
  const setHealth = usePipelineStore((s) => s.setHealth);
  const setBadge = usePipelineStore((s) => s.setAlertBadgeCount);

  const alertsQ = useQuery<Alert[]>({
    queryKey: ["alerts", "recent"],
    queryFn: () => fetchAlerts(20),
    refetchInterval: 5000,
  });

  const statsQ = useQuery({
    queryKey: ["stats"],
    queryFn: fetchStats,
    refetchInterval: 5000,
  });

  useEffect(() => {
    if (alertsQ.data) setBadge(alertsQ.data.length);
  }, [alertsQ.data, setBadge]);

  useEffect(() => {
    if (statsQ.isError) setHealth("red");
    else if (statsQ.data) setHealth("green");
  }, [statsQ.data, statsQ.isError, setHealth]);

  const totalEvents = statsQ.data
    ? Object.values(statsQ.data.topics).reduce(
        (acc: number, s) => acc + Object.values(s).reduce((a: number, v) => a + (v as number), 0),
        0
      )
    : 0;

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">Overview</h2>
      <div className="grid grid-cols-4 gap-4">
        <Card label="Total Events (since start)" value={totalEvents.toLocaleString()} />
        <Card label="Active Alerts" value={alertsQ.data?.length ?? 0} />
        <Card label="Consumers Running" value={
          statsQ.data ? Object.values(statsQ.data.consumers).filter((c) => c.running).length : 0
        } />
        <Card label="Pipeline Status" value={statsQ.isError ? "error" : "healthy"} />
      </div>

      <section>
        <h3 className="font-semibold mb-2">Recent events (alerts)</h3>
        <div className="bg-slate-900 border border-slate-800 rounded divide-y divide-slate-800">
          {(alertsQ.data ?? []).slice(0, 20).map((a, i) => (
            <div key={i} className="p-3 text-sm flex gap-3">
              <span className="text-slate-400">{String(a.ts ?? "")}</span>
              <span className="font-mono">{a.alert_type}</span>
              <span className="text-slate-300">{a.src_ip ?? ""}</span>
              <span className="ml-auto text-yellow-400">{a.severity}</span>
            </div>
          ))}
          {alertsQ.isLoading && <div className="p-3 text-slate-500">Loading…</div>}
        </div>
      </section>
    </div>
  );
}
