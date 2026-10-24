import type { Metadata } from "next";
import { AuthScreen } from "@/features/auth/auth-screen";

export const metadata: Metadata = { robots: { index: false, follow: false }, referrer: "no-referrer" };
export default function AccountLink() { return <AuthScreen mode="verify" />; }
