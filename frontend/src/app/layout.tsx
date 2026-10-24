import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { Sidebar } from "@/components/Sidebar";

import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "PolicyPilot",
  description: "AI compliance copilot: ask your policies, review contracts, cite every answer.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} font-sans`}>
        <div className="flex h-dvh flex-col md:flex-row">
          <Sidebar />
          <main className="min-h-0 flex-1 overflow-y-auto px-4 py-6 md:px-10 md:py-8">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
