/** The Atlan shell simulator ships only in development unless explicitly enabled. */
export const DEV_SHELL_ENABLED =
  process.env.NODE_ENV !== "production" || process.env.NEXT_PUBLIC_DEV_SHELL === "1";
