import { Fragment, useState, type ReactNode } from "react";
import Markdown, { RuleType } from "markdown-to-jsx/react";
import type { Artifact } from "./api/runs";
import { useTheme } from "./themes";

function ArtifactMarkdown({ text, filename, files }: {
  text: string;
  filename: string;
  files: ReadonlySet<string>;
}) {
  return (
    <Markdown className="artifact-markdown" options={{
      forceBlock: true, forceWrapper: true, wrapper: "div", disableParsingRawHTML: true,
      slugify: (heading, slugify) => `${filename}-${slugify(heading)}`,
      overrides: {
        a: ({ href = "", children }: { href?: string; children?: ReactNode }) => {
          const file = href.replace(/^\.\//, "");
          if (files.has(file)) return <a href={`#artifact-${file}`}>{children}</a>;
          if (href.startsWith("#")) return <a href={`#${filename}-${href.slice(1)}`}>{children}</a>;
          if (/^(https?:\/\/|mailto:)/i.test(href)) return <a href={href}>{children}</a>;
          return <span title={href}>{children}</span>;
        },
        img: ({ alt }: { alt?: string }) => <span>{alt}</span>,
      },
      renderRule(next, node, _children, state) {
        // The report writer uses literal <br> for newlines in table cells.
        if (node.type === RuleType.text && node.text.includes("<br>")) {
          return node.text.split("<br>").map((line, index) => (
            <Fragment key={`${state.key}-${index}`}>{index > 0 && <br />}{line}</Fragment>
          ));
        }
        return next();
      },
    }}>{text}</Markdown>
  );
}

function JsonField({ name, value }: { name: string; value: unknown }) {
  const [open, setOpen] = useState(false);
  const label = <span className="json-key">{name}</span>;
  if (value === null || typeof value !== "object") {
    const scalar = typeof value === "string"
      ? <span className="json-string">{value === "" ? '""' : value}</span>
      : <span className="json-literal">{String(value)}</span>;
    return <li>{label}: {scalar}</li>;
  }
  const array = Array.isArray(value);
  const count = array ? value.length : Object.keys(value).length;
  if (!count) return <li>{label}{array ? ": []" : ": {}"}</li>;
  const unit = array ? "item" : "field";
  return (
    <li>
      <details onToggle={event => setOpen(event.currentTarget.open)}>
        <summary>{label} <span className="json-count">{count} {unit}{count === 1 ? "" : "s"}</span></summary>
        {open && <JsonEntries value={value} />}
      </details>
    </li>
  );
}

function JsonEntries({ value }: { value: object }) {
  const entries = Object.entries(value);
  if (!entries.length) return <span>{Array.isArray(value) ? "[]" : "{}"}</span>;
  return <ul className="json-fields">{entries.map(([key, item]) => (
    <JsonField key={key} name={key} value={item} />
  ))}</ul>;
}

interface ArtifactPanelProps {
  label: string;
  filename: string;
  files: ReadonlySet<string>;
  artifact?: Artifact;
  loading: boolean;
  error?: Error;
  children?: ReactNode;
}

export default function ArtifactPanel({ label, filename, files, artifact, loading, error, children }: ArtifactPanelProps) {
  const { Button } = useTheme();
  const [showSource, setShowSource] = useState<boolean | null>(null);
  const data = artifact?.data;
  const json = data != null && typeof data === "object";
  const markdown = typeof data === "string" && (filename.endsWith(".md") || filename.endsWith(".final.txt"));
  // A byte window can begin inside a code fence or table.
  const source = showSource ?? artifact?.truncated;
  const available = artifact?.state === "available";
  let content: ReactNode;
  if (available) {
    if (json && !source) {
      content = <div className="artifact-json"><JsonEntries value={data} /></div>;
    } else if (markdown && !source) {
      content = <ArtifactMarkdown text={data} filename={filename} files={files} />;
    } else {
      content = <pre>{typeof data === "string" ? data : JSON.stringify(data, null, 2)}</pre>;
    }
  } else if (artifact) {
    content = <p className="artifact-state">{artifact.state}</p>;
  }
  return (
    <section id={`artifact-${filename}`} aria-label={label} className="artifact">
      <header className="artifact-heading">
        <h4>{label}</h4>
        {available && (json || markdown) && (
          <Button onClick={() => setShowSource(!source)}>{source ? "Show formatted" : "Show source"}</Button>
        )}
      </header>
      {loading && <p>Loading {label.toLowerCase()}…</p>}
      {error && <p role="alert">Could not load {label.toLowerCase()}. {error.message}</p>}
      {content}
      {children}
    </section>
  );
}
