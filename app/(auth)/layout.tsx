import React from "react";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="relative flex min-h-screen items-center justify-center bg-background overflow-hidden">
      {/* Background Gradients */}
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-indigo-900/20 via-background to-background" />
      <div className="absolute -top-[500px] -right-[500px] h-[1000px] w-[1000px] rounded-full bg-violet-600/10 blur-[100px]" />
      <div className="absolute -bottom-[500px] -left-[500px] h-[1000px] w-[1000px] rounded-full bg-blue-600/10 blur-[100px]" />

      <div className="relative z-10 w-full max-w-md px-4">
        {children}
      </div>
    </div>
  );
}
