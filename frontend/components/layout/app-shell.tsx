"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, BookOpen, Clock3, Database, Globe2, Home, MessageSquareText, Settings, Stethoscope } from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/", label: "Home", icon: Home },
  { href: "/chat", label: "Agent Workspace", icon: MessageSquareText },
  { href: "/web-search", label: "Web Search Agent", icon: Globe2 },
  { href: "/medical-rag", label: "Medical RAG Agent", icon: Stethoscope },
  { href: "/history", label: "History", icon: Clock3 },
  { href: "/literature", label: "Literature", icon: BookOpen },
  { href: "/evidence", label: "Evidence", icon: Database },
  { href: "/evaluation", label: "Evaluation", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings }
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const activeNav = nav.find((item) => pathname === item.href);
  return (
    <div className="min-h-screen bg-[#eef2ef]">
      <aside className="fixed left-0 top-0 z-30 hidden h-screen w-20 flex-col border-r border-[#d5ddd8] bg-[#fbfcfb] px-3 py-4 lg:flex">
        <Link href="/" className="focus-ring grid h-12 place-items-center rounded-md text-ink" title="WMD-agent">
          <span className="grid h-10 w-10 place-items-center rounded-md bg-[#176b5c] text-sm font-black text-white shadow-sm">
            W
          </span>
        </Link>
        <nav className="mt-5 flex flex-1 flex-col items-center gap-2">
          {nav.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                title={item.label}
                className={cn(
                  "focus-ring flex h-12 w-12 items-center justify-center rounded-md border border-transparent text-[#687782] transition hover:border-[#d5ddd8] hover:bg-white hover:text-ink",
                  active && "border-[#b9d8ca] bg-[#e2f1eb] text-[#176b5c] shadow-sm"
                )}
              >
                <Icon size={18} />
                <span className="sr-only">{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>
      <header className="sticky top-0 z-20 border-b border-[#d5ddd8] bg-[#fbfcfb]/95 backdrop-blur lg:hidden">
        <div className="flex items-center justify-between px-4 py-3">
          <Link href="/" className="font-black text-ink">
            WMD-agent
          </Link>
          <span className="text-sm font-bold text-[#176b5c]">{activeNav?.label || "Agent"}</span>
        </div>
        <nav className="flex gap-2 overflow-x-auto border-t border-[#e4ebe7] px-3 py-2">
          {nav.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "focus-ring flex h-9 shrink-0 items-center gap-2 rounded-md border border-transparent px-3 text-xs font-black text-[#687782]",
                  active && "border-[#b9d8ca] bg-[#e2f1eb] text-[#176b5c]"
                )}
              >
                <Icon size={15} />
                {item.label.replace(" Agent", "").replace(" Workspace", "")}
              </Link>
            );
          })}
        </nav>
      </header>
      <main className="lg:pl-20">{children}</main>
    </div>
  );
}
