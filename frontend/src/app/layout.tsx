import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Forensics — Blockchain Tracer",
  description: "Praca magisterska: automatyczne wykrywanie i analiza aktywności w blockchainie.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pl">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
