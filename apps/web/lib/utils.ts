import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Default to same-origin ("") so the browser hits the Next.js server, which
// proxies backend routes to FastAPI via rewrites (see next.config.mjs). This
// lets a single public URL (e.g. one ngrok tunnel) serve both UI and API.
// Override with NEXT_PUBLIC_API_BASE for a direct cross-origin backend.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
