import { NavLink, Outlet } from "react-router-dom";
import { Activity, AlertTriangle, Search, Settings } from "lucide-react";
import { usePipelineStore } from "../stores/pipelineStore";

const links = [
  { to: "/", label: "Overview", icon: Activity },
  { to: "/alerts", label: "Alerts", icon: AlertTriangle },
  { to: "/explorer", label: "Explorer", icon: Search },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Layout() {
  const health = usePipelineStore((s) => s.health);
  const badge = usePipelineStore((s) => s.alertBadgeCount);

  return (
    <div className="flex h-full">
      <aside className="w-56 bg-slate-900 border-r border-slate-800 p-4">
        <h1 className="text-lg font-bold mb-6">NetWatch</h1>
        <nav className="space-y-2">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-2 px-3 py-2 rounded ${
                  isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:text-white"
                }`
              }
            >
              <Icon size={16} />
              <span>{label}</span>
              {to === "/alerts" && badge > 0 && (
                <span className="ml-auto bg-red-500 text-xs px-2 py-0.5 rounded-full">{badge}</span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="mt-10 text-xs text-slate-400">
          <div>Pipeline</div>
          <div className={`mt-1 inline-block px-2 py-1 rounded text-black ${
            health === "green" ? "bg-emerald-400" : health === "yellow" ? "bg-yellow-400" : "bg-red-500"
          }`}>{health.toUpperCase()}</div>
        </div>
      </aside>
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  );
}
