import assert from "node:assert/strict";
import test from "node:test";

import { formatBlockNumber } from "./format.ts";

test("formatBlockNumber uses stable comma separators for SSR and client", () => {
  assert.equal(formatBlockNumber(0), "0");
  assert.equal(formatBlockNumber(14442835), "14,442,835");
  assert.equal(formatBlockNumber(19442835), "19,442,835");
});
