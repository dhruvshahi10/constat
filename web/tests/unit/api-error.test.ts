import { describe, expect, it } from "vitest";
import { parseApiError } from "@/lib/api";

describe("parseApiError", () => {
  it("reads the API's own {error, code}", () => {
    expect(parseApiError({ error: "no such claim", code: "NOT_FOUND" }, 404, "Not Found")).toEqual({ error: "no such claim", code: "NOT_FOUND" });
  });

  it("unwraps an HTTPException's {detail: {error, code}}", () => {
    const body = { detail: { error: "the source was not drafted: hidden text", code: "QUARANTINED" } };
    expect(parseApiError(body, 422, "Unprocessable Entity")).toEqual({ error: "the source was not drafted: hidden text", code: "QUARANTINED" });
  });

  it("joins request validation messages", () => {
    const body = { detail: [{ loc: ["body", "text"], msg: "String should have at least 1 character" }] };
    expect(parseApiError(body, 422, "")).toEqual({ error: "String should have at least 1 character", code: "INVALID" });
  });

  it("falls back to the status when the body says nothing", () => {
    expect(parseApiError(null, 502, "Bad Gateway")).toEqual({ error: "Bad Gateway", code: "HTTP_502" });
    expect(parseApiError({ detail: "Not authenticated" }, 401, "Unauthorized")).toEqual({ error: "Not authenticated", code: "HTTP_401" });
  });
});
