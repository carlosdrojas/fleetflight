// Shapes from ../../schemas (contract-v1). Every field is optional on purpose:
// the UI renders whatever arrives and must never crash on a missing field.

export type SnapVal = string | number | null;
export type Snapshot = { t_ms?: number } & Record<string, SnapVal | undefined>;

export interface Fixtureable {
  _fixture?: boolean;
  schema?: string;
}

export interface ModelRef { name?: string; version?: string; hash?: string }
export interface SutRef { id?: string; name?: string; version?: string }
export interface Bounds { max_depth?: number; max_injections?: number; horizon_ms?: number }

export interface Move {
  name?: string;
  args?: Record<string, string | number>;
  injected?: boolean;
  label?: string;
}

export interface TraceEvent { t_ms?: number; name?: string; detail?: string; injected?: boolean }

export interface TraceStep {
  step?: number;
  t_ms?: number;
  move?: Move | null;
  snapshot?: Snapshot;
  events?: TraceEvent[];
  violations?: string[];
}

export interface InvariantDef {
  id?: string;
  name?: string;
  description?: string;
  formula?: string;
  bound_ms?: number | null;
  timer_key?: string | null;
}

export interface Component {
  id?: string;
  name?: string;
  owner?: string;
  states?: string[];
  description?: string;
}

export interface Injectable {
  name?: string;
  description?: string;
  params?: { name?: string; values?: unknown }[];
}

export interface SnapshotKey { key?: string; label?: string; lane?: boolean }

export interface Describe extends Fixtureable {
  model?: ModelRef;
  sut?: SutRef;
  sut_versions?: string[];
  tick_ms?: number;
  components?: Component[];
  injectables?: Injectable[];
  invariants?: InvariantDef[];
  assumptions?: string[];
  bounds?: Bounds;
  constants?: Record<string, unknown>;
  snapshot_keys?: SnapshotKey[];
}

export interface RunRow {
  run_id?: string;
  created_at?: string;
  model?: string;
  sut?: string;
  verdict?: string;
  states?: number;
  wall_s?: number;
  counterexamples?: string[];
}

export interface RunList extends Fixtureable { runs?: RunRow[] }

export interface InvariantResult extends InvariantDef {
  result?: string;
  counterexample?: string | null;
  violated_at_ms?: number | null;
  violation_duration_ms?: number | null;
  depth?: number | null;
  worst_case_ms?: number | null;
}

export interface CheckReport extends Fixtureable {
  run_id?: string;
  created_at?: string;
  model?: ModelRef;
  sut?: SutRef;
  bounds?: Bounds;
  strategy?: string;
  assumptions?: string[];
  stats?: {
    states?: number;
    transitions?: number;
    max_depth_reached?: number;
    wall_s?: number;
    states_per_s?: number;
    new_states_per_depth?: number[];
    complete?: boolean;
  };
  invariants?: InvariantResult[];
  counterexample_files?: string[];
  notes?: string[];
  verdict?: string;
}

export interface ScriptedMove { tick_index?: number; t_ms?: number; move?: Move }

export interface Counterexample extends Fixtureable {
  id?: string;
  model?: ModelRef;
  sut?: SutRef;
  invariant?: InvariantDef;
  violated_at_ms?: number;
  violation_duration_ms?: number | null;
  bounds?: Bounds;
  search?: {
    strategy?: string;
    minimal?: boolean;
    depth?: number;
    states_explored?: number;
    transitions?: number;
    wall_s?: number;
  };
  assumptions?: string[];
  trace?: TraceStep[];
  moves?: ScriptedMove[];
  ticks?: number;
  trace_hash?: string;
  explanation?: string;
  replay?: { command?: string };
}

export interface Window { start_ms?: number; end_ms?: number | null; duration_ms?: number; open?: boolean }

export interface ReplayStep extends TraceStep { match?: boolean | null; diff?: string[] }

export interface ReplayResult extends Fixtureable {
  /** Site mode: served from the exported run because the live replay function was unavailable. */
  _snapshot?: boolean;
  counterexample?: string;
  model?: ModelRef;
  sut?: SutRef;
  cex_sut?: string;
  same_sut?: boolean;
  horizon_ms?: number;
  steps?: ReplayStep[];
  compared_steps?: number;
  matched_steps?: number;
  first_divergence?: number | null;
  trace_hash?: string;
  expected_trace_hash?: string;
  hash_match?: boolean;
  full_trace_hash?: string;
  skipped_moves?: { tick_index?: number; move?: Move; reason?: string }[];
  invariants?: { id?: string; name?: string; result?: string; first_violation_ms?: number | null; max_window?: Window | null }[];
  violation_window_ms?: (Window & { invariant?: string; bound_ms?: number; over_budget_ms?: number }) | null;
  verdict?: string;
}

// Not in contract-v1: see status/04-ui.md CONTRACT REQUEST.
export interface RegressList extends Fixtureable {
  tests?: { cex?: string; path?: string; invariant?: string; sut?: string }[];
}
export interface RegressSource extends Fixtureable { cex?: string; path?: string; source?: string }

/** Site mode: provenance of the exported run (scripts/export_site.py). */
export interface SiteMeta {
  checked_at?: string;
  exported_at?: string;
  commit?: string;
  source?: string;
  counterexamples?: string[];
  versions?: string[];
}
