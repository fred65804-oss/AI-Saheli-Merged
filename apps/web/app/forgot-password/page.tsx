"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { CheckCircle2, KeyRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  // No backend call yet — password reset delivery isn't built. This just
  // confirms the request was captured so the flow is testable end to end
  // once the email/reset-link backend lands.
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
  };

  return (
    <div className="mx-auto max-w-sm mt-8">
      <Card>
        <CardHeader className="space-y-1.5 items-center text-center">
          <div className="h-11 w-11 rounded-full bg-primary text-primary-foreground grid place-items-center mb-1">
            <KeyRound className="h-5 w-5" />
          </div>
          <CardTitle className="normal-case tracking-normal text-xl font-semibold text-foreground">
            Reset your password
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Enter your account email and we'll send you a reset link.
          </p>
        </CardHeader>
        <CardContent>
          {submitted ? (
            <div className="flex flex-col items-center gap-3 py-4 text-center">
              <CheckCircle2 className="h-8 w-8 text-emerald-500" />
              <p className="text-sm text-foreground">
                If an account exists for <b>{email}</b>, we've sent a password reset link to it.
              </p>
              <p className="text-xs text-muted-foreground">
                Didn't get it? Check your spam folder or try again in a few minutes.
              </p>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="space-y-3.5">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground" htmlFor="email">
                  Email
                </label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@mowcd.gov.in"
                />
              </div>
              <Button type="submit" className="w-full">
                Send reset link
              </Button>
            </form>
          )}
          <p className="mt-4 text-center text-xs text-muted-foreground">
            <Link href="/login" className="text-primary hover:underline">
              Back to sign in
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
