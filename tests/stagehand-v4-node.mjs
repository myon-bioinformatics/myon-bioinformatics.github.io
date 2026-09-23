import * as stagehand from "@browserbasehq/stagehand";

if (typeof stagehand.Stagehand !== "function") {
  throw new Error("Stagehand v4 Node surface missing: expected Stagehand export");
}
console.log("Stagehand v4 Node surface: OK");
