import Image from "next/image";
import { Languages, ShieldCheck, Sparkles } from "lucide-react";

export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto mt-8 grid w-full max-w-4xl overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-[0_24px_70px_-42px_rgba(11,61,145,0.55)] md:grid-cols-[1.05fr_0.95fr]">
      <aside className="gradient-ministry relative hidden overflow-hidden p-10 text-white md:flex md:flex-col md:justify-between">
        <div className="dot-pattern absolute inset-0 opacity-25" aria-hidden="true" />
        <div
          className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-white/10 blur-2xl"
          aria-hidden="true"
        />
        <div className="relative">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-medium">
            <ShieldCheck className="h-3.5 w-3.5" />
            Authorised staff workspace
          </div>
          <h2 className="mt-6 max-w-sm text-3xl font-semibold leading-tight">
            Citizen support, grounded in official guidance.
          </h2>
          <p className="mt-3 max-w-sm text-sm leading-6 text-blue-100">
            Access live service analytics, scheme tools, and system health from
            one secure Ministry workspace.
          </p>
        </div>

        <div className="relative mt-10 flex items-end gap-5">
          <div className="grid h-24 w-24 shrink-0 place-items-center overflow-hidden rounded-3xl border border-white/25 bg-white/10 shadow-xl">
            <div className="relative h-24 w-24 overflow-hidden rounded-full">
              <Image
                src="/ai-saheli-avatar.png"
                alt="AI Saheli"
                fill
                sizes="96px"
                className="avatar-face object-cover"
              />
            </div>
          </div>
          <div className="space-y-2 pb-1 text-xs text-blue-100">
            <div className="flex items-center gap-2">
              <Languages className="h-4 w-4 text-amber-300" />
              11 Indian languages
            </div>
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-amber-300" />
              Poshan · Vatsalya · Shakti
            </div>
          </div>
        </div>
      </aside>

      <div className="bg-white p-1">{children}</div>
    </div>
  );
}
