"use client";

import * as React from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Settings, Key, Trash2, Copy, Check, AlertTriangle, UserPlus } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Slider } from "@/components/ui/slider";
import { toast } from "sonner";
import { fetchApi } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { KeyRound } from "lucide-react";

export default function SettingsPage() {
  const [threshold, setThreshold] = React.useState([85]);
  const [newAccountName, setNewAccountName] = React.useState("");
  const [newAccountEmail, setNewAccountEmail] = React.useState("");
  const [newAccountPassword, setNewAccountPassword] = React.useState("");
  const [newAccountRole, setNewAccountRole] = React.useState<"Reviewer" | "User">("Reviewer");
  const [provisionMsg, setProvisionMsg] = React.useState({ type: "", text: "" });
  const [isProvisioning, setIsProvisioning] = React.useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = React.useState(false);

  const [users, setUsers] = React.useState<any[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = React.useState(false);

  const [resetModalData, setResetModalData] = React.useState<{ open: boolean; user: any; password: string }>({
    open: false,
    user: null,
    password: "",
  });
  const [resetConfirmUser, setResetConfirmUser] = React.useState<any | null>(null);
  const [deleteConfirmUser, setDeleteConfirmUser] = React.useState<any | null>(null);
  const [copied, setCopied] = React.useState(false);
  const [actionLoadingId, setActionLoadingId] = React.useState<string | null>(null);

  const fetchAccounts = React.useCallback(async () => {
    setIsLoadingUsers(true);
    try {
      const res = await fetchApi("http://localhost:4000/api/auth/users", { credentials: "include" });
      const data = await res.json();
      if (data.success && Array.isArray(data.users)) {
        setUsers(data.users);
      }
    } catch (err) {
      console.error("Failed to fetch provisioned users", err);
    } finally {
      setIsLoadingUsers(false);
    }
  }, []);

  React.useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  const handleResetPassword = async () => {
    if (!resetConfirmUser) return;
    const user = resetConfirmUser;
    setActionLoadingId(`reset-${user.id}`);
    try {
      const res = await fetchApi(`http://localhost:4000/api/auth/users/${user.id}/reset-password`, {
        method: "POST",
        credentials: "include",
      });
      const data = await res.json();
      if (data.success && data.newPassword) {
        setResetModalData({ open: true, user, password: data.newPassword });
        setResetConfirmUser(null);
        setCopied(false);
        toast.success(`Password reset for ${user.name}`);
      } else {
        toast.error(data.error || "Failed to reset password");
      }
    } catch (err: any) {
      toast.error(err.message || "Failed to reset password");
    } finally {
      setActionLoadingId(null);
    }
  };

  const confirmDeleteAccount = async () => {
    if (!deleteConfirmUser) return;
    const user = deleteConfirmUser;
    setActionLoadingId(`delete-${user.id}`);
    try {
      const res = await fetchApi(`http://localhost:4000/api/auth/users/${user.id}`, {
        method: "DELETE",
        credentials: "include",
      });
      const data = await res.json();
      if (data.success) {
        toast.success(`Account ${user.email} deleted successfully`);
        setDeleteConfirmUser(null);
        fetchAccounts();
      } else {
        toast.error(data.error || "Failed to delete account");
      }
    } catch (err: any) {
      toast.error(err.message || "Failed to delete account");
    } finally {
      setActionLoadingId(null);
    }
  };

  const copyPassword = () => {
    navigator.clipboard.writeText(resetModalData.password);
    setCopied(true);
    toast.success("Password copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleProvisionAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    setProvisionMsg({ type: "", text: "" });
    setIsProvisioning(true);

    try {
      const res = await fetchApi("http://localhost:4000/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          name: newAccountName,
          email: newAccountEmail,
          password: newAccountPassword,
          roleName: newAccountRole,
        }),
      });

      const data = await res.json();
      if (data.success) {
        const msg = `${newAccountRole} account created successfully!`;
        setProvisionMsg({ type: "success", text: msg });
        toast.success(msg);
        setNewAccountName("");
        setNewAccountEmail("");
        setNewAccountPassword("");
        setIsCreateModalOpen(false);
        fetchAccounts();
      } else {
        throw new Error(data.error || "Failed to create account");
      }
    } catch (err: any) {
      setProvisionMsg({ type: "error", text: err.message });
      toast.error(err.message);
    } finally {
      setIsProvisioning(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6">
        <Card className="bg-background/60 backdrop-blur border-border/50">
          <CardHeader>
            <CardTitle>Profile Configuration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 border-t border-border/50 pt-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="firstName">First Name</Label>
                <Input id="firstName" defaultValue="Ujala" className="bg-background/50" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="lastName">Last Name</Label>
                <Input id="lastName" defaultValue="Zaib" className="bg-background/50" />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email Address</Label>
              <Input id="email" type="email" defaultValue="admin@falsora.ai" className="bg-background/50" disabled />
              <p className="text-xs text-muted-foreground">Email changes require superadmin approval.</p>
            </div>
          </CardContent>
          <CardFooter className="justify-end border-t border-border/50 pt-4">
            <Button>Save Changes</Button>
          </CardFooter>
        </Card>

        {/* Provisioned Accounts */}
        <Card className="bg-background/60 backdrop-blur border-border/50">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
            <div>
              <CardTitle>Provisioned Accounts ({users.length})</CardTitle>
              <CardDescription className="text-xs text-muted-foreground mt-1">Manage user & reviewer access accounts.</CardDescription>
            </div>
            <Button
              onClick={() => {
                setProvisionMsg({ type: "", text: "" });
                setIsCreateModalOpen(true);
              }}
              className="cursor-pointer gap-1.5"
              size="sm"
            >
              <UserPlus className="w-4 h-4" />
              Provision New Account
            </Button>
          </CardHeader>

          <CardContent className="border-t border-border/50 pt-6">
            {isLoadingUsers ? (
              <p className="text-xs text-muted-foreground">Loading accounts...</p>
            ) : users.length === 0 ? (
              <p className="text-xs text-muted-foreground">No custom provisioned accounts yet. Click "Provision New Account" above to create one.</p>
            ) : (
              <div className="rounded-md border border-border/50 overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted/40 text-muted-foreground border-b border-border/50">
                    <tr>
                      <th className="px-4 py-2.5 font-medium">Name</th>
                      <th className="px-4 py-2.5 font-medium">Email</th>
                      <th className="px-4 py-2.5 font-medium">Role</th>
                      <th className="px-4 py-2.5 font-medium">Created</th>
                      <th className="px-4 py-2.5 font-medium text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/30">
                    {users.map((u) => (
                      <tr key={u.id} className="hover:bg-muted/20">
                        <td className="px-4 py-2.5 font-medium text-foreground">{u.name}</td>
                        <td className="px-4 py-2.5 text-muted-foreground font-mono">{u.email}</td>
                        <td className="px-4 py-2.5">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold ${
                            u.role === 'Administrator' ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20' :
                            u.role === 'Reviewer' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' :
                            'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                          }`}>
                            {u.role}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-muted-foreground">
                          {u.createdAt ? new Date(u.createdAt).toLocaleDateString() : 'N/A'}
                        </td>
                        <td className="px-4 py-2.5 text-right space-x-1">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-amber-400 hover:text-amber-300 hover:bg-amber-500/10 cursor-pointer"
                            onClick={() => setResetConfirmUser(u)}
                            disabled={actionLoadingId === `reset-${u.id}`}
                            title="Reset Password"
                          >
                            <Key className="w-3.5 h-3.5" />
                            <span className="sr-only">Reset Password</span>
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-red-400 hover:text-red-300 hover:bg-red-500/10 cursor-pointer"
                            onClick={() => setDeleteConfirmUser(u)}
                            disabled={actionLoadingId === `delete-${u.id}`}
                            title="Delete Account"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            <span className="sr-only">Delete Account</span>
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="bg-background/60 backdrop-blur border-border/50">
          <CardHeader>
            <CardTitle>Detection Thresholds</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 border-t border-border/50 pt-6">
            <div className="space-y-2">
              <div className="flex justify-between">
                <Label>Deepfake Confidence Threshold (Auto-Flag)</Label>
                <span className="text-sm font-medium text-primary">
                  {Array.isArray(threshold) ? threshold[0] : threshold}%
                </span>
              </div>
              <Slider 
                min={50} 
                max={99} 
                step={1}
                value={threshold} 
                onValueChange={(val) => setThreshold(Array.isArray(val) ? val : [val])} 
                className="w-full py-4 cursor-pointer" 
              />
              <p className="text-xs text-muted-foreground">Any media scoring above this will automatically generate an Alert.</p>
            </div>
          </CardContent>
          <CardFooter className="justify-end border-t border-border/50 pt-4">
            <Button variant="secondary">Reset Defaults</Button>
            <Button className="ml-2">Apply Thresholds</Button>
          </CardFooter>
        </Card>

        <Card className="bg-background/60 backdrop-blur border-destructive/20">
          <CardHeader>
            <CardTitle className="text-destructive">Danger Zone</CardTitle>
          </CardHeader>
          <CardContent className="border-t border-border/50 pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-sm">Purge Cache</p>
                <p className="text-xs text-muted-foreground">Clears all temporary forensic analysis files.</p>
              </div>
              <Button variant="destructive">Purge Cache</Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Create New Account Dialog */}
      <Dialog open={isCreateModalOpen} onOpenChange={setIsCreateModalOpen}>
        <DialogContent className="sm:max-w-md bg-background/95 backdrop-blur border border-border/80 p-6 overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base font-semibold">
              <UserPlus className="w-4 h-4 text-primary" />
              Provision New Account
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground mt-1">
              Provision a new Reviewer or User account into Neon PostgreSQL DB.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleProvisionAccount} className="space-y-4 mt-2">
            {provisionMsg.text && (
              <div className={`p-3 text-xs rounded-md border flex items-center gap-2 ${provisionMsg.type === "success" ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" : "bg-red-500/10 border-red-500/20 text-red-400"}`}>
                <span>{provisionMsg.text}</span>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="provName">Full Name</Label>
              <Input
                id="provName"
                placeholder="e.g. Dr. Sarah Connor"
                value={newAccountName}
                onChange={(e) => setNewAccountName(e.target.value)}
                required
                className="bg-background/50"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="provEmail">Email Address</Label>
              <Input
                id="provEmail"
                type="email"
                placeholder="sarah@falsora.ai"
                value={newAccountEmail}
                onChange={(e) => setNewAccountEmail(e.target.value)}
                required
                className="bg-background/50"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="provPassword">Password</Label>
              <Input
                id="provPassword"
                type="password"
                placeholder="••••••••"
                value={newAccountPassword}
                onChange={(e) => setNewAccountPassword(e.target.value)}
                required
                className="bg-background/50"
              />
            </div>

            <div className="space-y-2">
              <Label>Assigned Role</Label>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant={newAccountRole === "Reviewer" ? "default" : "outline"}
                  onClick={() => setNewAccountRole("Reviewer")}
                  className="flex-1 cursor-pointer"
                >
                  Reviewer
                </Button>
                <Button
                  type="button"
                  variant={newAccountRole === "User" ? "default" : "outline"}
                  onClick={() => setNewAccountRole("User")}
                  className="flex-1 cursor-pointer"
                >
                  Public User
                </Button>
              </div>
            </div>

            <DialogFooter className="-mx-6 -mb-6 mt-6 px-6 py-4 border-t border-border/40 bg-muted/30 flex justify-end gap-2 rounded-b-xl">
              <Button
                type="button"
                variant="outline"
                onClick={() => setIsCreateModalOpen(false)}
                className="cursor-pointer"
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isProvisioning} className="cursor-pointer">
                {isProvisioning ? "Provisioning..." : `Provision ${newAccountRole}`}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteConfirmUser} onOpenChange={(open) => !open && setDeleteConfirmUser(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogMedia className="bg-destructive/10 text-destructive">
              <Trash2 className="w-6 h-6" />
            </AlertDialogMedia>
            <AlertDialogTitle>Delete user?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to permanently delete the account for{" "}
              <span className="font-semibold text-foreground">{deleteConfirmUser?.name}</span> (
              <span className="font-mono text-foreground">{deleteConfirmUser?.email}</span>)?
              <br /><br />
              This action cannot be undone. All access privileges associated with this account will be revoked immediately.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setDeleteConfirmUser(null)}>Cancel</AlertDialogCancel>
            <Button
              variant="destructive"
              onClick={confirmDeleteAccount}
              disabled={!!actionLoadingId}
            >
              {actionLoadingId ? "Deleting..." : "Delete Account"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Password Reset Confirmation */}
      <AlertDialog open={!!resetConfirmUser} onOpenChange={(open) => !open && setResetConfirmUser(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogMedia className="bg-amber-500/10 text-amber-500">
              <KeyRound className="w-6 h-6" />
            </AlertDialogMedia>
            <AlertDialogTitle>Reset user password?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to reset the password for{" "}
              <span className="font-semibold text-foreground">{resetConfirmUser?.name}</span> (
              <span className="font-mono text-foreground">{resetConfirmUser?.email}</span>)?
              <br /><br />
              This will generate a new temporary password and invalidate their current one.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setResetConfirmUser(null)}>Cancel</AlertDialogCancel>
            <Button
              className="bg-amber-500 hover:bg-amber-600 text-white"
              onClick={handleResetPassword}
              disabled={!!actionLoadingId}
            >
              {actionLoadingId ? "Resetting..." : "Reset Password"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Reset Password Result Dialog */}
      <Dialog open={resetModalData.open} onOpenChange={(open) => setResetModalData((prev) => ({ ...prev, open }))}>
        <DialogContent className="sm:max-w-md bg-background/95 backdrop-blur border border-border/80 p-6 overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base font-semibold">
              <Key className="w-4 h-4 text-amber-400" />
              Password Reset Successful
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground mt-1">
              New temporary password generated for <span className="font-semibold text-foreground">{resetModalData.user?.name}</span> ({resetModalData.user?.email}).
            </DialogDescription>
          </DialogHeader>

          <div className="my-4 p-3 bg-muted/60 rounded-lg border border-border/60 flex items-center justify-between gap-3">
            <code className="text-sm font-mono tracking-wider font-bold text-amber-400 select-all">
              {resetModalData.password}
            </code>
            <Button
              size="sm"
              variant="secondary"
              onClick={copyPassword}
              className="h-8 gap-1.5 text-xs cursor-pointer shrink-0"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              {copied ? "Copied!" : "Copy"}
            </Button>
          </div>

          <p className="text-[11px] text-muted-foreground">
            Please make sure to copy and send this temporary password to the account holder.
          </p>

          <DialogFooter className="-mx-6 -mb-6 mt-6 px-6 py-4 border-t border-border/40 bg-muted/30 flex justify-end gap-2 rounded-b-xl">
            <Button
              variant="default"
              onClick={() => setResetModalData({ open: false, user: null, password: "" })}
              className="cursor-pointer"
            >
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
