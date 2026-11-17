import assert from "node:assert/strict";
import test from "node:test";
import { setTimeout as wait } from "node:timers/promises";
import { JSDOM } from "jsdom";

test("select a run, follow verification, and stop polling detail at completion", async t => {
  const dom = new JSDOM('<main id="test-root"></main>', { url: "http://localhost/" });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const { createElement, act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: App } = await import("../src/App.tsx");
  const container = document.getElementById("test-root");
  const root = createRoot(container);
  t.after(async () => {
    await act(() => root.unmount());
    dom.window.close();
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
    delete globalThis.document;
    delete globalThis.window;
  });

  const prefix = "/api/projects/project-1";
  const runUrl = `${prefix}/work-items/TASK/runs/run-0001`;
  const summary = { work_item_id: "TASK", run_id: "run-0001", state: "running", outcome: null };
  const started = new Date().toISOString();
  let activity = {
    state: "available",
    data: {
      loop: 2, phase: "verifying", phase_started_at: started,
      verification: { index: 2, total: 3, command: "make test", started_at: started },
    },
  };
  let detailReads = 0;
  t.mock.method(globalThis, "fetch", async url => {
    if (url === "/api/projects") return Response.json([{ id: "project-1", name: "Example", available: true }]);
    if (url === `${prefix}/runs`) return Response.json([summary]);
    assert.equal(url, runUrl);
    detailReads++;
    return Response.json({ summary, loops: [1, 2], activity });
  });

  async function select(label, value) {
    const input = [...container.querySelectorAll("select")].find(
      element => element.labels[0].textContent.trim().startsWith(label)
    );
    assert.ok(input, `Missing ${label} selector`);
    await act(() => {
      input.value = value;
      input.dispatchEvent(new window.Event("change", { bubbles: true }));
    });
  }

  await act(() => root.render(createElement(App)));
  await select("Project", "project-1");
  await select("Run", runUrl);
  assert.match(container.textContent, /Verification command 2 of 3/);
  assert.equal(container.querySelector("code").textContent, "make test");
  assert.equal(container.querySelector("time").dateTime, started);

  summary.state = "finished";
  summary.outcome = "completed";
  activity = { state: "missing", data: null };
  const deadline = Date.now() + 6000;
  while (!container.textContent.includes("Outcome: completed") && Date.now() < deadline) {
    await act(() => wait(50));
  }
  assert.match(container.textContent, /Outcome: completed/);
  assert.equal(container.querySelector("code"), null);
  const finalReads = detailReads;
  await act(() => wait(2200));
  assert.equal(detailReads, finalReads);
});
