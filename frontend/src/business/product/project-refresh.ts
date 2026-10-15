import type { DocumentTask, DraftOutput, OutputFamily } from './product-api';

// Polling changes progress frequently, while report bodies usually stay unchanged.
export function stableTaskSnapshot(previous: DocumentTask | null, next: DocumentTask): DocumentTask {
  if (!previous) return next;
  const old = previous as unknown as Record<string, unknown>;
  const entries = Object.entries(next).map(([key, value]) => [key, JSON.stringify(old[key]) === JSON.stringify(value) ? old[key] : value]);
  return entries.length === Object.keys(previous).length && entries.every(([key, value]) => old[key as string] === value)
    ? previous : Object.fromEntries(entries) as DocumentTask;
}

export function outputBasisChanged(previous: DocumentTask | null, next: DocumentTask): boolean {
  return !!previous && (previous.id !== next.id || previous.input_version !== next.input_version
    || previous.blueprint_version !== next.blueprint_version || previous.blueprint?.sha256 !== next.blueprint?.sha256
    || JSON.stringify(previous.input) !== JSON.stringify(next.input) || (previous.blueprint_approved === true && next.blueprint_approved !== true));
}

export function currentOutputVersions(outputs: DraftOutput[]): Map<OutputFamily, string> {
  return new Map(outputs.filter(output => output.current && !output.stale)
    .map(output => [output.family, `${output.id}:${output.version}:${output.sha256}`]));
}
