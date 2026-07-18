import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { api } from "../api/client";
import type { StrategyDocument } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import { formatNumber } from "../lib/format";

interface StrategyEditorProps {
  document: StrategyDocument;
  canCopy: boolean;
  copyPending: boolean;
  onCopy: () => void;
  onUseForBacktest: (path: string) => void;
  onDirtyChange: (dirty: boolean) => void;
}

const pythonExtension = python();

export function StrategyEditor({
  document,
  canCopy,
  copyPending,
  onCopy,
  onUseForBacktest,
  onDirtyChange,
}: StrategyEditorProps) {
  const { locale, t } = useI18n();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(document.content);
  const [notice, setNotice] = useState<string | null>(null);
  const dirty = draft !== document.content;
  const saveMutation = useMutation({
    mutationFn: () => api.saveStrategy(document.path, draft, document.revision),
    onSuccess: (saved) => {
      queryClient.setQueryData(["strategy", saved.path], saved);
      void queryClient.invalidateQueries({ queryKey: ["strategies"] });
      void queryClient.invalidateQueries({ queryKey: ["config"] });
      setDraft(saved.content);
      onDirtyChange(false);
      setNotice(t("strategy.savedNotice"));
    },
    onError: (error) => setNotice(error.message),
  });

  useEffect(() => {
    const handleSave = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (dirty && !document.readonly && !saveMutation.isPending) {
          saveMutation.mutate();
        }
      }
    };
    window.addEventListener("keydown", handleSave);
    return () => window.removeEventListener("keydown", handleSave);
  }, [dirty, document.readonly, saveMutation]);

  return (
    <>
      <header className="editor-toolbar">
        <div>
          <span className="section-code">PYTHON STRATEGY</span>
          <h2>{document.path}</h2>
          <p>{formatNumber(document.size, 0, locale)} bytes · revision {document.revision.slice(0, 8)}</p>
        </div>
        <div className="editor-actions">
          {document.readonly ? (
            <button type="button" className="secondary-action" disabled={!canCopy || copyPending} onClick={onCopy}>{t("strategy.copy")}</button>
          ) : null}
          <button type="button" className="secondary-action" onClick={() => onUseForBacktest(document.path)}>{t("strategy.useBacktest")}</button>
          <button type="button" className="primary-action" disabled={!dirty || document.readonly || saveMutation.isPending} onClick={() => saveMutation.mutate()}>
            {saveMutation.isPending ? t("strategy.saving") : dirty ? t("strategy.save") : t("strategy.saved")}
          </button>
        </div>
      </header>
      <div className="editor-status" data-dirty={dirty}>
        <span>{document.readonly ? t("strategy.readonly") : dirty ? t("strategy.unsaved") : t("strategy.synced")}</span>
        <span>{t("strategy.saveHelp")}</span>
      </div>
      <div className="code-editor">
        <CodeMirror
          value={draft}
          height="calc(100vh - 302px)"
          minHeight="460px"
          extensions={[pythonExtension]}
          editable={!document.readonly}
          onChange={(value) => {
            setDraft(value);
            onDirtyChange(value !== document.content);
          }}
          basicSetup={{ foldGutter: true, highlightActiveLine: true, autocompletion: true }}
        />
      </div>
      {notice ? <p className="editor-notice" role="status">{notice}</p> : null}
    </>
  );
}
