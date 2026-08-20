import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth/AuthProvider";

export const metadata: Metadata = {
  title: {
    default: "Apex — studio photo motorsport",
    template: "%s · Apex",
  },
  description:
    "Outil interne de gestion d'un studio photo de sport mécanique — ingestion, rattachement et bibliothèque.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fr">
      <body className="antialiased min-h-screen">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
