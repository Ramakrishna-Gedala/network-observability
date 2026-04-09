import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, fetchStats } from "../lib/api";

export default function SettingsPage() {
  const [threshold, setThreshold] = useState<number>(1000);
  const [saving, setSaving] = useState<boolean>(false);

  const statsQ = useQuery({
    queryKey: ["stats", "settings"],
    queryFn: fetchStats,
    refetchInterval: 5000,
  });

  const saveThreshold = async () => {
    setSaving(true);
    try {
      await api.patch(`/api/config`, { alert_threshold_requests_per_minute: threshold });
    } catch (e) {
      // swallow — the stats endpoint is authoritative for true state
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  const toggleConsumer = async (topic: string, paused: boolean) => {
    const action = paused ? "resume" : "pause";
    try {
      await api.post(`/api/consumers/${topic}/${action}`);
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="space-y-6 max-w-xl">
      <h2 className="text-xl font-bold">Pipeline Settings</h2>

      <section className="bg-slate-900 border border-slate-800 p-4 rounded space-y-3">
        <label className="block text-sm text-slate-400">Alert threshold (req/min)</label>
        <input
          type="number"
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
          className="bg-slate-950 border border-slate-700 px-3 py-1 rounded w-40"
        />
        <button
          onClick={saveThreshold}
          disabled={saving}
          className="bg-blue-600 px-4 py-1 rounded hover:bg-blue-500 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </section>

      <section className="bg-slate-900 border border-slate-800 p-4 rounded">
        <h3 className="font-semibold mb-2">Consumers</h3>
        <table className="w-full text-sm">
          <thead className="text-left text-slate-400">
            <tr>
              <th>Topic</th>
              <th>Running</th>
              <th>Paused</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {statsQ.data &&
              Object.entries(statsQ.data.consumers).map(([topic, c]) => (
                <tr key={topic} className="border-t border-slate-800">
                  <td className="py-2 font-mono">{topic}</td>
                  <td>{c.running ? "✓" : "✗"}</td>
                  <td>{c.paused ? "✓" : "✗"}</td>
                  <td>
                    <button
                      className="text-blue-400 hover:underline"
                      onClick={() => toggleConsumer(topic, c.paused)}
                    >
                      {c.paused ? "Resume" : "Pause"}
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
