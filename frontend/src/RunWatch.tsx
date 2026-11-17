import { useEffect, useState } from "react";
import { isLoopActivity, isTerminal, type LoopActivity } from "./api/activity";
import { useRunDetail, type RunDetail } from "./api/runs";

function StartTime({ start, now }: { start: string; now: number }) {
  const date = new Date(start);
  const seconds = Math.max(0, Math.floor((now - date.getTime()) / 1000));
  return (
    <>
      <time dateTime={start}>{date.toLocaleTimeString()}</time> ({seconds}s elapsed)
    </>
  );
}

function Activity({ activity }: { activity: LoopActivity }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const command = activity.verification;

  return (
    <dl>
      <dt>Loop</dt>
      <dd>{activity.loop}</dd>
      <dt>Phase</dt>
      <dd>{activity.phase}</dd>
      <dt>Phase started</dt>
      <dd><StartTime start={activity.phase_started_at} now={now} /></dd>
      {command && (
        <>
          <dt>Verification command {command.index} of {command.total}</dt>
          <dd><code>{command.command}</code></dd>
          <dt>Command started</dt>
          <dd><StartTime start={command.started_at} now={now} /></dd>
        </>
      )}
    </dl>
  );
}

function ReportedActivity({ artifact }: { artifact: RunDetail["activity"] }) {
  if (!artifact || artifact.state === "missing") {
    return <p>No activity has been reported for this run.</p>;
  }
  if (artifact.state !== "available") {
    return <p>Live activity unavailable ({artifact.state}).</p>;
  }
  if (!isLoopActivity(artifact.data)) {
    return <p>Live activity unavailable (invalid data).</p>;
  }
  return <Activity activity={artifact.data} />;
}

export default function RunWatch({ url }: { url: string }) {
  const { data, error, isLoading } = useRunDetail(url);

  return (
    <section aria-label="Run detail">
      <h2>Run detail</h2>
      {isLoading && <p>Loading run…</p>}
      {error && <p role="alert">Could not refresh this run. {error.message}</p>}
      {data && (
        <>
          <p>{data.summary.work_item_id} / {data.summary.run_id} · {data.summary.state}</p>
          {data.summary.outcome && <p>Outcome: {data.summary.outcome}</p>}
          {data.loops.length > 0 && <p>Loops: {data.loops.join(", ")}</p>}
          {!isTerminal(data.summary.state) && <ReportedActivity artifact={data.activity} />}
        </>
      )}
    </section>
  );
}
