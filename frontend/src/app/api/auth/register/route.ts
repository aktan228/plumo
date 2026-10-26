import type { NextRequest } from "next/server";
import { handleAuth } from "@/lib/server/auth-handler";

export async function POST(request: NextRequest) {
  return handleAuth(request, "register");
}
