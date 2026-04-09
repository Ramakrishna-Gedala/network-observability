import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, fetchAlerts } from "../lib/api";

export default function AlertsPage() {
  const [severity, setSeverity] = useState<string>("all");
  const [type, setType] = useState<string>("all");
  const [expanded, setExpanded] = useState<number | null>(null);

  const { data, isLoading } = useQuery<Alert[]>({
    queryKey: ["alerts", "list"],
    queryFn: () => fetchAlerts(200),
    refetchInterval: 10_000,
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    return data.filter((a) => {
      if (severity !== "all" && a.severity !== severity) return false;
      if (type !== "all" && a.alert_type !== type) return false;
      return true;
    });
  }, [data, severity, type]);

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Alerts</h2>
      <div className="flex gap-3">
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="bg-slate-900 border border-slate-700 px-2 py-1 rounded"
        >
          <option value="all">All severities</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </select>
        <select
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="bg-slate-900 border border-slate-700 px-2 py-1 rounded"
        >
          <option value="all">All types</option>
          <option value="high_volume">High volume</option>
          <option value="port_scan">Port scan</option>
          <option value="dns_tunneling_suspect">DNS tunneling</option>
        </select>
      </div>

      <table className="w-full text-sm">
        <thead className="text-left text-slate-400">
          <tr>
            <th className="py-2">Time</th>
            <th>Type</th>
            <th>Source</th>
            <th>Severity</th>
            <th>Count</th>
          </tr>
        </thead>
        <tbody>
          {isLoading && (
            <tr>
              <td colSpan={5} className="py-3 text-slate-500">Loading…</td>
            </tr>
          )}
          {filtered.map((a, i) => (
            <>
              <tr
                key={`r-${i}`}
                className="border-t border-slate-800 cursor-pointer hover:bg-slate-900"
                onClick={() => setExpanded(expanded === i ? null : i)}
              >
                <td className="py-2">{String(a.ts ?? "")}</td>
                <td className="font-mono">{a.alert_type}</td>
                <td>{a.src_ip ?? ""}</td>
                <td>{a.severity ?? ""}</td>
                <td>{a.count ?? ""}</td>
              </tr>
              {expanded === i && (
                <tr key={`e-${i}`}>
                  <td colSpan={5} className="bg-slate-950 px-3 py-2">
                    <pre className="text-xs text-slate-400">{JSON.stringify(a, null, 2)}</pre>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </div>
  );
}
