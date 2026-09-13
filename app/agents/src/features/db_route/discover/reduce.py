"""Stage 5, agentic: the agent dilutes each fetched table to what the training set needs; code verifies and applies.

Code profiles the table (type, null rate, cardinality, samples, and for numeric columns the
correlation with the delay target when the table has one). The agent reads the profile and the
need and answers with the columns to keep, the columns to drop with a reason each, row filters
as SQL predicates with a reason each, and which column plays which required role. Code refuses a
proposal that drops a required role, names a column the table lacks, or writes a predicate DuckDB
cannot parse; one re-prompt with the objections, then the table is kept whole. What is applied is
measured: rows, columns and bytes before and after, per filter.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import llm

ROLES = {
    "events": {"timestamp": "when the stop happened", "station": "station name or id", "train": "train identity (type and number or line)",
               "target": "delay in minutes", "cancelled": "cancellation flag(s)"},
    "calendar": {"date_start": "start of the holiday", "date_end": "end of the holiday", "region": "subdivision code", "kind": "public or school"},
    "reference": {"station_id": "EVA or equivalent id", "region": "federal state"},
    "weather": {"timestamp": "hour", "station": "station key", "variable": "at least one weather variable"},
}


def profile_table(path: Path, target: str | None = "delay_in_min") -> dict:
    import duckdb  # noqa: PLC0415

    con = duckdb.connect()
    con.execute(f"CREATE VIEW t AS SELECT * FROM read_parquet('{path}')")
    rows = con.execute("SELECT count(*) FROM t").fetchone()[0]
    cols = con.execute("DESCRIBE t").fetchall()
    has_target = target and any(c[0] == target for c in cols)
    out = []
    for name, typ, *_ in cols:
        q = f'SELECT count(*) - count("{name}"), count(DISTINCT "{name}") FROM t'
        nulls, nd = con.execute(q).fetchone()
        sample = [str(x[0])[:40] for x in con.execute(f'SELECT "{name}" FROM t WHERE "{name}" IS NOT NULL LIMIT 3').fetchall()]
        entry = {"name": name, "type": typ, "null_rate": round(nulls / max(1, rows), 3), "n_distinct": int(nd), "sample": sample}
        if has_target and name != target and any(k in typ.upper() for k in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "BOOL")):
            try:
                corr = con.execute(f'SELECT corr(CAST("{name}" AS DOUBLE), CAST("{target}" AS DOUBLE)) FROM t').fetchone()[0]
                entry["corr_with_target"] = None if corr is None else round(float(corr), 3)
            except Exception:  # noqa: BLE001
                pass
        out.append(entry)
    return {"rows": int(rows), "bytes": path.stat().st_size, "columns": out}


def propose(source_id: str, kind: str, need: str, profile: dict, problems: list[str] | None = None) -> dict | None:
    roles = ROLES.get(kind, {})
    system = ("You reduce a data table to what a train-delay forecasting model needs. Reply with one JSON object: "
              '{"roles": {role: column or null}, "keep": [columns], "drop": [{"column": c, "reason": r}], '
              '"row_filters": [{"sql": "<DuckDB WHERE predicate>", "reason": r}], "reasoning": "..."}. '
              "Every column of the table must appear in keep or drop. Drop what carries no information for the "
              "need (constant, near-empty, duplicates of another column, identifiers with no reuse, free text the "
              "model cannot use) and say why. Filters remove rows that are noise for the need (e.g. transport modes "
              "outside scope, impossible values). Never drop a required role.")
    user = (f"Need: {need}\nSource: {source_id} ({kind}). Required roles: {json.dumps(roles)}\n"
            f"Profile: rows {profile['rows']}, bytes {profile['bytes']}\nColumns: {json.dumps(profile['columns'], ensure_ascii=False)[:6000]}\n"
            + (f"Your previous proposal was rejected: {problems}. Fix exactly these.\n" if problems else ""))
    return llm.chat(f"reduction {source_id}", system, user, max_tokens=900)


def normalise(proposal: dict, profile: dict) -> list[str]:
    """Resolve protocol slips the agent makes without changing its decisions; each one is recorded.

    A role given as "a or b" becomes a list; a filter written with a leading WHERE loses it; a
    column named in both keep and drop is dropped (the drop carries a reason, the keep does not);
    a column named in neither is kept. The substance stays the agent's, and the log says what
    code touched.
    """
    notes: list[str] = []
    have = [c["name"] for c in profile["columns"]]
    roles = proposal.get("roles") or {}
    for role, val in list(roles.items()):
        if isinstance(val, str) and (" or " in val or "," in val):
            parts = [x.strip() for x in val.replace(" or ", ",").split(",") if x.strip()]
            roles[role] = parts; notes.append(f"role {role}: '{val}' read as the columns {parts}")
    proposal["roles"] = roles
    for f in proposal.get("row_filters") or []:
        sql = (f.get("sql") or "").strip()
        if sql.lower().startswith("where "):
            f["sql"] = sql[6:].strip(); notes.append(f"filter: leading WHERE removed from '{sql[:40]}'")
    keep = [c for c in (proposal.get("keep") or []) if isinstance(c, str)]
    drop_cols = {d.get("column") for d in proposal.get("drop") or []}
    both = [c for c in keep if c in drop_cols]
    if both:
        keep = [c for c in keep if c not in drop_cols]; notes.append(f"named in both keep and drop, dropped (the drop carries the reason): {both}")
    missing = [c for c in have if c not in keep and c not in drop_cols]
    if missing:
        keep += missing; notes.append(f"named in neither keep nor drop, kept: {missing}")
    proposal["keep"] = keep
    proposal["normalisation"] = notes
    return notes


def verify(proposal: dict, kind: str, profile: dict, path: Path) -> list[str]:
    import duckdb  # noqa: PLC0415

    normalise(proposal, profile)
    have = {c["name"] for c in profile["columns"]}
    keep = proposal.get("keep") or []; drop = [d.get("column") for d in proposal.get("drop") or []]
    bad = [f"unknown column in keep: {c}" for c in keep if c not in have]
    bad += [f"unknown column in drop: {c}" for c in drop if c not in have]
    roles = proposal.get("roles") or {}
    for role in ROLES.get(kind, {}):
        col = roles.get(role)
        if role == "variable" and kind == "weather":
            if not any(c in keep for c in have - {roles.get("timestamp"), roles.get("station")}): bad.append("no weather variable kept")
            continue
        cols = col if isinstance(col, list) else [col]
        if not col: bad.append(f"required role {role} not mapped")
        for c in cols:
            if c not in have: bad.append(f"role {role} mapped to unknown column {c}")
            elif c not in keep: bad.append(f"required role {role} ({c}) was dropped")
    con = duckdb.connect(); con.execute(f"CREATE VIEW t AS SELECT * FROM read_parquet('{path}')")
    for f in proposal.get("row_filters") or []:
        sql = f.get("sql", "")
        if not sql or any(w in sql.lower() for w in (";", "drop ", "delete ", "update ", "insert ", "copy ", "attach")):
            bad.append(f"filter refused: {sql[:80]}"); continue
        try:
            con.execute(f"SELECT count(*) FROM t WHERE {sql}")
        except Exception as exc:  # noqa: BLE001
            bad.append(f"filter does not parse: {sql[:80]} ({str(exc)[:80]})")
    return bad


def apply(path: Path, proposal: dict, out: Path) -> dict:
    import duckdb  # noqa: PLC0415

    t0 = time.time(); con = duckdb.connect()
    con.execute(f"CREATE VIEW t AS SELECT * FROM read_parquet('{path}')")
    before = con.execute("SELECT count(*) FROM t").fetchone()[0]
    keep = ", ".join(f'"{c}"' for c in proposal["keep"])
    filters, where = [], []
    for f in proposal.get("row_filters") or []:
        n = con.execute(f"SELECT count(*) FROM t WHERE NOT ({f['sql']}) OR ({f['sql']}) IS NULL").fetchone()[0]
        filters.append({"sql": f["sql"], "reason": f.get("reason", ""), "rows_removed_alone": int(n)})
        where.append(f"({f['sql']})")
    out.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT {keep} FROM t WHERE {' AND '.join(where) if where else 'TRUE'}) TO '{out}' (FORMAT PARQUET)")
    after = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()[0]
    return {"path": str(out), "rows_before": int(before), "rows_after": int(after), "columns_before": len(proposal["keep"]) + len(proposal.get("drop") or []),
            "columns_after": len(proposal["keep"]), "bytes_before": path.stat().st_size, "bytes_after": out.stat().st_size,
            "filters": filters, "dropped": proposal.get("drop") or [], "roles": proposal.get("roles"), "reasoning": proposal.get("reasoning", ""),
            "normalisation": proposal.get("normalisation", []), "seconds": round(time.time() - t0, 1)}
