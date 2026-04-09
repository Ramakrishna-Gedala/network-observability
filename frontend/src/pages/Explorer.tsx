import { useState } from "react";
import { api } from "../lib/api";

type IndexType = "conn" | "dns" | "http";

interface SearchHit { [key: string]: unknown }

export default function Explorer() {
  const [index, setIndex] = useState<IndexType>("conn");
  const [query, setQuery] = useState<string>("*");
  const [results, setResults] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get<{ hits: SearchHit[] }>(`/api/search`, {
        params: { q: query, index },
      });
      setResults(data.hits ?? []);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Log Explorer</h2>
      <div className="flex gap-3">
        <select
          value={index}
          onChange={(e) => setIndex(e.target.value as IndexType)}
          className="bg-slate-900 border border-slate-700 px-2 py-1 rounded"
        >
          <option value="conn">conn</option>
          <option value="dns">dns</option>
          <option value="http">http</option>
        </select>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Lucene query"
          className="flex-1 bg-slate-900 border border-slate-700 px-3 py-1 rounded"
        />
        <button onClick={run} className="bg-blue-600 px-4 rounded hover:bg-blue-500">
          Search
        </button>
      </div>
      {error && <div className="text-red-400">{error}</div>}
      {loading && <div className="text-slate-500">Loading…</div>}
      <pre className="bg-slate-900 p-3 rounded text-xs overflow-auto">
        {JSON.stringify(results, null, 2)}
      </pre>
    </div>
  );
}
