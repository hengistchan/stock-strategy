import { ApiError } from "../../api/client";
import type { MonitorState } from "./MonitorStatePanel";

export function classifyMonitorError(error: unknown): MonitorState {
  if (!(error instanceof ApiError)) return "error";
  if (error.code === "market_data_permission_denied") return "permission";
  if (error.code === "market_data_quota_exhausted") return "quota";
  if (error.code === "opend_unavailable") return "offline";
  if (
    error.code === "monitor_snapshot_not_found"
    || error.code === "option_chain_not_found"
    || error.code === "option_contract_not_found"
  ) {
    return "unavailable";
  }
  return "error";
}
