"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Fingerprint, AlertCircle, Loader2, Eye, EyeOff } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const [forgotOpen, setForgotOpen] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotBusy, setForgotBusy] = useState(false);
  const [forgotError, setForgotError] = useState("");
  const [forgotResult, setForgotResult] = useState<{
    message: string;
    temporaryPassword?: string;
  } | null>(null);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      const res = await fetch("http://localhost:4000/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to login");

      if (data.user) {
        localStorage.setItem("falsora_user", JSON.stringify(data.user));
      }
      document.cookie = "auth_session=true; path=/; max-age=86400";

      const role = data.user?.role as string | undefined;
      const home =
        role === "Reviewer"
          ? "/dashboard/reviewer"
          : role === "User"
            ? "/dashboard/user"
            : "/dashboard/admin";
      router.push(home);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleForgotPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setForgotError("");
    setForgotResult(null);
    setForgotBusy(true);
    try {
      const res = await fetch("http://localhost:4000/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: forgotEmail }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || "Reset failed");
      setForgotResult({
        message: data.message,
        temporaryPassword: data.temporaryPassword,
      });
      if (data.temporaryPassword) {
        setEmail(forgotEmail);
        setPassword(data.temporaryPassword);
      }
    } catch (err: any) {
      setForgotError(err.message || "Reset failed");
    } finally {
      setForgotBusy(false);
    }
  };

  return (
    <div className="flex flex-col items-center gap-6 w-full max-w-md mx-auto mt-20">
      <div className="flex items-center gap-2 text-primary">
        <Fingerprint className="h-8 w-8" />
        <span className="text-2xl font-bold tracking-wider">FALSORA</span>
      </div>

      <Card className="w-full bg-background/60 backdrop-blur-xl border-border/50 shadow-2xl">
        <CardHeader className="space-y-1 text-center">
          <CardTitle className="text-2xl">Welcome back</CardTitle>
          <CardDescription>
            Enter your credentials to access the forensics portal
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleLogin} className="space-y-4">
            {error && (
              <div className="p-3 text-sm text-destructive-foreground bg-destructive/10 border border-destructive rounded-md flex items-center gap-2">
                <AlertCircle className="h-4 w-4" />
                {error}
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="admin@falsora.ai"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="bg-background/50"
                disabled={isLoading}
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Password</Label>
                <button
                  type="button"
                  className="text-sm font-medium text-muted-foreground hover:text-primary transition-colors"
                  onClick={() => {
                    setForgotEmail(email);
                    setForgotError("");
                    setForgotResult(null);
                    setForgotOpen(true);
                  }}
                >
                  Forgot password?
                </button>
              </div>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="bg-background/50 pr-10"
                  disabled={isLoading}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  disabled={isLoading}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <Button type="submit" className="w-full font-semibold mt-2" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Authenticating...
                </>
              ) : (
                "Authenticate"
              )}
            </Button>
          </form>
        </CardContent>
        <CardFooter className="flex flex-col gap-2 text-sm text-muted-foreground">
          <p className="text-center">
            New here?{" "}
            <Link href="/register" className="text-primary font-medium hover:underline">
              Create a public account
            </Link>
          </p>
          <p className="text-center text-xs">
            Public Verification Mode — check suspicious images yourself. Reviewers
            and admins are invited by an organization admin.
          </p>
        </CardFooter>
      </Card>

      <Dialog open={forgotOpen} onOpenChange={setForgotOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Reset password</DialogTitle>
            <DialogDescription>
              Enter your account email. If it exists, a temporary password is
              issued (demo mode — no email SMTP).
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleForgotPassword} className="space-y-4">
            {forgotError && (
              <div className="p-3 text-sm text-destructive bg-destructive/10 border border-destructive/40 rounded-md">
                {forgotError}
              </div>
            )}
            {forgotResult && (
              <div className="p-3 text-sm rounded-md border border-border bg-muted/40 space-y-2">
                <p>{forgotResult.message}</p>
                {forgotResult.temporaryPassword && (
                  <p className="font-mono text-xs break-all">
                    Temp password:{" "}
                    <span className="font-semibold text-foreground">
                      {forgotResult.temporaryPassword}
                    </span>
                  </p>
                )}
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="forgot-email">Email</Label>
              <Input
                id="forgot-email"
                type="email"
                required
                value={forgotEmail}
                onChange={(e) => setForgotEmail(e.target.value)}
                disabled={forgotBusy}
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setForgotOpen(false)}
                disabled={forgotBusy}
              >
                Close
              </Button>
              <Button type="submit" disabled={forgotBusy}>
                {forgotBusy ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Working…
                  </>
                ) : (
                  "Issue temporary password"
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
