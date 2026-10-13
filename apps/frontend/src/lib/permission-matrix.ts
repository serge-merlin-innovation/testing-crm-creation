export type PermissionMatrix = {
  columns: { id: number; name: string }[];
  rows: { permission: string; granted: boolean[] }[];
};

/** The full permission list the column at `columnIndex` holds once `permission` is flipped. */
export function toggleGrant(matrix: PermissionMatrix, permission: string, columnIndex: number): string[] {
  return matrix.rows
    .filter((row) => (row.permission === permission ? !row.granted[columnIndex] : row.granted[columnIndex]))
    .map((row) => row.permission)
    .sort();
}

export function isPermissionMatrix(payload: unknown): payload is PermissionMatrix {
  return (
    typeof payload === "object" &&
    payload !== null &&
    Array.isArray((payload as PermissionMatrix).columns) &&
    Array.isArray((payload as PermissionMatrix).rows)
  );
}
