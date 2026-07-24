import { ShieldCheck, UserRound } from "lucide-react";

import type { AuthRole } from "@/lib/auth";
import { cn } from "@/lib/utils";

const ROLES = [
  {
    value: "citizen",
    label: "Citizen",
    description: "Chat and scheme guidance",
    icon: UserRound,
  },
  {
    value: "admin",
    label: "Administrator",
    description: "Dashboard and staff tools",
    icon: ShieldCheck,
  },
] as const;

export function AuthRoleSelector({
  value,
  onChange,
  legend,
}: {
  value: AuthRole;
  onChange: (role: AuthRole) => void;
  legend: string;
}) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-xs font-medium text-muted-foreground">
        {legend}
      </legend>
      <div className="grid grid-cols-2 gap-2">
        {ROLES.map((role) => {
          const Icon = role.icon;
          const selected = value === role.value;
          return (
            <button
              key={role.value}
              type="button"
              aria-pressed={selected}
              onClick={() => onChange(role.value)}
              className={cn(
                "rounded-xl border p-3 text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                selected
                  ? "border-ministry bg-blue-50 text-ministry shadow-sm"
                  : "border-border bg-white text-muted-foreground hover:border-ministry/30 hover:bg-blue-50/40",
              )}
            >
              <span className="flex items-center gap-2 text-xs font-semibold">
                <span
                  className={cn(
                    "grid h-7 w-7 place-items-center rounded-lg",
                    selected ? "bg-ministry text-white" : "bg-secondary text-foreground",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                </span>
                {role.label}
              </span>
              <span className="mt-1.5 block text-[10px] leading-4 text-muted-foreground">
                {role.description}
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
