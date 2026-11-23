import { useState } from "react";
import { loopArtifacts, pageBytes, useLoopArtifact, useLoopDetail, type LoopArtifactKind } from "./api/loops";
import ArtifactPanel from "./ArtifactPanel";
import { useTheme } from "./themes";

interface ArtifactProps {
  loopUrl: string;
  live: boolean;
  kind: LoopArtifactKind;
  label: string;
  filename: string;
  files: ReadonlySet<string>;
  verification?: number;
}

function LoopArtifact({ loopUrl, live, kind, label, filename, files, verification }: ArtifactProps) {
  const { Button } = useTheme();
  const [offset, setOffset] = useState(0);
  const { data, error, isLoading } = useLoopArtifact(loopUrl, kind, live, offset, verification);
  const end = data ? data.offset + data.bytes_read : 0;
  return (
    <ArtifactPanel label={label} filename={filename} files={files} artifact={data} loading={isLoading} error={error}>
      {data?.truncated && data.bytes_read > 0 && (
        <p>Bytes {data.offset + 1}–{end} of {data.total_bytes}</p>
      )}
      {offset > 0 && (
        <Button onClick={() => setOffset(Math.max(0, offset - pageBytes))}>Previous page</Button>
      )}
      {data?.truncated && data.total_bytes !== null && end < data.total_bytes && (
        <Button onClick={() => setOffset(end)}>Next page</Button>
      )}
    </ArtifactPanel>
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
  const receiptFile = `iteration-${number}.json`;
  const artifacts = [
    ...loopArtifacts.map(([kind, label, template]) => ({
      kind, label, filename: template.replace("{number}", String(number)),
    })),
    ...checks.map((_, index) => ({
      kind: "verification_output" as const, label: `Verification output ${index + 1}`,
      filename: `verification-${index + 1}.log`, verification: index + 1,
    })),
  ];
  const files = new Set([receiptFile, ...artifacts.map(artifact => artifact.filename)]);
  return (
    <section aria-label={`Loop ${number} details`} className="loop-detail">
      <h3>Loop {number}</h3>
      <ArtifactPanel label="Receipt" filename={receiptFile} files={files} artifact={data?.receipt}
        loading={isLoading} error={error} />
      {artifacts.map(artifact => (
        <LoopArtifact key={artifact.filename} {...artifact} files={files} loopUrl={loopUrl} live={live} />
      ))}
    </section>
  );
}
