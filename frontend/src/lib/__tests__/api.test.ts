import { describe, expect, it } from "vitest";

import { cleanParams, serializeParams } from "@/lib/api";

/**
 * These guard a bug that shipped silently for two stages.
 *
 * axios serialises arrays as `status[]=Blocked`. FastAPI declares
 * `status: list[str] = Query(None)` and reads the bare key, so a bracketed
 * name is simply absent: the filter binds to None, the branch never runs, and
 * the request still returns 200 with every row. A broken filter and a filter
 * that matched everything look identical from the UI, which is why nobody
 * noticed that every multi-select on three screens was dead.
 */
describe("serializeParams", () => {
  it("repeats the bare key for arrays, never brackets", () => {
    const query = serializeParams({ status: ["Blocked", "Assigned"] });
    expect(query).toBe("status=Blocked&status=Assigned");
    expect(query).not.toContain("[]");
    expect(query).not.toContain("%5B%5D");
  });

  it("keeps every value of a multi-select", () => {
    const parsed = new URLSearchParams(
      serializeParams({ status: ["In Progress", "Completed"] }),
    );
    expect(parsed.getAll("status")).toEqual(["In Progress", "Completed"]);
  });

  it("mixes scalars and arrays without losing either", () => {
    const parsed = new URLSearchParams(
      serializeParams({ page: 1, status: ["Blocked"], search: "GA Drawing" }),
    );
    expect(parsed.get("page")).toBe("1");
    expect(parsed.getAll("status")).toEqual(["Blocked"]);
    expect(parsed.get("search")).toBe("GA Drawing");
  });

  it("drops empty values rather than sending blanks the API would reject", () => {
    const query = serializeParams({
      a: undefined,
      b: null,
      c: "",
      d: [],
      e: "kept",
    });
    expect(query).toBe("e=kept");
  });

  it("preserves false and zero, which are meaningful filter values", () => {
    const parsed = new URLSearchParams(
      serializeParams({ overdue_only: false, page: 0 }),
    );
    expect(parsed.get("overdue_only")).toBe("false");
    expect(parsed.get("page")).toBe("0");
  });
});

describe("cleanParams", () => {
  it("strips unset filters so they never reach the query string", () => {
    expect(cleanParams({ a: "x", b: "", c: null, d: undefined, e: [] })).toEqual({
      a: "x",
    });
  });
});
