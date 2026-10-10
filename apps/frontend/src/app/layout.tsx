import type { Metadata } from "next";
import { Geist } from "next/font/google";
import { KeyboardScrollRegions } from "@/components/keyboard-scroll-regions";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { cn } from "@/lib/utils";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "M&A CRM",
  description: "M&A CRM",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const language = await getLanguage();

  return (
    <html lang={language} className={cn("font-sans", geist.variable)}>
      <body>
        {children}
        <KeyboardScrollRegions label={MESSAGES[language]["a11y.scrollRegion"]} />
      </body>
    </html>
  );
}
