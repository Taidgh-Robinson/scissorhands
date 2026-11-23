import { useEffect, useState } from "react";
import { isLoopActivity, isTerminal, type LoopActivity } from "./api/activity";
import { useRunDetail, type RunDetail } from "./api/runs";
import LoopDetail from "./LoopDetail";
import { useTheme } from "./themes";

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
  const { Choice } = useTheme();
  const { data, error, isLoading } = useRunDetail(url);
  const [selectedLoop, setSelectedLoop] = useState<number | null>(null);
  const loop = data?.loops.find(number => number === selectedLoop);
  const verification = data?.work_item?.data?.verification;

  return (
    <section aria-label="Run detail" className="run-content">
      {isLoading && <p>Loading run…</p>}
      {error && <p role="alert">Could not refresh this run. {error.message}</p>}
      {data && (
        <>
          <div className="run-summary">
            <div>
              <p className="item-id">{data.summary.work_item_id}</p>
              <h3 className="run-id">{data.summary.run_id}</h3>
            </div>
            <span className="run-state">{data.summary.state}</span>
          </div>
          {data.summary.outcome && <p className="outcome">Outcome: <strong>{data.summary.outcome}</strong></p>}
          {!isTerminal(data.summary.state) && <ReportedActivity artifact={data.activity} />}
          {data.loops.length > 0 ? (
            <Choice
              label="Loop"
              value={loop === undefined ? "" : String(loop)}
              options={[
                { value: "", label: "Select a loop" },
                ...data.loops.map(number => ({ value: String(number), label: `Loop ${number}` })),
              ]}
              onChange={value => setSelectedLoop(Number(value) || null)}
            />
          ) : <p>No loops recorded yet.</p>}
          {loop !== undefined && (
            <LoopDetail
              key={loop}
              loopUrl={`${url}/loops/${loop}`}
              number={loop}
              live={loop === data.loops.at(-1) && !isTerminal(data.summary.state)}
              verification={Array.isArray(verification) ? verification : []}
            />
          )}
        </>
      )}
    </section>
  );
}
