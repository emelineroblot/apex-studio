"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth/AuthProvider";
import { Spinner } from "@/components/ui/States";

export default function RootPage() {
  const { user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (user === undefined) return;
    router.replace(user ? "/shootings" : "/login");
  }, [user, router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <Spinner label="Chargement d'Apex…" />
    </div>
  );
}
