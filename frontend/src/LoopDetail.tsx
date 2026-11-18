import { useState } from "react";
import { loopArtifacts, pageBytes, useLoopArtifact, useLoopDetail, type LoopArtifactKind } from "./api/loops";
import type { Artifact } from "./api/runs";
import { useTheme } from "./themes";

function ArtifactContent({ artifact }: { artifact: Artifact }) {
  if (artifact.state !== "available") return <p className="artifact-state">{artifact.state}</p>;
  const { data } = artifact;
  return <pre>{typeof data === "string" ? data : JSON.stringify(data, null, 2)}</pre>;
}

interface ArtifactProps {
  loopUrl: string;
  live: boolean;
  kind: LoopArtifactKind;
  label: string;
  verification?: number;
}

function LoopArtifact({ loopUrl, live, kind, label, verification }: ArtifactProps) {
  const { Button } = useTheme();
  const [offset, setOffset] = useState(0);
  const { data, error, isLoading } = useLoopArtifact(loopUrl, kind, live, offset, verification);
  const end = data ? data.offset + data.bytes_read : 0;
  return (
    <section aria-label={label} className="artifact">
      <h4>{label}</h4>
      {isLoading && <p>Loading…</p>}
      {error && <p role="alert">Could not load {label.toLowerCase()}. {error.message}</p>}
      {data && <ArtifactContent artifact={data} />}
      {data?.truncated && data.bytes_read > 0 && (
        <p>Bytes {data.offset + 1}–{end} of {data.total_bytes}</p>
      )}
      {offset > 0 && (
        <Button onClick={() => setOffset(Math.max(0, offset - pageBytes))}>Previous page</Button>
      )}
      {data?.truncated && data.total_bytes !== null && end < data.total_bytes && (
        <Button onClick={() => setOffset(end)}>Next page</Button>
      )}
    </section>
  );
}

interface LoopDetailProps {
  loopUrl: string;
  number: number;
  live: boolean;
  verification: string[];
}

export default function LoopDetail({ loopUrl, number, live, verification }: LoopDetailProps) {
  const { data, error, isLoading } = useLoopDetail(loopUrl, live);
  const commands = data?.receipt.data?.verification?.commands;
  const checks = Array.isArray(commands) ? commands : verification;
  return (
    <section aria-label={`Loop ${number} details`} className="loop-detail">
      <h3>Loop {number}</h3>
      <section className="artifact" aria-label="Receipt">
        <h4>Receipt</h4>
        {isLoading && <p>Loading receipt…</p>}
        {error && <p role="alert">Could not load loop receipt. {error.message}</p>}
        {data && <ArtifactContent artifact={data.receipt} />}
      </section>
      {loopArtifacts.map(([kind, label]) => (
        <LoopArtifact key={kind} loopUrl={loopUrl} live={live} kind={kind} label={label} />
      ))}
      {checks.map((_, index) => (
        <LoopArtifact
          key={index}
          loopUrl={loopUrl}
          live={live}
          kind="verification_output"
          label={`Verification output ${index + 1}`}
          verification={index + 1}
        />
      ))}
    </section>
  );
}
