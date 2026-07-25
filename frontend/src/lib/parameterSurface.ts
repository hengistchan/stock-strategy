import type { Experiment, ExperimentRun, ParameterValue } from "../api/types";

interface HeatmapCell {
  x: ParameterValue;
  y: ParameterValue | null;
  score: number | null;
  runs: number;
  bestRank: number | null;
}

export interface ParameterSurface {
  xName: string;
  yName: string | null;
  xValues: ParameterValue[];
  yValues: Array<ParameterValue | null>;
  cells: HeatmapCell[];
  minScore: number | null;
  maxScore: number | null;
}

export function buildParameterSurface(
  experiment: Pick<Experiment, "parameter_grid" | "runs">,
  requestedX?: string,
  requestedY?: string | null,
): ParameterSurface | null {
  const varyingNames = Object.entries(experiment.parameter_grid)
    .filter(([, values]) => values.length > 1)
    .map(([name]) => name);
  const xName = varyingNames.includes(requestedX ?? "")
    ? requestedX!
    : varyingNames[0];
  if (!xName) return null;
  const yName = requestedY && requestedY !== xName && varyingNames.includes(requestedY)
    ? requestedY
    : varyingNames.find((name) => name !== xName) ?? null;
  const xValues = experiment.parameter_grid[xName];
  const yValues = yName ? experiment.parameter_grid[yName] : [null];
  const cells = yValues.flatMap((y) =>
    xValues.map((x) => aggregateCell(experiment.runs, xName, x, yName, y)),
  );
  const scores = cells
    .map((cell) => cell.score)
    .filter((score): score is number => score !== null);
  return {
    xName,
    yName,
    xValues,
    yValues,
    cells,
    minScore: scores.length ? Math.min(...scores) : null,
    maxScore: scores.length ? Math.max(...scores) : null,
  };
}

function aggregateCell(
  runs: ExperimentRun[],
  xName: string,
  x: ParameterValue,
  yName: string | null,
  y: ParameterValue | null,
): HeatmapCell {
  const matches = runs.filter(
    (run) =>
      run.status === "succeeded"
      && run.score !== null
      && run.parameters[xName] === x
      && (!yName || run.parameters[yName] === y),
  );
  return {
    x,
    y,
    score: matches.length
      ? matches.reduce((total, run) => total + Number(run.score), 0) / matches.length
      : null,
    runs: matches.length,
    bestRank: matches.reduce<number | null>(
      (best, run) => run.rank !== null && (best === null || run.rank < best) ? run.rank : best,
      null,
    ),
  };
}
