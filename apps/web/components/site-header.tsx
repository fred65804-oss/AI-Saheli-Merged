"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { LogOut, MessageSquare, BarChart3, Wrench, ServerCog, UserRound } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/auth-context";
import { Button } from "@/components/ui/button";

const NAV = [
  { href: "/", label: "Chat", icon: MessageSquare, adminOnly: false },
  { href: "/dashboard", label: "Analytics", icon: BarChart3, adminOnly: true },
  { href: "/tools", label: "Tools", icon: Wrench, adminOnly: true },
  { href: "/system", label: "System", icon: ServerCog, adminOnly: true },
];

export function SiteHeader() {
  const pathname = usePathname();
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const nav = NAV.filter((item) => !item.adminOnly || user?.role === "admin");

  return (
    <header className="relative sticky top-0 z-30 border-b border-border bg-white/95 backdrop-blur">
      <div className="container flex h-16 items-center justify-between lg:h-[72px]">
        <Link href="/" className="flex items-center gap-3">
          <div className="gradient-ministry relative grid h-10 w-10 place-items-center rounded-xl text-base font-semibold text-primary-foreground shadow-[0_8px_20px_-10px_rgba(11,61,145,0.8)] ring-1 ring-primary/10">
            स
            <span
              className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-amber-400 ring-2 ring-white/80"
              aria-hidden="true"
            />
          </div>
          <div className="leading-tight">
            <div className="font-display text-[15px] font-semibold text-foreground">AI Saheli</div>
            <div className="text-[11px] text-muted-foreground uppercase tracking-wider">
              MoWCD · Government of India
            </div>
          </div>
        </Link>
        <div className="flex items-center gap-3">
          <nav aria-label="Primary navigation" className="flex items-center gap-1 rounded-lg bg-secondary/70 p-1">
            {nav.map((item) => {
              const active = pathname === item.href;
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    active
                      ? "bg-white text-primary shadow-sm"
                      : "text-muted-foreground hover:bg-white/70 hover:text-foreground"
                  )}
                  aria-current={active ? "page" : undefined}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="h-6 w-px bg-border" />
          {loading ? null : user ? (
            <div className="flex items-center gap-2">
              <div className="hidden items-center gap-2 lg:flex">
                <div className="grid h-8 w-8 place-items-center rounded-full bg-ministry-soft text-ministry">
                  <UserRound className="h-4 w-4" />
                </div>
                <div className="max-w-[150px] leading-tight">
                  <div className="truncate text-xs font-medium text-foreground">{user.name}</div>
                  <div className="text-[11px] capitalize text-muted-foreground">{user.role}</div>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={async () => {
                  await logout();
                  router.push("/login");
                }}
              >
                <LogOut className="h-3.5 w-3.5" />
                <span className="hidden lg:inline">Log out</span>
              </Button>
            </div>
          ) : (
            <Button variant="outline" size="sm" onClick={() => router.push("/login")}>
              Sign in
            </Button>
          )}
        </div>
      </div>
      <div className="tricolor-rule absolute inset-x-0 bottom-0 h-[2px] opacity-80" aria-hidden="true" />
    </header>
  );
}
