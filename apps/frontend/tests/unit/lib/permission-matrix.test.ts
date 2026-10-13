import { describe, expect, it } from "vitest";
import { toggleGrant, type PermissionMatrix } from "@/lib/permission-matrix";

const matrix: PermissionMatrix = {
  columns: [
    { id: 1, name: "Admin" },
    { id: 2, name: "Read-only" },
  ],
  rows: [
    { permission: "audit.read", granted: [true, false] },
    { permission: "dashboard.aggregated", granted: [false, true] },
  ],
};

describe("permission matrix", () => {
  it("lists the permissions a column grants after a toggle", () => {
    expect(toggleGrant(matrix, "audit.read", 1)).toEqual(["audit.read", "dashboard.aggregated"]);
    expect(toggleGrant(matrix, "dashboard.aggregated", 1)).toEqual([]);
  });

});
