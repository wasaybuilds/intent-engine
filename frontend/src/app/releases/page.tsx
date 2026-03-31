import type { Metadata } from "next";
import { ReleasesPage } from "@/components/releases-page";

export const metadata: Metadata = {
  title: "Releases — Intent Engine",
  description: "What's new in Intent Engine.",
};

export default function Releases() {
  return <ReleasesPage />;
}
