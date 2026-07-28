export type OptionSide = "CALL" | "PUT";
export type OptionMoneyness = "ATM" | "ITM" | "OTM" | "UNKNOWN";
export type QuoteMarketState = "normal" | "locked" | "inverted" | "missing";

export interface OptionContractInput {
  code: unknown;
  name?: unknown;
  underlying_code?: unknown;
  option_type?: unknown;
  expiration?: unknown;
  strike_price?: unknown;
  lot_size?: unknown;
  suspended?: unknown;
  expiration_cycle?: unknown;
  standard_type?: unknown;
  settlement_mode?: unknown;
}

export interface OptionSnapshotInput {
  code: unknown;
  name?: unknown;
  underlying_code?: unknown;
  option_type?: unknown;
  expiration?: unknown;
  strike_price?: unknown;
  source_time?: unknown;
  fetched_at?: unknown;
  last_price?: unknown;
  previous_close?: unknown;
  change_rate?: unknown;
  volume?: unknown;
  turnover?: unknown;
  bid_price?: unknown;
  ask_price?: unknown;
  bid_volume?: unknown;
  ask_volume?: unknown;
  days_to_expiry?: unknown;
  option_contract_size?: unknown;
  option_open_interest?: unknown;
  option_net_open_interest?: unknown;
  option_implied_volatility?: unknown;
  option_premium?: unknown;
  option_delta?: unknown;
  option_gamma?: unknown;
  option_vega?: unknown;
  option_theta?: unknown;
  option_rho?: unknown;
}

export interface OptionChainContract {
  code: string;
  name: string | null;
  underlyingCode: string | null;
  side: OptionSide;
  expiration: string | null;
  strike: number;
  lotSize: number | null;
  suspended: boolean;
  expirationCycle: string | null;
  standardType: string | null;
  settlementMode: string | null;
  sourceTime: string | null;
  fetchedAt: string | null;
  lastPrice: number | null;
  previousClose: number | null;
  changeRate: number | null;
  volume: number | null;
  turnover: number | null;
  bidPrice: number | null;
  askPrice: number | null;
  bidVolume: number | null;
  askVolume: number | null;
  daysToExpiry: number | null;
  contractSize: number | null;
  openInterest: number | null;
  netOpenInterest: number | null;
  impliedVolatility: number | null;
  premium: number | null;
  delta: number | null;
  gamma: number | null;
  vega: number | null;
  theta: number | null;
  rho: number | null;
  midPrice: number | null;
  spread: number | null;
  spreadPct: number | null;
  volumeOpenInterestRatio: number | null;
  quoteMarketState: QuoteMarketState;
  moneyness: OptionMoneyness;
}

export interface OptionChainRow {
  strike: number;
  isAtm: boolean;
  call: OptionChainContract | null;
  put: OptionChainContract | null;
}

export interface OptionSideSummary {
  contractCount: number;
  totalVolume: number | null;
  totalOpenInterest: number | null;
  volumeObservedContracts: number;
  openInterestObservedContracts: number;
  volumeComplete: boolean;
  openInterestComplete: boolean;
}

export interface OptionChainSummary {
  call: OptionSideSummary;
  put: OptionSideSummary;
  callPutVolumeRatio: number | null;
  callPutOpenInterestRatio: number | null;
}

export interface OptionChainModel {
  rows: OptionChainRow[];
  atmStrike: number | null;
  summary: OptionChainSummary;
  rejectedContractCount: number;
  duplicateContractCount: number;
}

export interface BuildOptionChainInput {
  contracts: readonly OptionContractInput[];
  snapshots: readonly OptionSnapshotInput[];
  underlyingPrice: unknown;
}

interface IndexedContract {
  index: number;
  value: OptionChainContract;
}

interface MutableRow {
  strike: number;
  firstIndex: number;
  call: IndexedContract | null;
  put: IndexedContract | null;
}

const MISSING_TEXT = new Set(["", "N/A", "NA", "NAN", "NULL", "NONE", "--", "—"]);

