import type { Me } from "../api/types";

/** Landing route after sign-in, by what the user can do. */
export function homePath(me: Me): string {
  if (me.role === "platform_admin") return "/platform";
  if (me.permissions.includes("analytics:read")) return "/dashboard";
  if (me.permissions.includes("tickets:work")) return "/tickets?view=mine";
  return "/tickets";
}
