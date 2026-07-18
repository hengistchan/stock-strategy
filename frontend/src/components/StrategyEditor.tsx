import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { api } from "../api/client";
import type { StrategyDocument } from "../api/types";
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
      setNotice("策略已保存并通过 Python 语法校验。");
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
          <p>{formatNumber(document.size, 0)} bytes · revision {document.revision.slice(0, 8)}</p>
        </div>
        <div className="editor-actions">
          {document.readonly ? (
            <button type="button" className="secondary-action" disabled={!canCopy || copyPending} onClick={onCopy}>复制为新策略</button>
          ) : null}
          <button type="button" className="secondary-action" onClick={() => onUseForBacktest(document.path)}>用此策略回测</button>
          <button type="button" className="primary-action" disabled={!dirty || document.readonly || saveMutation.isPending} onClick={() => saveMutation.mutate()}>
            {saveMutation.isPending ? "保存中" : dirty ? "保存策略" : "已保存"}
          </button>
        </div>
      </header>
      <div className="editor-status" data-dirty={dirty}>
        <span>{document.readonly ? "示例策略只读" : dirty ? "有未保存修改" : "文件与磁盘一致"}</span>
        <span>⌘/Ctrl + S 保存 · 保存前执行 AST 语法校验</span>
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