export function buildOptionChain({
  contracts,
  snapshots,
  underlyingPrice,
}: BuildOptionChainInput): OptionChainModel {
  const snapshotsByCode = new Map<string, OptionSnapshotInput>();
  snapshots.forEach((snapshot) => {
    const code = normalizeCode(snapshot.code);
    if (code) snapshotsByCode.set(code, snapshot);
  });

  const rowsByStrike = new Map<number, MutableRow>();
  let rejectedContractCount = 0;
  let duplicateContractCount = 0;

  contracts.forEach((contract, index) => {
    const code = normalizeCode(contract.code);
    const snapshot = code ? snapshotsByCode.get(code) : undefined;
    const normalized = normalizeContract(contract, snapshot);
    if (!normalized) {
      rejectedContractCount += 1;
      return;
    }

    const row = rowsByStrike.get(normalized.strike) ?? {
      strike: normalized.strike,
      firstIndex: index,
      call: null,
      put: null,
    };
    const indexed = { index, value: normalized };
    if (normalized.side === "CALL") {
      if (row.call) duplicateContractCount += 1;
      else row.call = indexed;
    } else {
      if (row.put) duplicateContractCount += 1;
      else row.put = indexed;
    }
    rowsByStrike.set(normalized.strike, row);
  });

  const sortedRows = [...rowsByStrike.values()].sort(
    (left, right) => left.strike - right.strike || left.firstIndex - right.firstIndex,
  );
  const normalizedUnderlying = positiveNumber(underlyingPrice);
  const atmStrike = nearestStrike(
    sortedRows.map((row) => row.strike),
    normalizedUnderlying,
  );
  const rows = sortedRows.map<OptionChainRow>((row) => ({
    strike: row.strike,
    isAtm: atmStrike !== null && row.strike === atmStrike,
    call: row.call
      ? withMoneyness(row.call.value, normalizedUnderlying, atmStrike)
      : null,
    put: row.put
      ? withMoneyness(row.put.value, normalizedUnderlying, atmStrike)
      : null,
  }));

  return {
    rows,
    atmStrike,
    summary: summarizeChain(rows),
    rejectedContractCount,
    duplicateContractCount,
  };
}

function normalizeContract(
  contract: OptionContractInput,
  snapshot: OptionSnapshotInput | undefined,
): OptionChainContract | null {
  const code = normalizeCode(contract.code);
  const side = optionSide(contract.option_type) ?? optionSide(snapshot?.option_type);
  const strike = positiveNumber(contract.strike_price) ?? positiveNumber(snapshot?.strike_price);
  if (!code || !side || strike === null) return null;

  const bidPrice = nonNegativeNumber(snapshot?.bid_price);
  const askPrice = nonNegativeNumber(snapshot?.ask_price);
  const quote = quoteMetrics(bidPrice, askPrice);
  const volume = nonNegativeNumber(snapshot?.volume);
  const openInterest = nonNegativeNumber(snapshot?.option_open_interest);

  return {
    code,
    name: text(contract.name) ?? text(snapshot?.name),
    underlyingCode:
      normalizeCode(contract.underlying_code) ?? normalizeCode(snapshot?.underlying_code),
    side,
    expiration: text(contract.expiration) ?? text(snapshot?.expiration),
    strike,
    lotSize: nonNegativeInteger(contract.lot_size),
    suspended: contract.suspended === true,
    expirationCycle: text(contract.expiration_cycle),
    standardType: text(contract.standard_type),
    settlementMode: text(contract.settlement_mode),
    sourceTime: text(snapshot?.source_time),
    fetchedAt: text(snapshot?.fetched_at),
    lastPrice: nonNegativeNumber(snapshot?.last_price),
    previousClose: nonNegativeNumber(snapshot?.previous_close),
    changeRate: finiteNumber(snapshot?.change_rate),
    volume,
    turnover: nonNegativeNumber(snapshot?.turnover),
    bidPrice,
    askPrice,
    bidVolume: nonNegativeNumber(snapshot?.bid_volume),
    askVolume: nonNegativeNumber(snapshot?.ask_volume),
    daysToExpiry: nonNegativeInteger(snapshot?.days_to_expiry),
    contractSize: positiveNumber(snapshot?.option_contract_size),
    openInterest,
    netOpenInterest: finiteNumber(snapshot?.option_net_open_interest),
    impliedVolatility: nonNegativeNumber(snapshot?.option_implied_volatility),
    premium: finiteNumber(snapshot?.option_premium),
    delta: finiteNumber(snapshot?.option_delta),
    gamma: finiteNumber(snapshot?.option_gamma),
    vega: finiteNumber(snapshot?.option_vega),
    theta: finiteNumber(snapshot?.option_theta),
    rho: finiteNumber(snapshot?.option_rho),
    midPrice: quote.midPrice,
    spread: quote.spread,
    spreadPct: quote.spreadPct,
    volumeOpenInterestRatio:
      volume !== null && openInterest !== null && openInterest > 0
        ? volume / openInterest
        : null,
    quoteMarketState: quote.state,
    moneyness: "UNKNOWN",
  };
}

