export interface VerificationCommand {
  index: number;
  total: number;
  command: string;
  started_at: string;
}

export interface LoopActivity {
  loop: number;
  phase: string;
  phase_started_at: string;
  verification: VerificationCommand | null;
}

export function isTerminal(state?: string): boolean {
  return state === "finished" || state === "cancelled" || state === "interrupted";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isTimestamp(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

// The artifact endpoint returns file contents, including JSON from older writers.
export function isLoopActivity(value: unknown): value is LoopActivity {
  if (!isRecord(value) || typeof value.loop !== "number" ||
      typeof value.phase !== "string" || !isTimestamp(value.phase_started_at)) {
    return false;
  }
  const command = value.verification;
  return command === null || (
    isRecord(command) && typeof command.command === "string" &&
    typeof command.index === "number" && typeof command.total === "number" &&
    isTimestamp(command.started_at)
  );
}
