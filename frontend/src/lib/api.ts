import axios from "axios";

const baseURL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export const api = axios.create({ baseURL, timeout: 10_000 });

export interface Alert {
  alert_type: string;
  src_ip?: string;
  severity?: string;
  count?: number;
  ts?: number | string;
  [key: string]: unknown;
}

export interface StatsResponse {
  topics: Record<string, Record<string, number>>;
  consumers: Record<string, { paused: boolean; running: boolean }>;
}

export async function fetchAlerts(limit = 50): Promise<Alert[]> {
  const { data } = await api.get<{ alerts: Alert[] }>(`/api/alerts`, { params: { limit } });
  return data.alerts;
}

export async function fetchStats(): Promise<StatsResponse> {
  const { data } = await api.get<StatsResponse>(`/api/stats`);
  return data;
}
