import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { StrategyMetadata } from "../api/types";
import { formatDateTime } from "../lib/format";
import { StrategyEditor } from "./StrategyEditor";

interface StrategyWorkspaceProps {
  strategies: StrategyMetadata[];
  selectedPath: string;
  onSelectedPathChange: (path: string) => void;
  onUseForBacktest: (path: string) => void;
}

export function StrategyWorkspace({
  strategies,
  selectedPath,
  onSelectedPathChange,
  onUseForBacktest,
}: StrategyWorkspaceProps) {
  const queryClient = useQueryClient();
  const [newName, setNewName] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [editorDirty, setEditorDirty] = useState(false);
  const documentQuery = useQuery({
    queryKey: ["strategy", selectedPath],
    queryFn: () => api.strategy(selectedPath),
    enabled: Boolean(selectedPath),
  });
  const document = documentQuery.data;

  const createMutation = useMutation({
    mutationFn: (templatePath?: string) =>
      api.createStrategy({ name: newName, template_path: templatePath }),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ["strategies"] });
      void queryClient.invalidateQueries({ queryKey: ["config"] });
      queryClient.setQueryData(["strategy", created.path], created);
      onSelectedPathChange(created.path);
      setEditorDirty(false);
      setNewName("");
      setNotice(`已创建 ${created.path}`);
    },
    onError: (error) => setNotice(error.message),
  });

  const grouped = useMemo(() => {
    const result = new Map<string, StrategyMetadata[]>();
    strategies.forEach((strategy) => {
      const group = result.get(strategy.group) ?? [];
      group.push(strategy);
      result.set(strategy.group, group);
    });
    return result;
  }, [strategies]);

  function selectStrategy(path: string) {
    if (editorDirty && !window.confirm("当前策略尚未保存，确定切换吗？")) return;
    setNotice(null);
    setEditorDirty(false);
    onSelectedPathChange(path);
  }

  const canCreate = /^[a-zA-Z][a-zA-Z0-9_]{0,63}(\.py)?$/.test(newName);
  return (
    <main className="strategy-workspace">
      <aside className="strategy-browser">
        <div className="strategy-browser-heading">
          <span className="section-code">REPOSITORY</span>
          <h2>策略仓库</h2>
          <p>示例只读；你的策略保存在项目的 strategies/。</p>
        </div>
        <div className="strategy-create">
          <label htmlFor="strategyName">新策略名称</label>
          <div>
            <input id="strategyName" value={newName} placeholder="my_strategy" onChange={(event) => setNewName(event.target.value)} />
            <button type="button" disabled={!canCreate || createMutation.isPending} onClick={() => createMutation.mutate(undefined)}>新建</button>
          </div>
        </div>
        <div className="strategy-list">
          {[...grouped].map(([group, items]) => (
            <section key={group}>
              <h3>{group}</h3>
              {items.map((strategy) => (
                <button
                  key={strategy.path}
                  type="button"
                  aria-current={strategy.path === selectedPath}
                  onClick={() => selectStrategy(strategy.path)}
                >
                  <span>{strategy.name}</span>
                  <small>{strategy.readonly ? "READ ONLY" : formatDateTime(strategy.updated_at)}</small>
                </button>
              ))}
            </section>
          ))}
        </div>
      </aside>

      <section className="editor-desk">
        {documentQuery.isError ? <div className="editor-message">{documentQuery.error.message}</div> : null}
        {documentQuery.isLoading ? <div className="editor-message">正在读取策略文件…</div> : null}
        {!selectedPath ? <div className="editor-message">从左侧选择策略，或创建一个新文件。</div> : null}
        {document ? (
          <StrategyEditor
            key={document.path}
            document={document}
            canCopy={canCreate}
            copyPending={createMutation.isPending}
            onCopy={() => createMutation.mutate(document.path)}
            onUseForBacktest={onUseForBacktest}
            onDirtyChange={setEditorDirty}
          />
        ) : null}
        {notice ? <p className="editor-notice" role="status">{notice}</p> : null}
      </section>
    </main>
  );
}
