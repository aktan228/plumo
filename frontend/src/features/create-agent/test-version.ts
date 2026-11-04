/** Missing version data must not silently assert that an old test is current. */
export function testVersionState(tested: number | undefined, current: number | null | undefined): "current" | "stale" | "unknown" {
  if (tested === undefined || current === undefined) return "unknown";
  return tested === current ? "current" : "stale";
}
