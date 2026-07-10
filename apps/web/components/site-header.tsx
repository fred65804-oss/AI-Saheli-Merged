"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { LogOut, MessageSquare, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/auth-context";
import { Button } from "@/components/ui/button";

const NAV = [
  { href: "/", label: "Chat", icon: MessageSquare },
  { href: "/dashboard", label: "Analytics", icon: BarChart3 },
];

export function SiteHeader() {
  const pathname = usePathname();
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  return (
    <header className="border-b border-border bg-white sticky top-0 z-30">
      <div className="container flex h-16 items-center justify-between">
        <Link href="/" className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-md bg-primary text-primary-foreground grid place-items-center font-semibold text-base">
            स
          </div>
          <div className="leading-tight">
            <div className="font-semibold text-foreground text-[15px]">AI Saheli</div>
            <div className="text-[11px] text-muted-foreground uppercase tracking-wider">
              MoWCD · Government of India
            </div>
          </div>
        </Link>
        <div className="flex items-center gap-3">
          <nav className="flex items-center gap-1">
            {NAV.map((item) => {
              const active = pathname === item.href;
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    active
                      ? "bg-secondary text-foreground"
                      : "text-muted-foreground hover:text-foreground hover:bg-secondary/60"
                  )}
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
              <span className="text-xs text-muted-foreground max-w-[140px] truncate hidden sm:inline">
                {user.name}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={async () => {
                  await logout();
                  router.push("/login");
                }}
              >
                <LogOut className="h-3.5 w-3.5" />
                Log out
              </Button>
            </div>
          ) : (
            <Button variant="outline" size="sm" onClick={() => router.push("/login")}>
              Sign in
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}
