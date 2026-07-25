import { useMemo, useState, type CSSProperties } from "react";
import type {
  Experiment,
  ExperimentObjective,
} from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import type { Locale } from "../i18n/core";
import { formatNumber } from "../lib/format";
import {
  buildParameterSurface,
  type ParameterSurface,
} from "../lib/parameterSurface";

interface ParameterHeatmapProps {
  experiment: Experiment;
}

export function ParameterHeatmap({ experiment }: ParameterHeatmapProps) {
  const { locale, t } = useI18n();
  const parameterNames = Object.entries(experiment.parameter_grid)
    .filter(([, values]) => values.length > 1)
    .map(([name]) => name);
  const [xName, setXName] = useState(parameterNames[0] ?? "");
  const [requestedYName, setRequestedYName] = useState(parameterNames[1] ?? "");
  const yName = requestedYName === xName
    ? parameterNames.find((name) => name !== xName) ?? ""
    : requestedYName;
  const surface = useMemo(
    () => buildParameterSurface(experiment, xName, yName || null),
    [experiment, xName, yName],
  );

  if (!surface) return null;
  const aggregatedDimensions = Math.max(
    0,
    parameterNames.length - (surface.yName ? 2 : 1),
  );

  return (
    <section className="parameter-heatmap" aria-label={t("experiment.heatmap")}>
      <header>
        <div>
          <span className="section-code">PARAMETER SURFACE</span>
          <h3>{t("experiment.heatmap")}</h3>
          <p>
            {t("experiment.heatmapHelp", {
              objective: objectiveLabel(experiment.objective),
            })}
            {aggregatedDimensions > 0
              ? ` ${t("experiment.heatmapAggregated", { count: aggregatedDimensions })}`
              : ""}
          </p>
        </div>
        <div className="heatmap-axis-controls">
          <label>
            <span>X</span>
            <select value={surface.xName} onChange={(event) => setXName(event.target.value)}>
              {parameterNames.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          {parameterNames.length > 1 ? (
            <label>
              <span>Y</span>
              <select value={surface.yName ?? ""} onChange={(event) => setRequestedYName(event.target.value)}>
                {parameterNames.filter((name) => name !== surface.xName).map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
      </header>
      <div
        className="heatmap-grid"
        style={{ gridTemplateColumns: `minmax(82px, auto) repeat(${surface.xValues.length}, minmax(56px, 1fr))` }}
      >
        <span className="heatmap-corner">{surface.yName ?? surface.xName}</span>
        {surface.xValues.map((value) => (
          <strong key={`x-${String(value)}`} className="heatmap-axis-value">{String(value)}</strong>
        ))}
        {surface.yValues.map((yValue) => (
          <HeatmapRow
            key={`y-${String(yValue)}`}
            surface={surface}
            yValue={yValue}
            locale={locale}
            emptyLabel={t("experiment.noScore")}
          />
        ))}
      </div>
      <footer>
        <span>{t("experiment.weaker")}</span>
        <i aria-hidden="true" />
        <span>{t("experiment.stronger")}</span>
      </footer>
    </section>
  );
}

function HeatmapRow({
  surface,
  yValue,
  locale,
  emptyLabel,
}: {
  surface: ParameterSurface;
  yValue: ParameterSurface["yValues"][number];
  locale: Locale;
  emptyLabel: string;
}) {
  return (
    <>
      <strong className="heatmap-axis-value">
        {surface.yName ? String(yValue) : surface.xName}
      </strong>
      {surface.xValues.map((xValue) => {
        const cell = surface.cells.find(
          (candidate) => candidate.x === xValue && candidate.y === yValue,
        );
        const intensity = heatIntensity(
          cell?.score ?? null,
          surface.minScore,
          surface.maxScore,
        );
        const label = cell?.score == null
          ? emptyLabel
          : `${formatNumber(cell.score, 2, locale)} · ${cell.runs} run${cell.runs === 1 ? "" : "s"}`;
        return (
          <span
            key={`${String(yValue)}-${String(xValue)}`}
            className="heatmap-cell"
            data-best={cell?.bestRank === 1 ? "true" : undefined}
            style={{ "--heat": intensity } as CSSProperties}
            title={label}
          >
            {cell?.score == null ? "—" : formatNumber(cell.score, 2, locale)}
            {cell?.bestRank === 1 ? <b>#1</b> : null}
          </span>
        );
      })}
    </>
  );
}

function heatIntensity(
  score: number | null,
  minScore: number | null,
  maxScore: number | null,
): number {
  if (score === null || minScore === null || maxScore === null) return 0;
  if (maxScore === minScore) return 0.65;
  return 0.18 + 0.82 * (score - minScore) / (maxScore - minScore);
}

function objectiveLabel(objective: ExperimentObjective): string {
  if (objective === "sharpe_ratio") return "Sharpe";
  if (objective === "total_return_pct") return "return";
  return "drawdown";
}
