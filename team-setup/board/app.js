// hack-os board — client. No framework, no build step. Polls /api/state,
// /api/docs, /api/focus and renders both view modes from the same data.
(function () {
  "use strict";

  var POLL_MS = 6000;
  var state = null;
  var docs = null;
  var focus = null;
  var countdownTimer = null;

  // ---------------------------------------------------------------------
  // fetch helpers
  // ---------------------------------------------------------------------

  function getJSON(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error("Dashboard state unavailable; local files retained for review");
      return r.json();
    });
  }

  function postJSON(url, body, revision) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Hackos-Token": state.csrf_token,
        "If-Match": revision || state.revision },
      body: JSON.stringify(body || {}),
    }).then(function (r) { return r.json(); }).then(function (result) {
      if (!result.ok) throw new Error(result.error || "Save failed");
      document.getElementById("save-status").textContent = result.warning || "Saved locally. Commit, push and integrate to share with teammates.";
      return result;
    }).catch(function (error) {
      document.getElementById("save-status").textContent = error.message + " Your input has not been cleared. Review the latest state before retrying.";
      document.getElementById("failed-draft").value = JSON.stringify(body, null, 2);
      document.getElementById("draft-recovery").hidden = false;
      return { ok: false, error: error.message };
    });
  }

  function refresh() {
    return Promise.all([getJSON("/api/state"), getJSON("/api/docs"), getJSON("/api/focus")])
      .then(function (results) {
        if (results.some(function (r) { return r.revision !== results[0].revision; })) return;
        state = results[0];
        docs = results[1];
        focus = results[2].focus;
        renderAll();
      })
      .catch(function (e) {
        document.getElementById("freshness").textContent = "Dashboard disconnected or state unreadable. Displayed data is stale. " + e.message;
      });
  }

  // ---------------------------------------------------------------------
  // small utils
  // ---------------------------------------------------------------------

  function el(tag, attrs, children) {
    var e = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      if (k === "class") e.className = attrs[k];
      else if (k === "text") e.textContent = attrs[k];
      else e.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) {
      if (c) e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return e;
  }

  function fmtDuration(seconds) {
    if (seconds === null || seconds === undefined || isNaN(seconds)) return "--:--:--";
    var neg = seconds < 0;
    seconds = Math.abs(Math.floor(seconds));
    var h = Math.floor(seconds / 3600);
    var m = Math.floor((seconds % 3600) / 60);
    var s = seconds % 60;
    var pad = function (n) { return String(n).padStart(2, "0"); };
    return (neg ? "-" : "") + pad(h) + ":" + pad(m) + ":" + pad(s);
  }

  function setEmpty(container, message) {
    container.appendChild(el("div", { class: "empty-state", text: message }));
  }

  // ---------------------------------------------------------------------
  // countdown hero — ticks client-side every second between polls
  // ---------------------------------------------------------------------

  function renderCountdown() {
    var label = document.getElementById("hero-label");
    var big = document.getElementById("hero-countdown");
    var sub = document.getElementById("hero-sub");

    if (!state || state.event_is_blank) {
      label.textContent = state && state.example_mode ? "EXAMPLES INACTIVE" : "NO EVENT CONFIGURED";
      big.textContent = "Not started";
      sub.textContent = "run team-setup/scripts/new-event.sh to initialize a real event; no example is a requirement";
      return;
    }

    var cd = state.pipeline.countdown || {};
    if (cd.seconds_to_submit_target === null || cd.seconds_to_submit_target === undefined) {
      label.textContent = "SUBMIT TARGET IN";
      big.textContent = "--:--:--";
      sub.textContent = state.pipeline.warning || "build_starts / submission_deadline not set yet";
      return;
    }

    var secs = cd.seconds_to_submit_target;
    label.textContent = secs < 0 ? "SUBMIT TARGET PASSED BY" : "SUBMIT TARGET IN";
    big.textContent = fmtDuration(secs);
    sub.textContent = "real deadline: " + (cd.real_deadline || "--") +
      "  (" + fmtDuration(cd.seconds_to_real_deadline) + " remaining)";
  }

  function tickCountdown() {
    if (!state || !state.pipeline || !state.pipeline.countdown) return;
    var cd = state.pipeline.countdown;
    if (cd.seconds_to_submit_target !== null && cd.seconds_to_submit_target !== undefined) {
      cd.seconds_to_submit_target -= 1;
    }
    if (cd.seconds_to_real_deadline !== null && cd.seconds_to_real_deadline !== undefined) {
      cd.seconds_to_real_deadline -= 1;
    }
    renderCountdown();
  }

  // ---------------------------------------------------------------------
  // stage strip
  // ---------------------------------------------------------------------

  function renderStageStrip() {
    var strip = document.getElementById("stage-strip");
    strip.innerHTML = "";
    if (!state || !state.pipeline) return;
    state.pipeline.stages.forEach(function (s) {
      var chip = el("span", { class: "stage-chip status-" + s.status, text: s.name });
      if (s.id === state.pipeline.current_stage) {
        chip.style.borderWidth = "2px";
      }
      strip.appendChild(chip);
    });
  }

  // ---------------------------------------------------------------------
  // TECHNICAL VIEW
  // ---------------------------------------------------------------------

  function renderTechStage() {
    var c = document.getElementById("tech-stage");
    c.innerHTML = "";
    if (!state || !state.pipeline) return setEmpty(c, "no pipeline data");
    var cur = state.pipeline.stages.find(function (s) { return s.id === state.pipeline.current_stage; });
    if (!cur) return setEmpty(c, "Initialize the event, then capture the reveals.");
    c.appendChild(el("div", { class: "row" }, [el("span", { text: "Stage" }), el("span", { text: cur.name })]));
    c.appendChild(el("div", { class: "row" }, [el("span", { text: "Owner role" }), el("span", { text: cur.owner || "-" })]));
    c.appendChild(el("div", { class: "row" }, [el("span", { text: "Exit condition" }), el("span", { text: cur.exit_condition || "-" })]));
    var idx = state.pipeline.stages.indexOf(cur);
    var next = state.pipeline.stages[idx + 1];
    if (next) {
      c.appendChild(el("div", { class: "row" }, [el("span", { text: "Next gate" }), el("span", { text: next.name + " — " + (next.owner || "") })]));
    }
    var advanceBtn = el("button", { text: "advance stage" });
    advanceBtn.addEventListener("click", function () {
      postJSON("/api/stage", {}).then(refresh);
    });
    c.appendChild(advanceBtn);
  }

  function renderTechDrift() {
    var c = document.getElementById("tech-drift");
    c.innerHTML = "";
    if (!state) return setEmpty(c, "no data");
    if (state.contract_drift === null) return setEmpty(c, "No real freeze baseline recorded yet.");
    var tag = state.contract_drift
      ? el("span", { class: "tag blocked", text: "DRIFTED since freeze" })
      : el("span", { class: "tag ok", text: "matches freeze" });
    c.appendChild(tag);
  }

  function renderTechSleep() {
    var c = document.getElementById("tech-sleep");
    c.innerHTML = "";
    if (!state || !state.sleep_rota || !state.sleep_rota.length) return setEmpty(c, "no sleep rota configured");
    state.sleep_rota.forEach(function (shift) {
      var active = state.current_sleep_shift && state.current_sleep_shift.shift === shift.shift;
      var row = el("div", { class: "row" }, [
        el("span", { text: "Shift " + shift.shift + (active ? " (active)" : "") }),
        el("span", { text: (shift.people || []).join(", ") + " — " + (shift.window || "?") }),
      ]);
      if (active) row.style.color = "var(--ok)";
      c.appendChild(row);
    });
  }

  function renderTechSmoke() {
    var c = document.getElementById("tech-smoke");
    c.innerHTML = "";
    if (!state) return setEmpty(c, "no data");
    var smoke = state.smoke_last;
    c.appendChild(el("div", { class: "row" }, [
      el("span", { text: "Last smoke test" }),
      smoke
        ? el("span", { class: "tag " + (smoke.ok ? "ok" : "blocked"), text: (smoke.ok ? "PASS" : "FAIL") + " @ " + (smoke.timestamp || "?") })
        : el("span", { class: "empty-state", text: "not run yet" }),
    ]));
    var tags = state.snapshot_tags || [];
    c.appendChild(el("div", { class: "row" }, [
      el("span", { text: "Last snapshot" }),
      el("span", { text: tags.length ? tags[0] : "none yet — run scripts/snapshot.sh" }),
    ]));
  }

  function renderTechCommits() {
    var c = document.getElementById("tech-commits");
    c.innerHTML = "";
    if (!state || !state.commits || !state.commits.length) return setEmpty(c, "no commits logged yet");
    var byPerson = {};
    state.commits.forEach(function (commit) {
      var author = commit.author || "unknown";
      (byPerson[author] = byPerson[author] || []).push(commit);
    });
    Object.keys(byPerson).forEach(function (author) {
      var commits = byPerson[author].slice(0, 5);
      var box = el("div", { style: "margin-bottom:8px;" });
      box.appendChild(el("div", { text: author + " (" + byPerson[author].length + ")", style: "color:var(--text-muted);font-size:11px;margin-bottom:3px;" }));
      commits.forEach(function (commit) {
        box.appendChild(el("div", { class: "row" }, [
          el("span", { text: (commit.t_offset || "") + " " + (commit.message || "") }),
          el("span", { text: (commit.sha || "").slice(0, 7) }),
        ]));
      });
      c.appendChild(box);
    });
  }

  function renderTechFilesHour() {
    var c = document.getElementById("tech-files-hour");
    c.innerHTML = "";
    if (!state || !state.files_last_hour || !state.files_last_hour.length) {
      return setEmpty(c, "no files touched in the last hour");
    }
    state.files_last_hour.forEach(function (commit) {
      c.appendChild(el("div", { class: "row" }, [
        el("span", { text: commit.author || "unknown" }),
        el("span", { text: (commit.files || []).join(", ") }),
      ]));
    });
  }

  function renderTechFocus() {
    var c = document.getElementById("tech-focus");
    c.innerHTML = "";
    if (!focus || !focus.length) return setEmpty(c, "No recorded commits yet. This view does not infer current work.");
    focus.forEach(function (f) {
      var wrap = el("div", { class: "focus-entry" });
      wrap.appendChild(el("strong", { text: f.person + (f.unmapped_author ? " (Git author not mapped to roster)" : "") }));
      (f.commits || []).forEach(function (commit) {
        wrap.appendChild(el("div", { class: "focus-files", text: commit.timestamp + " · " + commit.sha.slice(0, 8) + " · " + commit.message }));
        wrap.appendChild(el("div", { class: "empty-state", text: commit.files.join(", ") }));
      });
      if (!f.commits.length) setEmpty(wrap, "No matching Git author. Optional team.json git_names aliases map existing author names.");
      c.appendChild(wrap);
    });
  }

  var DOC_LABELS = {
    challenge: "challenge.md",
    demo_script: "demo-script.md",
    not_building: "not-building.md",
    contract: "contract.md",
    partner_notes: "partner-notes.md",
  };

  function renderTechDocs() {
    var c = document.getElementById("tech-docs");
    c.innerHTML = "";
    if (!docs) return setEmpty(c, "no docs loaded");
    Object.keys(DOC_LABELS).forEach(function (key) {
      var d = docs[key];
      var wrap = el("div", { style: "margin-bottom:10px;" });
      wrap.appendChild(el("div", { text: DOC_LABELS[key], style: "color:var(--text-muted);font-size:11px;margin-bottom:3px;" }));
      if (!d || d.not_written_yet) {
        wrap.appendChild(el("div", { class: "empty-state", text: "not written yet" }));
      } else {
        wrap.appendChild(el("div", { class: "mono-block", text: d.content }));
      }
      c.appendChild(wrap);
    });
  }

  // ---- tiny offline mermaid-subset renderer (graph LR/TD, A[Label] --> B[Label]) ----

  function parseMermaid(src) {
    var nodes = {};
    var edges = [];
    var order = [];
    var lines = src.split("\n");
    var nodeRe = /([A-Za-z0-9_]+)(\[([^\]]*)\])?/;
    lines.forEach(function (line) {
      line = line.trim();
      if (!line || line.indexOf("%%") === 0 || /^graph\s/i.test(line)) return;
      var arrowMatch = line.match(/-->(\|([^|]*)\|)?/);
      if (!arrowMatch) return;
      var parts = line.split(/-->(?:\|[^|]*\|)?/);
      if (parts.length < 2) return;
      var leftMatch = parts[0].trim().match(nodeRe);
      var rightMatch = parts[1].trim().match(nodeRe);
      if (!leftMatch || !rightMatch) return;
      var a = leftMatch[1], aLabel = leftMatch[3] || a;
      var b = rightMatch[1], bLabel = rightMatch[3] || b;
      if (!nodes[a]) { nodes[a] = aLabel; order.push(a); }
      if (!nodes[b]) { nodes[b] = bLabel; order.push(b); }
      edges.push({ from: a, to: b, label: arrowMatch[2] || "" });
    });
    return { nodes: nodes, order: order, edges: edges };
  }

  function renderMermaidSVG(src) {
    var graph = parseMermaid(src);
    if (!graph.order.length) return null;
    var boxW = 170, boxH = 46, gapX = 60, padding = 20;
    var x = padding, y = padding;
    var positions = {};
    graph.order.forEach(function (id) {
      positions[id] = { x: x, y: y };
      x += boxW + gapX;
    });
    var width = x + padding;
    var height = boxH + padding * 2 + 20;

    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    svg.setAttribute("class", "diagram-svg");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "architecture diagram");

    function svgEl(tag, attrs) {
      var e = document.createElementNS("http://www.w3.org/2000/svg", tag);
      Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
      return e;
    }

    var css = getComputedStyle(document.documentElement);
    var borderColor = css.getPropertyValue("--border").trim() || "#888";
    var textColor = css.getPropertyValue("--text").trim() || "#eee";
    var panelColor = css.getPropertyValue("--bg-panel-2").trim() || "#222";

    graph.edges.forEach(function (edge) {
      var p1 = positions[edge.from], p2 = positions[edge.to];
      if (!p1 || !p2) return;
      var x1 = p1.x + boxW, y1 = p1.y + boxH / 2;
      var x2 = p2.x, y2 = p2.y + boxH / 2;
      svg.appendChild(svgEl("line", { x1: x1, y1: y1, x2: x2, y2: y2, stroke: borderColor, "stroke-width": 1.5 }));
      if (edge.label) {
        svg.appendChild(svgEl("text", { x: (x1 + x2) / 2, y: y1 - 6, fill: textColor, "font-size": 10, "text-anchor": "middle" })).textContent = edge.label;
      }
    });

    graph.order.forEach(function (id) {
      var p = positions[id];
      svg.appendChild(svgEl("rect", { x: p.x, y: p.y, width: boxW, height: boxH, rx: 4, fill: panelColor, stroke: borderColor }));
      var text = svgEl("text", { x: p.x + boxW / 2, y: p.y + boxH / 2 + 4, fill: textColor, "font-size": 11, "text-anchor": "middle", "font-family": "var(--mono)" });
      text.textContent = graph.nodes[id];
      svg.appendChild(text);
    });

    return svg;
  }

  function renderTechArchitecture() {
    var c = document.getElementById("tech-architecture");
    c.innerHTML = "";
    if (!docs || !docs.architecture || docs.architecture.not_written_yet) {
      return setEmpty(c, "not written yet");
    }
    var svg = renderMermaidSVG(docs.architecture.content);
    if (svg) {
      c.appendChild(svg);
    } else {
      c.appendChild(el("div", { class: "mono-block", text: docs.architecture.content }));
    }
  }

  function renderTechnical() {
    renderTechStage();
    renderTechDrift();
    renderTechSleep();
    renderTechSmoke();
    renderTechCommits();
    renderTechFilesHour();
    renderTechFocus();
    renderTechDocs();
    renderTechArchitecture();
  }

  // ---------------------------------------------------------------------
  // PM VIEW
  // ---------------------------------------------------------------------

  var STAGE_LABELS = {};

  function renderPmMilestones() {
    var c = document.getElementById("pm-milestones");
    c.innerHTML = "";
    if (!state || !state.pipeline) return setEmpty(c, "no pipeline data");
    state.pipeline.stages.forEach(function (s) {
      STAGE_LABELS[s.id] = s.name;
      var statusLabel = { done: "done", in_progress: "in progress", pending: "not started" }[s.status] || s.status;
      var row = el("div", { class: "row" }, [
        el("span", { text: s.name }),
        el("span", { text: statusLabel }),
      ]);
      c.appendChild(row);
      c.appendChild(el("div", { class: "empty-state", text: s.exit_condition, style: "margin:-4px 0 6px;" }));
    });
  }

  function renderPmMvp() {
    var c = document.getElementById("pm-mvp");
    c.innerHTML = "";
    if (!state || !state.tasks || !state.tasks.length) return setEmpty(c, "no tasks yet");
    var groups = {};
    state.tasks.forEach(function (t) {
      var tag = t.mvp || "untagged";
      (groups[tag] = groups[tag] || []).push(t);
    });
    Object.keys(groups).sort().forEach(function (tag) {
      var tasks = groups[tag];
      var done = tasks.filter(function (t) { return t.status === "demo-ready"; }).length;
      var pct = Math.round((done / tasks.length) * 100);
      var band = el("div", { class: "mvp-band" });
      band.appendChild(el("div", { class: "row", style: "border:none;padding:0 0 4px;" }, [
        el("span", { text: tag }),
        el("span", { text: done + "/" + tasks.length }),
      ]));
      var track = el("div", { class: "mvp-bar-track" });
      track.appendChild(el("div", { class: "mvp-bar-fill", style: "width:" + pct + "%;" }));
      band.appendChild(track);
      band.appendChild(el("div", { class: "empty-state", text: done === tasks.length
        ? (state.smoke_current ? "Tasks complete; current clean-revision smoke passed." : "Tasks complete; integrated readiness unverified. Run the happy-path smoke.")
        : "Task status only; not proof of an integrated demo." }));
      c.appendChild(band);
    });
  }

  function renderPmOwners() {
    var c = document.getElementById("pm-owners");
    c.innerHTML = "";
    if (!state || !state.owners_raw) return setEmpty(c, "owners.md not readable");
    var lines = state.owners_raw.split("## Per-person")[0].split("\n").filter(function (l) {
      return l.trim().startsWith("|") && !l.includes("---") && !/^\|\s*(Directory|Feature|Role|Person)\s*\|/.test(l) && !l.includes("app/shared");
    });
    lines.forEach(function (line) {
      var cells = line.trim().replace(/^\||\|$/g, "").split("|").map(function (c) { return c.trim(); });
      if (cells.length < 2) return;
      var row = el("button", { class: "row", type: "button", "aria-label": "Reassign " + cells[0] }, [
        el("span", { text: cells[0] }),
        el("span", { text: cells[1] }),
      ]);
      row.addEventListener("click", function () {
        var newOwner = prompt("Reassign owner for '" + cells[0] + "' (currently " + cells[1] + "):", cells[1]);
        if (newOwner && newOwner.trim() && newOwner.trim() !== cells[1]) {
          postJSON("/api/owners", { key: cells[0], owner: newOwner.trim() }).then(refresh);
        }
      });
      row.style.cursor = "pointer";
      row.title = "click to reassign";
      c.appendChild(row);
    });
  }

  var TASK_COLUMNS = ["backlog", "building", "integrating", "demo-ready"];
  var TASK_COLUMN_LABELS = { backlog: "Backlog", building: "Building", integrating: "Integrating", "demo-ready": "Demo-ready" };

  function taskById(id) {
    return (state.tasks || []).find(function (t) { return t.id === id; });
  }

  function renderPmTasks() {
    var c = document.getElementById("pm-tasks");
    c.innerHTML = "";
    if (!state || !state.tasks) return setEmpty(c, "no tasks yet");
    if (!state.tasks.length) return setEmpty(c, "no tasks yet — add one below");

    var cols = el("div", { class: "board-columns" });
    TASK_COLUMNS.forEach(function (status) {
      var col = el("div", { class: "board-col" });
      col.appendChild(el("h3", { text: TASK_COLUMN_LABELS[status] }));
      state.tasks.filter(function (t) { return t.status === status; }).forEach(function (t) {
        var blockedOn = (t.depends_on || []).filter(function (id) {
          var dep = taskById(id);
          return !dep || dep.status !== "demo-ready";
        });
        var overdue = t.status !== "demo-ready" && t.resolved_target && new Date() > new Date(t.resolved_target);
        var card = el("div", { class: "task-card" + (blockedOn.length ? " blocked" : "") + (overdue ? " overdue" : "") });
        card.appendChild(el("div", { text: t.title }));
        var ownerLine = t.owner || "unassigned";
        if (t.sub_owners && t.sub_owners.length) ownerLine += " + " + t.sub_owners.join(", ");
        card.appendChild(el("div", { class: "owners", text: ownerLine + (t.target_time ? " — " + t.target_time : "") }));
        if (blockedOn.length) {
          card.appendChild(el("div", { class: "blocked-note", text: "blocked on: " + blockedOn.join(", ") }));
        }
        if (overdue) {
          card.appendChild(el("div", { class: "overdue-note", text: "overdue against target_time" }));
        }
        var actions = el("div", { style: "margin-top:6px;display:flex;gap:4px;flex-wrap:wrap;" });
        TASK_COLUMNS.forEach(function (s) {
          if (s === status) return;
          var b = el("button", { text: "-> " + TASK_COLUMN_LABELS[s], style: "font-size:10px;padding:2px 6px;" });
          b.addEventListener("click", function () { moveTask(t.id, s); });
          actions.appendChild(b);
        });
        var del = el("button", { text: "delete", style: "font-size:10px;padding:2px 6px;" });
        del.addEventListener("click", function () { deleteTask(t.id); });
        actions.appendChild(del);
        card.appendChild(actions);
        col.appendChild(card);
      });
      cols.appendChild(col);
    });
    c.appendChild(cols);
  }

  function isOverdueTargetTime(targetTime) {
    if (!targetTime || !state || !state.pipeline) return false;
    var m = /T\+(\d+)%/.exec(targetTime);
    if (!m || !state.event || !state.event.build_starts || !state.event.submission_deadline) return false;
    try {
      var start = new Date(state.event.build_starts);
      var end = new Date(state.pipeline.countdown.submit_target);
      var window = end - start;
      var targetDate = new Date(start.getTime() + window * (parseInt(m[1], 10) / 100));
      return new Date() > targetDate;
    } catch (e) { return false; }
  }

  function moveTask(id, newStatus) {
    var tasks = state.tasks.map(function (t) { return t.id === id ? Object.assign({}, t, { status: newStatus }) : t; });
    postJSON("/api/tasks", { tasks: tasks }).then(refresh);
  }

  function deleteTask(id) {
    if (!confirm("Delete task " + id + "? Dependent tasks will show it as missing.")) return;
    var tasks = state.tasks.filter(function (t) { return t.id !== id; });
    postJSON("/api/tasks", { tasks: tasks }).then(refresh);
  }

  function nextTaskId() {
    return "t-" + crypto.randomUUID().replace(/-/g, "");
  }

  function renderPmIdeas() {
    var c = document.getElementById("pm-ideas");
    c.innerHTML = "";
    if (!state || !state.ideas || !state.ideas.length) return setEmpty(c, "no ideas raised yet");
    ["raised", "exploring", "adopted", "discarded"].forEach(function (status) {
      var items = state.ideas.filter(function (i) { return i.status === status; });
      if (!items.length) return;
      c.appendChild(el("div", { text: status.toUpperCase(), style: "color:var(--text-dim);font-size:11px;margin:8px 0 2px;" }));
      items.forEach(function (i) {
        var row = el("div", { class: "idea-line" }, [
          el("span", { text: "[" + i.timestamp + "] " + i.idea + " — " + i.who }),
        ]);
        if (status !== "adopted" && status !== "discarded") {
          var actions = el("div", { style: "margin-top:3px;display:flex;gap:4px;" });
          ["exploring", "adopted", "discarded"].forEach(function (s) {
            if (s === status) return;
            var b = el("button", { text: s, style: "font-size:10px;padding:2px 6px;" });
            b.addEventListener("click", function () {
              if (s === "adopted") {
                postJSON("/api/decision", {
                  decision: "adopt idea: " + i.idea,
                  who: prompt("Who is deciding to adopt this idea?") || "",
                  reason: "promoted from ideas board",
                  promotes_idea: i.id,
                }).then(refresh);
              } else {
                postJSON("/api/ideas/status", { id: i.id, status: s }).then(refresh);
              }
            });
            actions.appendChild(b);
          });
          row.appendChild(actions);
        }
        c.appendChild(row);
      });
    });
  }

  var VIABILITY_TAG_CLASS = { untested: "", feasible: "ok", "not-viable": "blocked", implemented: "ok" };

  function renderPmResearch() {
    var c = document.getElementById("pm-research");
    c.innerHTML = "";
    if (!state || !state.research || !state.research.length) return setEmpty(c, "no research logged yet");
    state.research.forEach(function (r) {
      var wrap = el("div", { class: "focus-entry" });
      var head = el("div", {}, [
        el("strong", { text: r.topic || r.id }),
        el("span", { class: "tag " + (VIABILITY_TAG_CLASS[r.viability] || ""), text: " " + r.viability }),
        r.override ? el("span", { class: "tag warn", text: "manually overridden" }) : null,
      ]);
      wrap.appendChild(head);
      wrap.appendChild(el("div", { class: "focus-files", text: r.viability_reasoning || "" }));
      if (r.assessment) wrap.appendChild(el("div", { class: "empty-state", text: "Advisory AI assessment (not verified): " + r.assessment.viability + ". " + r.assessment.viability_reasoning }));
      if (r.evidence) wrap.appendChild(el("div", { class: "focus-files", text: "Evidence: " + r.evidence + " — confirmed by " + r.confirmed_by }));
      var correct = el("button", { text: "Record human assessment" });
      correct.addEventListener("click", function () {
        var viability = prompt("untested / feasible / not-viable / implemented", r.viability);
        if (!viability) return;
        var who = prompt("Who confirmed this assessment?");
        if (!who) return;
        var evidence = prompt("Evidence: commit, measured result, or smoke result (required for implemented)", r.evidence || "");
        if (evidence === null) return;
        postJSON("/api/research/override", { id: r.id, viability: viability, confirmed_by: who, evidence: evidence,
          viability_reasoning: "Human assessment; see recorded evidence" }).then(refresh);
      });
      wrap.appendChild(correct);
      wrap.appendChild(el("div", { class: "empty-state", text: r.summary, style: "margin-top:4px;" }));
      if (r.linked_idea) wrap.appendChild(el("div", { class: "focus-files", text: "linked idea: " + r.linked_idea }));
      if (r.spawned_idea) wrap.appendChild(el("div", { class: "focus-files", text: "spawned idea: " + r.spawned_idea }));
      c.appendChild(wrap);
    });
  }

  function renderPmDecisions() {
    var c = document.getElementById("pm-decisions");
    c.innerHTML = "";
    if (!state || !state.decisions || !state.decisions.length) return setEmpty(c, "no decisions logged yet");
    state.decisions.slice().reverse().forEach(function (d) {
      var superseded = !!d.superseded_by;
      var line = el("div", { class: "decision-line" + (superseded ? " superseded" : "") });
      line.id = d.id;
      line.appendChild(el("div", { text: "[" + d.timestamp + "] " + d.decision + " — " + d.who + " — " + d.reason }));
      line.appendChild(el("div", { class: "empty-state", text: "ID: " + d.id }));
      if (d.promotes_idea) line.appendChild(el("div", { class: "supersede-note", text: "promotes " + d.promotes_idea }));
      if (d.link_warning) line.appendChild(el("div", { class: "supersede-note", text: d.link_warning }));
      if (superseded) line.appendChild(el("div", { class: "supersede-note", text: "superseded by [" + d.superseded_by + "]" }));
      if (d.supersedes) line.appendChild(el("div", { class: "supersede-note", text: "supersedes [" + d.supersedes + "]" }));
      c.appendChild(line);
    });
  }

  function renderPM() {
    renderPmMilestones();
    renderPmMvp();
    renderPmOwners();
    renderPmTasks();
    renderPmIdeas();
    renderPmResearch();
    renderPmDecisions();
  }

  // ---------------------------------------------------------------------
  // render all
  // ---------------------------------------------------------------------

  function renderAll() {
    var banner = document.getElementById("empty-banner");
    banner.hidden = !(state && state.event_is_blank);
    var f = state.freshness || {};
    document.getElementById("freshness").textContent = "Local snapshot: " + (f.branch || "detached") + " @ " + (f.head || "uncommitted").slice(0, 10) +
      ". Coordination: " + f.coordination_branch + ", maintainer " + f.coordination_maintainer +
      ". Last successful remote check: " + ((f.remote_check || {}).last_success_at || "none recorded") +
      ((f.remote_check || {}).ok === false ? " (latest attempt failed)" : "") +
      ". Fetch metadata: " + (f.last_fetch_at || "none") + " (not proof of current remote state). " +
      (f.upstream ? f.ahead + " ahead / " + f.behind + " behind cached " + f.upstream + ". " : "No upstream. ") +
      f.local_changes.length + " uncommitted coordination file(s). Remote freshness unknown until explicitly checked.";
    document.getElementById("local-changes").textContent = f.local_changes.join("\n");
    renderCountdown();
    renderStageStrip();
    renderTechnical();
    renderPM();
  }

  // ---------------------------------------------------------------------
  // view toggle
  // ---------------------------------------------------------------------

  function setMode(mode) {
    var technical = document.getElementById("view-technical");
    var pm = document.getElementById("view-pm");
    var btnT = document.getElementById("btn-technical");
    var btnP = document.getElementById("btn-pm");
    technical.hidden = mode !== "technical";
    pm.hidden = mode !== "pm";
    btnT.setAttribute("aria-pressed", String(mode === "technical"));
    btnP.setAttribute("aria-pressed", String(mode === "pm"));
    try { localStorage.setItem("hackos-board-mode", mode); } catch (e) {}
  }

  document.getElementById("btn-technical").addEventListener("click", function () { setMode("technical"); });
  document.getElementById("btn-pm").addEventListener("click", function () { setMode("pm"); });

  var savedMode = "technical";
  try { savedMode = localStorage.getItem("hackos-board-mode") || "technical"; } catch (e) {}
  setMode(savedMode);

  // ---------------------------------------------------------------------
  // PM forms
  // ---------------------------------------------------------------------

  document.getElementById("pm-task-add-btn").addEventListener("click", function () {
    document.getElementById("pm-task-form").hidden = false;
  });
  document.getElementById("pm-task-cancel").addEventListener("click", function () {
    document.getElementById("pm-task-form").hidden = true;
  });
  document.getElementById("pm-task-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var f = e.target;
    var newTask = {
      id: nextTaskId(),
      title: f.elements.namedItem("title").value.trim(),
      status: "backlog",
      owner: f.owner.value.trim() || null,
      sub_owners: f.sub_owners.value.split(",").map(function (s) { return s.trim(); }).filter(Boolean),
      depends_on: f.depends_on.value.split(",").map(function (s) { return s.trim(); }).filter(Boolean),
      target_time: f.target_time.value.trim() || null,
      mvp: f.mvp.value.trim() || null,
      stage: state.pipeline.current_stage,
      notes: "",
    };
    var tasks = (state.tasks || []).concat([newTask]);
    postJSON("/api/tasks", { tasks: tasks }, f.dataset.revision).then(function (result) {
      if (!result.ok) return;
      delete f.dataset.revision;
      f.reset();
      f.closest("form").hidden = true;
      refresh();
    });
  });

  document.getElementById("pm-idea-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var f = e.target;
    postJSON("/api/ideas", { idea: f.idea.value.trim(), who: f.who.value.trim() }, f.dataset.revision).then(function (result) {
      if (!result.ok) return;
      delete f.dataset.revision;
      f.reset();
      refresh();
    });
  });

  document.getElementById("pm-research-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var f = e.target;
    postJSON("/api/research", { logged_by: f.logged_by.value.trim(), summary: f.summary.value,
      assess: f.assess.checked }, f.dataset.revision).then(function (result) {
      if (!result.ok) return;
      delete f.dataset.revision;
      f.reset();
      refresh();
    });
  });

  document.getElementById("pm-decision-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var f = e.target;
    postJSON("/api/decision", {
      decision: f.decision.value.trim(),
      who: f.who.value.trim(),
      reason: f.reason.value.trim(),
      supersedes: f.supersedes.value.trim() || undefined,
    }, f.dataset.revision).then(function (result) {
      if (!result.ok) return;
      delete f.dataset.revision;
      f.reset();
      refresh();
    });
  });

  document.getElementById("pm-notes-submit").addEventListener("click", function () {
    var text = document.getElementById("pm-notes-text").value;
    if (!text.trim()) return;
    var preview = document.getElementById("pm-notes-preview");
    preview.innerHTML = "";
    preview.appendChild(el("div", { class: "empty-state", text: "structuring..." }));
    postJSON("/api/notes", { text: text, structure: document.getElementById("notes-ai").checked }).then(function (result) {
      preview.innerHTML = "";
      if (!result.ok) return;
      if (result.warning) {
        preview.appendChild(el("div", { class: "tag warn", text: result.warning }));
      }
      preview.appendChild(el("div", { text: "raw notes saved to " + result.meeting_file, style: "font-size:11px;color:var(--text-dim);margin:6px 0;" }));

      var d = result.decisions || [], t = result.tasks || [], i = result.ideas || [], fl = result.flagged || [];
      if (!d.length && !t.length && !i.length && !fl.length) {
        preview.appendChild(el("div", { class: "empty-state", text: "nothing extracted" }));
        return;
      }
      [["Decisions", d, function (x) { return x.text + " — " + (x.who || ""); }],
       ["Tasks", t, function (x) { return x.title + (x.owner ? " — " + x.owner : ""); }],
       ["Ideas", i, function (x) { return x.text + " — " + (x.who || ""); }],
       ["Flagged (unclear)", fl, function (x) { return x; }]].forEach(function (group) {
        var label = group[0], items = group[1], fmt = group[2];
        if (!items.length) return;
        preview.appendChild(el("div", { text: label, style: "color:var(--text-dim);font-size:11px;margin-top:6px;" }));
        items.forEach(function (item) {
          preview.appendChild(el("div", { class: "row", text: fmt(item) }));
        });
      });

      if (d.length || t.length || i.length) {
        var actions = el("div", { class: "actions", style: "margin-top:8px;" });
        var confirmBtn = el("button", { text: "confirm — write these" });
        var discardBtn = el("button", { text: "discard" });
        confirmBtn.addEventListener("click", function () {
          postJSON("/api/notes/confirm", { preview_id: result.preview_id }).then(function (confirmed) {
            if (!confirmed.ok) return;
            document.getElementById("pm-notes-text").value = "";
            preview.innerHTML = "";
            preview.appendChild(el("div", { class: "tag ok", text: "written" }));
            refresh();
          });
        });
        discardBtn.addEventListener("click", function () {
          preview.innerHTML = "";
        });
        actions.appendChild(confirmBtn);
        actions.appendChild(discardBtn);
        preview.appendChild(actions);
      }
    });
  });

  // ---------------------------------------------------------------------
  // boot
  // ---------------------------------------------------------------------

  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("input", function () {
      if (state && !form.dataset.revision) form.dataset.revision = state.revision;
    });
  });
  document.getElementById("review-drafts").addEventListener("click", function () {
    refresh().then(function () {
      if (!state || !confirm("Review the latest board before retrying. Keep form input, but base the next save on this newly loaded state?")) return;
      document.querySelectorAll("form").forEach(function (form) { delete form.dataset.revision; });
      document.getElementById("save-status").textContent = "Latest state loaded. Review your retained input, then submit again. Failed button actions must be repeated from the updated board.";
    });
  });
  refresh();
  setInterval(refresh, POLL_MS);
  setInterval(tickCountdown, 1000);
})();
