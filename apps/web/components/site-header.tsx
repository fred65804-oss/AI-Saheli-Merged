"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageSquare, BarChart3, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Chat", icon: MessageSquare },
  { href: "/dashboard", label: "Analytics", icon: BarChart3 },
];

export function SiteHeader() {
  const pathname = usePathname();
  return (
    <header className="border-b border-white/40 bg-white/70 backdrop-blur-md sticky top-0 z-30 shadow-[0_1px_0_rgba(15,23,42,0.03)]">
      <div className="container flex h-16 items-center justify-between">
        <Link href="/" className="flex items-center gap-3 group">
          <div className="relative">
            <div className="h-10 w-10 rounded-xl gradient-ministry text-white grid place-items-center font-bold text-lg shadow-md group-hover:shadow-lg transition-shadow">
              स
            </div>
            <div className="absolute -bottom-1 -right-1 h-4 w-4 rounded-full bg-accent border-2 border-white grid place-items-center">
              <ShieldCheck className="h-2.5 w-2.5 text-white" />
            </div>
          </div>
          <div className="leading-tight">
            <div className="font-semibold text-ministry text-[15px]">AI Saheli</div>
            <div className="text-[11px] text-muted-foreground uppercase tracking-wider">
              MoWCD · Government of India
            </div>
          </div>
        </Link>
        <nav className="flex items-center gap-1 rounded-full border bg-white/60 p-1 shadow-sm">
          {NAV.map((item) => {
            const active = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-medium transition-all",
                  active
                    ? "gradient-ministry text-white shadow-md"
                    : "text-muted-foreground hover:text-ministry hover:bg-ministry-soft"
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
