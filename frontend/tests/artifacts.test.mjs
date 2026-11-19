import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ArtifactPanel from "../src/ArtifactPanel.tsx";

function panel(filename, data, state = "available") {
  const html = renderToStaticMarkup(createElement(ArtifactPanel, {
    label: "Artifact", filename, files: new Set([filename]), artifact: { state, data }, loading: false,
  }));
  return JSDOM.fragment(html);
}

test("Markdown preserves literal HTML and code and only activates supported links", () => {
  const content = panel("prompt.md", [
    "## Commands", "", "Treat `<br>` and <button> literally.", "",
    "[Docs](https://example.org/) · [Commands](#commands) · [unknown](other.md) · [bad](javascript:noop)",
    "", "![diagram](https://example.org/diagram.png)",
  ].join("\n"));
  const markdown = content.querySelector(".artifact-markdown");
  assert.equal(markdown.querySelector("code").textContent, "<br>");
  assert.match(markdown.textContent, /<button> literally/);
  assert.match(markdown.textContent, /diagram/);
  assert.equal(markdown.querySelector("button, br, img"), null);
  assert.deepEqual([...markdown.querySelectorAll("a")].map(link => link.getAttribute("href")), [
    "https://example.org/", "#" + markdown.querySelector("h2").id,
  ]);
});

test("JSON preserves empty collections, nulls, and multiline strings from older receipts", () => {
  const content = panel("iteration-1.json", { steps: [], metadata: {}, elapsed: null, progress: "one\ntwo" });
  assert.deepEqual([...content.querySelectorAll("li")].map(li => li.textContent), [
    "steps: []", "metadata: {}", "elapsed: null", "progress: one\ntwo",
  ]);
  const invalid = panel("plan.json", null, "invalid");
  assert.equal(invalid.querySelector(".artifact-state").textContent, "invalid");
  assert.equal(invalid.querySelector("button, pre, .artifact-json"), null);
});
