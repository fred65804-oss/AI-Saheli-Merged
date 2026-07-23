"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/contexts/auth-context";

/** Wrap a page's content to redirect to /login when there's no active session.
 * Pass requireAdmin to also redirect non-admins away (e.g. to "/") — this is
 * a UX nicety only, the backend 403s non-admins on these routes regardless. */
export function RequireAuth({
  children,
  requireAdmin = false,
}: {
  children: React.ReactNode;
  requireAdmin?: boolean;
}) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    } else if (requireAdmin && user.role !== "admin") {
      router.replace("/");
    }
  }, [loading, user, pathname, router, requireAdmin]);

  if (loading || !user || (requireAdmin && user.role !== "admin")) {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="rounded-lg border border-border bg-secondary/40 animate-pulse h-32" />
        ))}
      </div>
    );
  }

  return <>{children}</>;
}
