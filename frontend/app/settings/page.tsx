import { apiBaseUrl } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

const settings = [
  ["Backend API", apiBaseUrl],
  ["Web Search", "BRAVE_SEARCH_API_KEY or TAVILY_API_KEY"],
  ["Literature", "Europe PMC REST + PubMed/NCBI E-utilities"],
  ["Vector DB", "Qdrant dense/sparse/multivector ready"],
  ["Cache", "Redis"],
  ["Storage", "MinIO"]
];

export default function SettingsPage() {
  return (
    <div className="min-h-screen p-5">
      <div className="mx-auto max-w-5xl">
        <div className="mb-5">
          <h1 className="text-2xl font-black text-ink">Admin / Settings</h1>
          <p className="text-sm text-[#60717c]">Runtime endpoints and deployment configuration.</p>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {settings.map(([label, value]) => (
            <div key={label} className="rounded-md border border-[#d9e0dd] bg-white p-5 shadow-panel">
              <Badge>{label}</Badge>
              <div className="mt-3 break-words text-sm font-semibold text-ink">{value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
