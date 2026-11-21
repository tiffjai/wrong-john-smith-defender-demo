import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./styles.css";
import AuthLinkHandler from "./auth/link-handler";
import { cloudMode, config } from "../lib/supabase";

export const metadata: Metadata = {
  title: "Wrong John Smith Defender",
  description: "Synthetic identity screening and record linkage QA.",
};

export default function Layout({ children }: { children: ReactNode }) {
  return <html lang="en"><body><AuthLinkHandler settings={cloudMode ? config() : null}/>{children}</body></html>;
}
