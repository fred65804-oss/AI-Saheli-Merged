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
      <body className="min-h-screen bg-background">
        <AuthProvider>
          <div className="flex min-h-screen flex-col">
            <a
              href="#main-content"
              className="sr-only z-50 rounded-md bg-primary px-4 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
            >
              Skip to main content
            </a>
            <SiteHeader />
            <main id="main-content" className="container flex-1 py-8 lg:py-10">
              {children}
            </main>
            <footer className="mt-12 border-t border-border bg-white py-6">
              <div className="container flex items-center justify-between gap-4 text-xs text-muted-foreground">
                <span>
                  Presented by <b className="text-foreground">Uneecops Technologies</b>
                </span>
                <span>Demo environment · Synthetic personas only · No real PII</span>
              </div>
            </footer>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
