import type { Metadata } from "next";
import "./globals.css";
import { SiteHeader } from "@/components/site-header";
import { AuthProvider } from "@/contexts/auth-context";

export const metadata: Metadata = {
  title: "AI Saheli — MoWCD",
  description:
    "Agentic AI assistant for Poshan 2.0, Mission Vatsalya, and Mission Shakti.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-white">
        <AuthProvider>
          <SiteHeader />
          <main className="container py-8">{children}</main>
          <footer className="border-t border-border py-6 mt-12">
            <div className="container flex items-center justify-between text-xs text-muted-foreground">
              <span>
                Presented by <b className="text-foreground">Uneecops Technologies</b>
              </span>
              <span>Demo build · Synthetic personas only · No real PII</span>
            </div>
          </footer>
        </AuthProvider>
      </body>
    </html>
  );
}
