"use client";

import Link from "next/link";
import { KeyRound, MailQuestion } from "lucide-react";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { AuthShell } from "@/components/auth-shell";

export default function ForgotPasswordPage() {
  return (
    <AuthShell>
      <Card className="h-full border-0 shadow-none">
        <CardHeader className="items-center space-y-1.5 text-center">
          <div className="mb-1 grid h-11 w-11 place-items-center rounded-full bg-primary text-primary-foreground">
            <KeyRound className="h-5 w-5" />
          </div>
          <h1 className="font-display text-xl font-semibold text-foreground">
            Password assistance
          </h1>
          <p className="text-sm text-muted-foreground">
            Password reset email is not connected in this demo environment.
          </p>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-ministry/15 bg-ministry-soft/70 p-4">
            <div className="flex gap-3">
              <MailQuestion className="mt-0.5 h-5 w-5 shrink-0 text-ministry" />
              <div>
                <h2 className="text-sm font-semibold text-foreground">Contact your administrator</h2>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  Ask the administrator who created your staff account to reset your password or issue a new account.
                </p>
              </div>
            </div>
          </div>
          <Link
            href="/login"
            className="mt-4 inline-flex h-10 w-full items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            Back to sign in
          </Link>
        </CardContent>
      </Card>
    </AuthShell>
  );
}
