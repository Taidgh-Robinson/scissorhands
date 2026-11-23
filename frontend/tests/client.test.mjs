import assert from "node:assert/strict";
import test from "node:test";
import { fetchJson, runPath } from "../src/api/client.ts";

test("fetchJson requests JSON and returns the decoded body", async t => {
  const request = t.mock.method(globalThis, "fetch", async () => Response.json([{ id: "demo" }]));
  assert.deepEqual(await fetchJson("/api/projects"), [{ id: "demo" }]);
  const [url, options] = request.mock.calls[0].arguments;
  assert.equal(url, "/api/projects");
  assert.equal(options.headers.Accept, "application/json");
});

test("fetchJson reports FastAPI errors and handles non-JSON proxy errors", async t => {
  const request = t.mock.method(globalThis, "fetch", async () =>
    Response.json({ detail: "Project folder unavailable" }, { status: 409 })
  );
  await assert.rejects(fetchJson("/api/projects/demo/runs"), /409: Project folder unavailable/);
  request.mock.mockImplementation(async () => new Response("offline", {
    status: 502, statusText: "Bad Gateway",
  }));
  await assert.rejects(fetchJson("/api/projects"), /502: Bad Gateway/);
});

test("run keys include project and work-item identity and encode path segments", () => {
  assert.equal(runPath("a/b", "Issue #2", "run-0001"), "/api/projects/a%2Fb/work-items/Issue%20%232/runs/run-0001");
});
