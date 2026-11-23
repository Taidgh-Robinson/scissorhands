import assert from "node:assert/strict";
import test from "node:test";
import { setTimeout as wait } from "node:timers/promises";
import { JSDOM } from "jsdom";

async function renderApp(t, savedTheme) {
  const dom = new JSDOM('<main id="test-root"></main>', { url: "http://localhost/" });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  // jsdom has no layout engine. BlackChalk observes element sizes for its ink strokes.
  globalThis.ResizeObserver = class {
    observe() {}
    disconnect() {}
  };
  if (savedTheme) dom.window.localStorage.setItem("scissorhands.viewer.theme", savedTheme);
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
    delete globalThis.ResizeObserver;
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
    delete globalThis.document;
    delete globalThis.window;
  });

  async function select(label, value) {
    const combobox = container.querySelector(`[role="combobox"][aria-label="${label}"]`);
    if (combobox) {
      await act(() => combobox.click());
      const option = [...container.querySelectorAll('[role="option"]')].find(
        element => element.textContent === value
      );
      assert.ok(option, `Missing ${label} option ${value}`);
      await act(() => option.click());
      return;
    }
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
  await select("Project", "Example");
  await select("Run", "TASK / run-0001 (running)");
  assert.match(container.textContent, /Verification command 2 of 3/);
  assert.equal(container.querySelector("code").textContent, "make test");
  assert.equal(container.querySelector("time").dateTime, started);
  await select("Loop", "Loop 2");
  assert.match(container.textContent, /Receiptmissing/);

  summary.state = "finished";
  summary.outcome = "completed";
  activity = { state: "missing", data: null };
  const deadline = Date.now() + 6000;
  while (!container.textContent.includes("Outcome: completed") && Date.now() < deadline) {
    await act(() => wait(50));
  }
  assert.match(container.textContent, /Outcome: completed/);
  assert.equal(container.querySelector('[aria-label="Receipt"] li').textContent, "completion_accepted: true");
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
  const report = [
    "# Loop report", "", "Outcome: **completed**.", "", "## Verification", "",
    "| Command | Output |", "| --- | --- |",
    "| `make test` | passed<br>[log](verification-1.log) |",
  ].join("\n");
  const promptPage = "```text\n" + "x".repeat(pageSize - 8);
  const artifactData = {
    report, prompt: promptPage + "\n# inside the fence\n```", agent_output: "# Output\nline 2",
    final_message: "- Final answer", status: { criteria: [{ met: true }] },
    plan: null, progress: "```sh\nmake test\n```", patch: "+new line",
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

  const { container, select, act } = await renderApp(t, "retired-theme");
  const viewer = container.querySelector("[data-ui-theme]");
  assert.equal(viewer.dataset.uiTheme, "blackchalk");
  await select("Project", "Example");
  await select("Run", "TASK / run-0001 (completed)");
  assert.deepEqual(loopRequests, []);
  await select("Loop", "Loop 1");
  assert.ok(loopRequests.every(url => url.startsWith(`${runUrl}/loops/1`)));
  assert.match(container.textContent, /receipt for loop 1/);
  const section = label => container.querySelector(`section[aria-label="${label}"]`);
  const clickButton = (section, text) => act(() => {
    const button = [...section.querySelectorAll("button")].find(button => button.textContent === text);
    assert.ok(button, `Missing button ${text}`);
    button.click();
  });
  const rendered = section("Report");
  assert.equal(rendered.querySelector("h1").textContent, "Loop report");
  assert.equal(rendered.querySelector("strong").textContent, "completed");
  assert.deepEqual([...rendered.querySelectorAll("th")].map(th => th.textContent), ["Command", "Output"]);
  assert.equal(rendered.querySelector("td code").textContent, "make test");
  const logLink = rendered.querySelector("td br + a");
  assert.equal(document.getElementById(logLink.hash.slice(1)), section("Verification output 1"));
  await clickButton(rendered, "Show source");
  assert.equal(rendered.querySelector("pre").textContent, report);
  await clickButton(rendered, "Show formatted");
  assert.ok(rendered.querySelector("table"));
  assert.equal(section("Final message").querySelector("li").textContent, "Final answer");
  assert.equal(section("Progress").querySelector("pre code").textContent.trimEnd(), "make test");
  assert.equal(section("Agent output").querySelector("pre").textContent, artifactData.agent_output);
  assert.equal(section("Patch").querySelector("pre").textContent, artifactData.patch);
  const status = section("Status");
  const expand = async details => {
    await act(async () => { details.querySelector("summary").click(); await wait(0); });
  };
  assert.equal(status.querySelector("summary").textContent, "criteria 1 item");
  assert.equal(status.querySelector("details").open, false);
  await expand(status.querySelector("details"));
  await expand(status.querySelector("details details"));
  await select("Theme", "blackchalk-dark");
  assert.equal(viewer.dataset.theme, "dark");
  assert.equal(window.localStorage.getItem("scissorhands.viewer.theme"), "blackchalk-dark");
  assert.ok(rendered.querySelector("table"));
  assert.ok(status.querySelector("details details").open);
  assert.equal(status.querySelector(".json-literal").textContent, "true");
  await clickButton(status, "Show source");
  assert.deepEqual(JSON.parse(status.querySelector("pre").textContent), artifactData.status);
  const prompt = section("Prompt");
  assert.equal(prompt.querySelector("pre").textContent, promptPage);
  await clickButton(prompt, "Next page");
  assert.equal(prompt.querySelector("pre").textContent, "\n# inside the fence\n```");
  assert.match(container.textContent, /Planmissing/);
  assert.match(container.textContent, /Verification output 1first check/);

  const log = container.querySelector('section[aria-label="Verification output 2"]');
  assert.equal(log.querySelector("pre").textContent, firstPage);
  await act(() => log.querySelector("button").click());
  assert.equal(log.querySelector("pre").textContent, "end of second check");
  await select("Theme", "plain");
  assert.equal(viewer.dataset.uiTheme, "plain");
  assert.equal(viewer.dataset.theme, undefined);
  assert.equal(window.localStorage.getItem("scissorhands.viewer.theme"), "plain");
  assert.equal(log.querySelector("pre").textContent, "end of second check");
  assert.ok(rendered.querySelector("table"));
  assert.ok(status.querySelector("pre"));
  await clickButton(prompt, "Show formatted");
  assert.ok(prompt.querySelector(".artifact-markdown"));
  await clickButton(prompt, "Previous page");
  assert.equal(prompt.querySelector("pre code").textContent.trimEnd().length, pageSize - 8);
  assert.match(container.textContent, /receipt for loop 1/);
  await select("Theme", "blackchalk");
  assert.equal(viewer.dataset.theme, "light");
  await act(() => log.querySelector("button").click());
  assert.equal(log.querySelector("pre").textContent, firstPage);

  await select("Loop", "Loop 2");
  assert.match(container.textContent, /receipt for loop 2/);
  assert.doesNotMatch(container.textContent, /receipt for loop 1|Verification output/);
  await select("Loop", "Select a loop");
  assert.equal(container.querySelector("pre"), null);
});

test("restores the saved theme and renders its project control", async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json([]));
  const { container } = await renderApp(t, "plain");
  assert.equal(container.querySelector("[data-ui-theme]").dataset.uiTheme, "plain");
  assert.equal(container.querySelector(".theme-picker select").value, "plain");
  assert.ok(container.querySelector(".fields select").disabled);
});

test("restores BlackChalk Dark with its sketch controls on reload", async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json([]));
  const { container } = await renderApp(t, "blackchalk-dark");
  const viewer = container.querySelector('.sketch-paper[data-theme="dark"]');
  assert.equal(viewer.querySelector(".theme-picker select").selectedOptions[0].textContent, "BlackChalk Dark");
  assert.ok(viewer.querySelector('[role="combobox"][aria-label="Project"]'));
});
