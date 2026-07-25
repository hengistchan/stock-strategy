import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { queryKeys } from "../api/queryKeys";
import type { StrategyMigrationReport } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import type { TranslationKey } from "../i18n/translations";

interface StrategyMigrationPanelProps {
  onImported: (path: string) => void;
}

const fixtureStatusKeys: Record<
  StrategyMigrationReport["fixture"]["status"],
  TranslationKey
> = {
  not_run: "migration.status.notRun",
  blocked: "migration.status.blocked",
  passed: "migration.status.passed",
  failed: "migration.status.failed",
};

export function StrategyMigrationPanel({
  onImported,
}: StrategyMigrationPanelProps) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [report, setReport] = useState<StrategyMigrationReport | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const scanMutation = useMutation({
    mutationFn: () => api.scanMigration(content),
    onSuccess: (result) => {
      setReport(result);
      setNotice(null);
    },
    onError: (error) => setNotice(error.message),
  });
  const fixtureMutation = useMutation({
    mutationFn: () => api.validateMigrationFixture(content),
    onSuccess: (result) => {
      setReport(result);
      setNotice(
        result.fixture.status === "passed"
          ? t("migration.fixturePassed")
          : result.fixture.error ?? t("migration.fixtureFailed"),
      );
    },
    onError: (error) => setNotice(error.message),
  });
  const importMutation = useMutation({
    mutationFn: () => api.importMigration(name, content),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.strategies });
      void queryClient.invalidateQueries({ queryKey: queryKeys.config });
      queryClient.setQueryData(
        queryKeys.strategy(result.strategy.path),
        result.strategy,
      );
      setReport(result.report);
      setNotice(t("migration.imported", { path: result.strategy.path }));
      onImported(result.strategy.path);
    },
    onError: (error) => setNotice(error.message),
  });

  const validName = /^[a-zA-Z][a-zA-Z0-9_]{0,63}(\.py)?$/.test(name);
  const busy =
    scanMutation.isPending ||
    fixtureMutation.isPending ||
    importMutation.isPending;
  const canRun = content.trim().length > 0 && !busy;

  return (
    <details className="migration-panel">
      <summary>{t("migration.title")}</summary>
      <div className="migration-body">
        <p>{t("migration.help")}</p>
        <label>
          <span>{t("migration.file")}</span>
          <input
            type="file"
            accept=".py,text/x-python,text/plain"
            onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              if (!file) return;
              void file.text().then((source) => {
                setContent(source);
                setName(file.name.replace(/\.py$/i, ""));
                setReport(null);
              });
            }}
          />
        </label>
        <label>
          <span>{t("migration.name")}</span>
          <input
            value={name}
            placeholder="migrated_strategy"
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label>
          <span>{t("migration.source")}</span>
          <textarea
            value={content}
            placeholder={t("migration.placeholder")}
            spellCheck={false}
            onChange={(event) => {
              setContent(event.target.value);
              setReport(null);
            }}
          />
        </label>
        <div className="migration-actions">
          <button
            type="button"
            disabled={!canRun}
            onClick={() => scanMutation.mutate()}
          >
            {t("migration.scan")}
          </button>
          <button
            type="button"
            disabled={!canRun || report?.compatibility.supported !== true}
            onClick={() => fixtureMutation.mutate()}
          >
            {fixtureMutation.isPending
              ? t("migration.fixtureRunning")
              : t("migration.fixture")}
          </button>
          <button
            type="button"
            disabled={
              !canRun ||
              !validName ||
              report?.fixture.status !== "passed"
            }
            onClick={() => importMutation.mutate()}
          >
            {importMutation.isPending
              ? t("migration.importing")
              : t("migration.import")}
          </button>
        </div>

        {report ? <MigrationReport report={report} /> : null}
        {notice ? (
          <p className="migration-notice" role="status">
            {notice}
          </p>
        ) : null}
      </div>
    </details>
  );
}

function MigrationReport({ report }: { report: StrategyMigrationReport }) {
  const { t } = useI18n();
  const findings = report.compatibility.findings ?? [];
  return (
    <section className="migration-report">
      <header>
        <strong>
          {report.compatibility.supported
            ? t("migration.staticPassed")
            : t("migration.staticBlocked")}
        </strong>
        <span data-status={report.fixture.status}>
          {t(fixtureStatusKeys[report.fixture.status])}
        </span>
      </header>
      {findings.length ? (
        <ul>
          {findings.map((finding, index) => (
            <li key={`${finding.code}-${finding.line ?? index}`}>
              <strong>
                {finding.name ?? finding.code}
                {finding.line ? ` · L${finding.line}` : ""}
              </strong>
              <p>{finding.message}</p>
              <small>{finding.suggestion}</small>
            </li>
          ))}
        </ul>
      ) : (
        <p>{t("migration.noFindings")}</p>
      )}
      <details>
        <summary>{t("migration.semantics")}</summary>
        <ul>
          {(report.compatibility.semantic_differences ?? []).map((difference) => (
            <li key={difference.code}>{difference.message}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}
