import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const tenant = request.nextUrl.searchParams.get("tenant");
  if (!tenant) {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.redirect(new URL(`/tenant/${encodeURIComponent(tenant)}`, request.url));
}
