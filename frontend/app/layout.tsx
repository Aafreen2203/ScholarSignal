import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "ScholarSignal — Research, connected",
  description: "A considered workspace for discovering scientific literature.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}

