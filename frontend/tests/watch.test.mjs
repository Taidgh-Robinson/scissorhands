import assert from "node:assert/strict";
import test from "node:test";
import { setTimeout as wait } from "node:timers/promises";
import { JSDOM } from "jsdom";

async function renderApp(t) {
  const dom = new JSDOM('<main id="test-root"></main>', { url: "http://localhost/" });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const { createElement, act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { SWRConfig } = await import("swr");
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

  await act(() => root.render(createElement(SWRConfig, {
    value: { provider: () => new Map() },
  }, createElement(App))));
  return { container, select, act };
}

test("select a run, follow verification, and stop polling detail at completion", async t => {
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
  let loopReads = 0;
  t.mock.method(globalThis, "fetch", async url => {
    if (url === "/api/projects") return Response.json([{ id: "project-1", name: "Example", available: true }]);
    if (url === `${prefix}/runs`) return Response.json([summary]);
    if (url === `${runUrl}/loops/2`) {
      loopReads++;
      const receipt = summary.state === "running"
        ? { state: "missing", data: null }
        : { state: "available", data: { completion_accepted: true } };
      return Response.json({ work_item_id: "TASK", run_id: summary.run_id, number: 2, receipt });
    }
    if (url.startsWith(`${runUrl}/loops/2/artifacts/`)) {
      return Response.json({ state: "missing", data: null });
    }
    assert.equal(url, runUrl);
    detailReads++;
    return Response.json({ summary, loops: [1, 2], activity });
  });

  const { container, select, act } = await renderApp(t);
  await select("Project", "project-1");
  await select("Run", runUrl);
  assert.match(container.textContent, /Verification command 2 of 3/);
  assert.equal(container.querySelector("code").textContent, "make test");
  assert.equal(container.querySelector("time").dateTime, started);
  await select("Loop", "2");
  assert.match(container.textContent, /Receiptmissing/);

  summary.state = "finished";
  summary.outcome = "completed";
  activity = { state: "missing", data: null };
  const deadline = Date.now() + 6000;
  while (!container.textContent.includes("Outcome: completed") && Date.now() < deadline) {
    await act(() => wait(50));
  }
  assert.match(container.textContent, /Outcome: completed/);
  assert.match(container.textContent, /"completion_accepted": true/);
  assert.equal(container.querySelector("code"), null);
  const finalReads = detailReads;
  const finalLoopReads = loopReads;
  await act(() => wait(2200));
  assert.equal(detailReads, finalReads);
  assert.equal(loopReads, finalLoopReads);
});

test("a finished run shows the selected loop's receipt, artifacts and paged verification logs", async t => {
  const prefix = "/api/projects/project-1";
  const runUrl = `${prefix}/work-items/TASK/runs/run-0001`;
  const summary = { work_item_id: "TASK", run_id: "run-0001", state: "finished", outcome: "completed" };
  const pageSize = 64 * 1024;
  const firstPage = "é".repeat(pageSize / 2);
  const logs = ["first check", firstPage + "end of second check"];
  const loopRequests = [];
  const artifactData = {
    report: "Loop report", prompt: "Saved prompt", agent_output: "Output\nline 2",
    final_message: "Final answer", status: { criteria: ["done"] },
    plan: null, progress: "Saved progress", patch: "+new line",
  };
  t.mock.method(globalThis, "fetch", async url => {
    if (url === "/api/projects") return Response.json([{ id: "project-1", name: "Example", available: true }]);
    if (url === `${prefix}/runs`) return Response.json([summary]);
    if (url === runUrl) return Response.json({ summary, loops: [1, 2] });
    loopRequests.push(url);
    const { pathname, searchParams } = new URL(url, "http://localhost");
    const [number, , kind] = pathname.slice(`${runUrl}/loops/`.length).split("/");
    if (!kind) {
      return Response.json({
        work_item_id: "TASK", run_id: summary.run_id, number: Number(number),
        receipt: { state: "available", data: {
          progress: `receipt for loop ${number}`,
          verification: { commands: number === "1" ? [
            { command: "lint", return_code: 0, passed: true },
            { command: "test", return_code: 0, passed: true },
          ] : [] },
        } },
      });
    }
    let data = kind === "verification_output"
      ? logs[Number(searchParams.get("verification")) - 1]
      : artifactData[kind];
    const offset = Number(searchParams.get("offset"));
    const limit = Number(searchParams.get("limit"));
    const bytes = Buffer.from(typeof data === "string" ? data : JSON.stringify(data));
    const page = bytes.subarray(offset, offset + limit);
    if (typeof data === "string") data = page.toString();
    return Response.json({
      state: data === null ? "missing" : "available", data, offset,
      bytes_read: page.length, total_bytes: bytes.length, truncated: page.length < bytes.length,
    });
  });

  const { container, select, act } = await renderApp(t);
  await select("Project", "project-1");
  await select("Run", runUrl);
  assert.deepEqual(loopRequests, []);
  await select("Loop", "1");
  assert.ok(loopRequests.every(url => url.startsWith(`${runUrl}/loops/1`)));
  assert.match(container.textContent, /receipt for loop 1/);
  for (const content of Object.values(artifactData)) {
    if (typeof content === "string") assert.ok(container.textContent.includes(content));
  }
  assert.match(container.textContent, /"criteria": \[/);
  assert.match(container.textContent, /Planmissing/);
  assert.match(container.textContent, /Verification output 1first check/);

  const log = container.querySelector('section[aria-label="Verification output 2"]');
  assert.equal(log.querySelector("pre").textContent, firstPage);
  await act(() => log.querySelector("button").click());
  assert.equal(log.querySelector("pre").textContent, "end of second check");
  await act(() => log.querySelector("button").click());
  assert.equal(log.querySelector("pre").textContent, firstPage);

  await select("Loop", "2");
  assert.match(container.textContent, /receipt for loop 2/);
  assert.doesNotMatch(container.textContent, /receipt for loop 1|Verification output/);
  await select("Loop", "");
  assert.equal(container.querySelector("pre"), null);
});