function quoteMetrics(
  bidPrice: number | null,
  askPrice: number | null,
): {
  midPrice: number | null;
  spread: number | null;
  spreadPct: number | null;
  state: QuoteMarketState;
} {
  if (bidPrice === null || askPrice === null) {
    return { midPrice: null, spread: null, spreadPct: null, state: "missing" };
  }
  if (askPrice < bidPrice) {
    return { midPrice: null, spread: null, spreadPct: null, state: "inverted" };
  }
  const midPrice = (bidPrice + askPrice) / 2;
  const spread = askPrice - bidPrice;
  return {
    midPrice,
    spread,
    spreadPct: midPrice > 0 ? (spread / midPrice) * 100 : null,
    state: spread === 0 ? "locked" : "normal",
  };
}

function nearestStrike(
  strikes: readonly number[],
  underlyingPrice: number | null,
): number | null {
  if (underlyingPrice === null || strikes.length === 0) return null;
  return strikes.reduce((nearest, strike) => {
    const distance = Math.abs(strike - underlyingPrice);
    const nearestDistance = Math.abs(nearest - underlyingPrice);
    return distance < nearestDistance || (distance === nearestDistance && strike < nearest)
      ? strike
      : nearest;
  });
}

function withMoneyness(
  contract: OptionChainContract,
  underlyingPrice: number | null,
  atmStrike: number | null,
): OptionChainContract {
  let moneyness: OptionMoneyness = "UNKNOWN";
  if (underlyingPrice !== null && atmStrike !== null) {
    if (contract.strike === atmStrike) moneyness = "ATM";
    else if (contract.side === "CALL") {
      moneyness = contract.strike < underlyingPrice ? "ITM" : "OTM";
    } else {
      moneyness = contract.strike > underlyingPrice ? "ITM" : "OTM";
    }
  }
  return { ...contract, moneyness };
}

function summarizeChain(rows: readonly OptionChainRow[]): OptionChainSummary {
  const call = summarizeSide(rows.flatMap((row) => (row.call ? [row.call] : [])));
  const put = summarizeSide(rows.flatMap((row) => (row.put ? [row.put] : [])));
  return {
    call,
    put,
    callPutVolumeRatio: completeRatio(
      call.totalVolume,
      put.totalVolume,
      call.volumeComplete && put.volumeComplete,
    ),
    callPutOpenInterestRatio: completeRatio(
      call.totalOpenInterest,
      put.totalOpenInterest,
      call.openInterestComplete && put.openInterestComplete,
    ),
  };
}

function summarizeSide(contracts: readonly OptionChainContract[]): OptionSideSummary {
  const volumes = contracts.flatMap((contract) =>
    contract.volume === null ? [] : [contract.volume],
  );
  const openInterests = contracts.flatMap((contract) =>
    contract.openInterest === null ? [] : [contract.openInterest],
  );
  return {
    contractCount: contracts.length,
    totalVolume: safeSum(volumes),
    totalOpenInterest: safeSum(openInterests),
    volumeObservedContracts: volumes.length,
    openInterestObservedContracts: openInterests.length,
    volumeComplete: contracts.length > 0 && volumes.length === contracts.length,
    openInterestComplete:
      contracts.length > 0 && openInterests.length === contracts.length,
  };
}

function safeSum(values: readonly number[]): number | null {
  if (values.length === 0) return null;
  const total = values.reduce((sum, value) => sum + value, 0);
  return Number.isFinite(total) ? total : null;
}

function completeRatio(
  numerator: number | null,
  denominator: number | null,
  complete: boolean,
): number | null {
  if (!complete || numerator === null || denominator === null || denominator <= 0) {
    return null;
  }
  return numerator / denominator;
}

function optionSide(value: unknown): OptionSide | null {
  const normalized = text(value)?.toUpperCase();
  if (normalized === "CALL" || normalized === "C") return "CALL";
  if (normalized === "PUT" || normalized === "P") return "PUT";
  return null;
}

function normalizeCode(value: unknown): string | null {
  return text(value)?.toUpperCase() ?? null;
}

function text(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  return MISSING_TEXT.has(normalized.toUpperCase()) ? null : normalized;
}

function finiteNumber(value: unknown): number | null {
  if (typeof value === "boolean" || value === null || value === undefined) return null;
  if (typeof value === "string" && MISSING_TEXT.has(value.trim().toUpperCase())) {
    return null;
  }
  if (typeof value !== "number" && typeof value !== "string") return null;
  const normalized = Number(value);
  return Number.isFinite(normalized) ? normalized : null;
}

function nonNegativeNumber(value: unknown): number | null {
  const normalized = finiteNumber(value);
  return normalized !== null && normalized >= 0 ? normalized : null;
}

function positiveNumber(value: unknown): number | null {
  const normalized = finiteNumber(value);
  return normalized !== null && normalized > 0 ? normalized : null;
}

function nonNegativeInteger(value: unknown): number | null {
  const normalized = nonNegativeNumber(value);
  return normalized === null ? null : Math.trunc(normalized);
}
