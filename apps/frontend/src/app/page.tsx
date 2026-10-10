import { redirect } from "next/navigation";
import { DEFAULT_AUTHENTICATED_PATH } from "@/lib/auth-routing";

/** `/` is the one page whose audience is anyone, so it stays public and hands off immediately: the
 *  proxy, not this page, decides what a signed-out visitor is shown at the other end. */
export default function Home() {
  redirect(DEFAULT_AUTHENTICATED_PATH);
}
