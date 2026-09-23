import { redirect } from "next/navigation";

export default function Home() {
  // For now, redirect the root page directly to the authentication login page.
  redirect("/login");
}
