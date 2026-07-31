import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Club & Event Concierge",
  description:
    "Conversational, hallucination-free campus event discovery for UBC & Douglas College.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
