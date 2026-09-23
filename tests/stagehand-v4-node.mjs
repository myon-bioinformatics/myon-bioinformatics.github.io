import * as stagehand from "@browserbasehq/stagehand";

// Node and Python probes intentionally reflect each SDK public export shape.
// The shared contract is import success plus the expected Stagehand surface.
if (typeof stagehand.Stagehand !== "function") {
  throw new Error("Stagehand v4 Node surface missing: expected Stagehand export");
}
console.log("Stagehand v4 Node surface: OK");
