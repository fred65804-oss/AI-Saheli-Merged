import type { Metadata } from "next";
import "./globals.css";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = {
  title: "AI Saheli — MoWCD",
  description:
    "Agentic AI assistant for Poshan 2.0, Mission Vatsalya, and Mission Shakti.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <SiteHeader />
        <main className="container py-8">{children}</main>
        <footer className="border-t border-white/40 py-6 mt-12 bg-white/40 backdrop-blur-sm">
          <div className="container flex items-center justify-between text-xs text-muted-foreground">
            <span className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
              Presented by <b className="text-foreground">Uneecops Technologies</b>
            </span>
            <span>Demo build · Synthetic personas only · No real PII</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
