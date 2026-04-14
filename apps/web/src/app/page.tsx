import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export default async function RootPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get("aura_token");

  if (!token?.value) {
    redirect("/login");
  }

  redirect("/chat");
}
