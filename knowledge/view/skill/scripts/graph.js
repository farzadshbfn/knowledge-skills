// graph.js — Knowledge graph visualization for KB Viewer
// Depends on: d3 (global), toUrlPath/fromUrlPath/kbConfig (from index.html)

// ---------------------------------------------------------------------------
// Config (editable from controls panel)
// ---------------------------------------------------------------------------
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const graphConfig = {
  repel: -800,
  edgeDistance: 160,
  centralForce: 0.02,
  sizeMode: "both", // "both", "in", "out"
  fadeCoef: 0.5,     // 0=no fading, 1=maximum fading
  boundaryFade: 1.0, // 0=invisible, 1=full opacity (KB hulls + bg only)
  showOrphans: false, // include nodes with zero connections
};

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let mmGraph = null;
let mmSimulation = null;
let currentView = "tree";
let mmZoom = null;

// Render-local state (set during renderGraph, used by focus/hover)
let graphNeighbors = {};
let graphCurrentZoom = 1;
let graphHoveredNode = null;
let graphFocusedNode = null; // set from sidebar click
let graphFlowRAF = null;
let graphMaxConn = 1;
let graphNodes, graphEdges, graphEdgeOverlays, graphCircles, graphLabels;
let graphEdgeGroup, graphEdgeOverlayGroup, graphNodeGroup, graphZoomLayer, graphHullGroup, graphLabelOverlay;
let updateGraphVisuals = () => {}; // set during renderGraph
let activateNode = () => {};
let deactivateAll = () => {};
let kbCenters = {};
let graphW = 0, graphH = 0;
let kbNamesList = [];
let hullEntries = {};
let hullLabelEntries = {};

// Pure layout computation — testable without DOM
function computeKbLayout(kbRoots, nodesByKb, viewW, viewH) {
  const cx = viewW / 2, cy = viewH / 2;
  const kbNames = kbRoots.map(e => e.name);
  const centers = {};

  if (kbNames.length <= 1) {
    kbNames.forEach(kb => { centers[kb] = { x: cx, y: cy }; });
    return centers;
  }

  // --- Build parent-child tree from path nesting ---
  const kbPaths = {};
  kbRoots.forEach(e => {
    const norm = e.path.replace(/^\.\//, "");
    kbPaths[e.name] = norm.replace(/\/?knowledge$/, "") || ".";
  });

  const kbParent = {};
  const kbChildren = {};
  kbNames.forEach(kb => { kbChildren[kb] = []; kbParent[kb] = null; });
  kbNames.forEach(kb => {
    const myDir = kbPaths[kb];
    let bestParent = null, bestLen = 0;
    kbNames.forEach(other => {
      if (other === kb) return;
      const otherDir = kbPaths[other];
      const isChild = otherDir === "." ? (myDir !== ".") : myDir.startsWith(otherDir + "/");
      const len = otherDir === "." ? 0 : otherDir.length;
      if (isChild && len >= bestLen) {
        bestParent = other; bestLen = len;
      }
    });
    kbParent[kb] = bestParent;
    if (bestParent) kbChildren[bestParent].push(kb);
  });

  // --- Subtree weights via DFS ---
  const subtreeWeight = {};
  function computeWeight(kb) {
    let w = Math.max((nodesByKb[kb] || 0), 1);
    for (const child of kbChildren[kb]) w += computeWeight(child);
    return subtreeWeight[kb] = w;
  }

  // --- Identify center KBs (parentless) ---
  const centerRoots = kbNames.filter(kb => !kbParent[kb]);
  centerRoots.forEach(computeWeight);

  const dim = Math.min(viewW, viewH);
  const ringStep = dim * 0.3;

  // --- Place center roots at origin ---
  const centerR = centerRoots.length > 1 ? dim * 0.06 : 0;
  centerRoots.forEach((kb, i) => {
    const angle = (i / centerRoots.length) * 2 * Math.PI - Math.PI / 2;
    centers[kb] = { x: cx + Math.cos(angle) * centerR, y: cy + Math.sin(angle) * centerR };
  });

  // --- Sector placement: children radiate from their parent's position ---
  function place(kbs, startAngle, endAngle, parentX, parentY) {
    if (!kbs.length) return;
    const totalWeight = kbs.reduce((s, kb) => s + subtreeWeight[kb], 0);
    let cursor = startAngle;
    kbs.forEach(kb => {
      const slice = (subtreeWeight[kb] / totalWeight) * (endAngle - startAngle);
      const aStart = cursor;
      const aEnd = cursor + slice;
      const midAngle = (aStart + aEnd) / 2;
      const px = parentX + Math.cos(midAngle) * ringStep;
      const py = parentY + Math.sin(midAngle) * ringStep;
      centers[kb] = { x: px, y: py };
      if (kbChildren[kb].length) {
        place(kbChildren[kb], aStart, aEnd, px, py);
      }
      cursor = aEnd;
    });
  }

  const firstRing = [];
  centerRoots.forEach(kb => firstRing.push(...kbChildren[kb]));
  place(firstRing, 0, 2 * Math.PI, cx, cy);

  return centers;
}

function recomputeKbCenters() {
  const config = (typeof kbConfig !== "undefined" ? kbConfig : {}).kb_roots || [];
  const nodesByKb = {};
  kbNamesList.forEach(kb => { nodesByKb[kb] = 0; });
  if (mmGraph) mmGraph.nodes.forEach(n => { nodesByKb[n.kb] = (nodesByKb[n.kb] || 0) + 1; });
  const result = computeKbLayout(config, nodesByKb, graphW, graphH);
  Object.assign(kbCenters, result);
}

// ---------------------------------------------------------------------------
// View switching
// ---------------------------------------------------------------------------
function setView(view) {
  currentView = view;
  document.querySelectorAll(".view-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.view === view);
  });

  const searchBar = document.getElementById("search-bar");
  const breadcrumb = document.getElementById("breadcrumb");
  const contentWrap = document.getElementById("content-wrap");
  const gWrap = document.getElementById("graph-wrap");

  if (view === "graph") {
    searchBar.style.display = "none";
    breadcrumb.style.display = "none";
    contentWrap.style.display = "none";
    gWrap.classList.add("active");
    const focusPath = typeof currentPath !== "undefined" ? currentPath : null;
    if (!mmGraph) {
      loadGraph().then(() => {
        // Wait for simulation to position nodes before focusing
        if (focusPath) setTimeout(() => focusGraphNode(focusPath), 600);
      });
    } else {
      if (mmSimulation) mmSimulation.alpha(0.05).restart();
      if (focusPath) focusGraphNode(focusPath);
    }
    const url = new URL(window.location);
    url.searchParams.set("view", "graph");
    history.replaceState({ view: "graph" }, "", url);
  } else {
    searchBar.style.display = "";
    breadcrumb.style.display = "";
    contentWrap.style.display = "";
    gWrap.classList.remove("active");
    if (mmSimulation) mmSimulation.stop();
    const url = new URL(window.location);
    url.searchParams.delete("view");
    history.replaceState(null, "", url.pathname + url.hash);
  }
}

// ---------------------------------------------------------------------------
// Graph loading
// ---------------------------------------------------------------------------
let mmGraphOriginal = null; // unfiltered copy

async function loadGraph() {
  try {
    let graphData;
    if (typeof buildGraphFromCache === "function" && Object.keys(fileCache || {}).length > 0) {
      graphData = buildGraphFromCache();
    } else {
      const res = await fetch("/api/graph");
      graphData = await res.json();
    }
    mmGraphOriginal = graphData;
    mmGraph = JSON.parse(JSON.stringify(mmGraphOriginal));
    renderGraph();
  } catch (e) {
    console.error("Failed to load graph:", e);
  }
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------
function renderGraph() {
  // Restore from original (orphan toggle may have modified nodes)
  if (mmGraphOriginal) mmGraph = JSON.parse(JSON.stringify(mmGraphOriginal));

  const svg = d3.select("#graph-svg");
  svg.selectAll("*").remove();

  // --- SVG glow filters ---
  const defs = svg.append("defs");
  const glowStrong = defs.append("filter").attr("id", "glow-strong")
    .attr("x", "-80%").attr("y", "-80%").attr("width", "260%").attr("height", "260%");
  glowStrong.append("feGaussianBlur").attr("in", "SourceGraphic").attr("stdDeviation", "8").attr("result", "blur");
  glowStrong.append("feComposite").attr("in", "SourceGraphic").attr("in2", "blur").attr("operator", "over");

  const glowSoft = defs.append("filter").attr("id", "glow-soft")
    .attr("x", "-60%").attr("y", "-60%").attr("width", "220%").attr("height", "220%");
  glowSoft.append("feGaussianBlur").attr("in", "SourceGraphic").attr("stdDeviation", "5").attr("result", "blur");
  glowSoft.append("feComposite").attr("in", "SourceGraphic").attr("in2", "blur").attr("operator", "over");

  const wrap = document.getElementById("graph-wrap");
  const W = graphW = wrap.clientWidth;
  const H = graphH = wrap.clientHeight;

  // --- Color scheme ---
  const kbNames = kbNamesList = [...new Set(mmGraph.nodes.map(n => n.kb))];

  function kbHue(kb) {
    return (kbNames.indexOf(kb) / Math.max(kbNames.length, 1)) * 300 + 210;
  }

  function folderHash(s) {
    let h = 0;
    for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
    return h;
  }

  function skillParentFolder(folder) {
    const idx = folder.indexOf("/skill");
    return idx >= 0 ? folder.slice(0, idx) : null;
  }

  function nodeColor(d) {
    const base = kbHue(d.kb);
    const parent = skillParentFolder(d.folder);
    if (parent !== null) {
      // Skill nodes share hue with parent topic folder, vary lightness by depth
      const offset = (((folderHash(parent) % 40) + 40) % 40) - 20;
      const skillDepth = d.folder.slice(parent.length).split("/").filter(Boolean).length;
      const light = Math.min(45 + skillDepth * 8, 70);
      return `hsl(${base + offset}, 75%, ${light}%)`;
    }
    const offset = (((folderHash(d.folder) % 40) + 40) % 40) - 20;
    const depth = d.folder.split("/").filter(Boolean).length;
    const light = Math.min(55 + depth * 5, 75);
    return `hsl(${base + offset}, 65%, ${light}%)`;
  }

  function kbColor(kb) { return `hsl(${kbHue(kb)}, 50%, 85%)`; }
  function kbStroke(kb) { return `hsl(${kbHue(kb)}, 40%, 60%)`; }

  // --- Connection counts & node radius ---
  computeNodeSizes();

  // Filter orphans from simulation if disabled
  if (!graphConfig.showOrphans) {
    const connIds = new Set();
    mmGraph.edges.forEach(e => {
      connIds.add(typeof e.source === "object" ? e.source.id : e.source);
      connIds.add(typeof e.target === "object" ? e.target.id : e.target);
    });
    mmGraph.nodes = mmGraph.nodes.filter(n => connIds.has(n.id));
  }

  // --- KB cluster centers ---
  recomputeKbCenters();


  // --- Node KB lookup + seed initial positions near KB centers ---
  const nodeKb = {};
  mmGraph.nodes.forEach(n => {
    nodeKb[n.id] = n.kb;
    const center = kbCenters[n.kb];
    if (center && n.x === undefined) {
      n.x = center.x + (Math.random() - 0.5) * 150;
      n.y = center.y + (Math.random() - 0.5) * 150;
    }
  });

  // --- D3 force simulation ---
  // Isolated nodes get stronger pull toward cluster center
  const clusterStrength = d => {
    const base = graphConfig.centralForce;
    return d.connections === 0 ? base * 4 : d.connections <= 1 ? base * 2 : base;
  };

  const linkStrength = e => {
    const src = typeof e.source === "object" ? e.source.id : e.source;
    const tgt = typeof e.target === "object" ? e.target.id : e.target;
    return nodeKb[src] !== nodeKb[tgt] ? 0.02 : 0.2;
  };

  mmSimulation = d3.forceSimulation(mmGraph.nodes)
    .force("link", d3.forceLink(mmGraph.edges).id(d => d.id).distance(graphConfig.edgeDistance).strength(linkStrength))
    .force("charge", d3.forceManyBody().strength(graphConfig.repel))
    .force("collision", d3.forceCollide().radius(d => d.radius + 8))
    .force("x", d3.forceX().x(d => kbCenters[d.kb].x).strength(clusterStrength))
    .force("y", d3.forceY().y(d => kbCenters[d.kb].y).strength(clusterStrength))
    .alphaDecay(0.015);

  // --- Zoom ---
  graphCurrentZoom = 1;
  let graphZoomTransform = d3.zoomIdentity;
  let graphZooming = false;
  let graphZoomTimer = null;
  graphZoomLayer = svg.append("g");
  mmZoom = d3.zoom().scaleExtent([0.05, 4]).on("zoom", (e) => {
    graphZoomLayer.attr("transform", e.transform);
    graphZoomTransform = e.transform;
    graphCurrentZoom = e.transform.k;
    // Suppress pointermove hover during zoom (Safari fires pointermove on pinch)
    graphZooming = true;
    clearTimeout(graphZoomTimer);
    graphZoomTimer = setTimeout(() => { graphZooming = false; }, 120);
    updateGraphVisuals();
    updateHulls();
  });
  svg.call(mmZoom);

  // --- KB boundary hulls (inside zoom layer) ---
  graphHullGroup = graphZoomLayer.append("g").attr("class", "hulls");

  // --- KB labels overlay (outside zoom layer — fixed screen size) ---
  graphLabelOverlay = svg.append("g").attr("class", "kb-label-overlay").style("pointer-events", "none");

  // --- Index hierarchy levels (for thicker backbone edges) ---
  // lvl = folder depth within KB: index.md = 0, topic/index.md = 1, etc.
  const nodeLevel = {};
  const isIndex = {};
  mmGraph.nodes.forEach(n => {
    const idx = n.id.endsWith("/index.md");
    isIndex[n.id] = idx;
    if (idx) {
      // folder is like "." (lvl0), "topic" (lvl1), "topic/sub" (lvl2)
      const parts = n.folder.split("/").filter(Boolean);
      nodeLevel[n.id] = Math.max(0, parts.length - 1); // "." = 0
    }
  });
  const maxLevel = Math.max(1, ...Object.values(nodeLevel));
  const BASE_EDGE_WIDTH = 1.5;

  function edgeWidth(e) {
    const s = typeof e.source === "object" ? e.source.id : e.source;
    const t = typeof e.target === "object" ? e.target.id : e.target;
    if (nodeKb[s] !== nodeKb[t]) return 2.5; // cross-KB
    if (isIndex[s] && isIndex[t]) {
      // Backbone edge: thicker at lower levels
      const lvl = Math.min(nodeLevel[s], nodeLevel[t]);
      const thickness = BASE_EDGE_WIDTH + (maxLevel - lvl) * 1.5;
      return thickness;
    }
    return BASE_EDGE_WIDTH;
  }

  // --- Edges (base layer + animated overlay) ---
  graphEdgeGroup = graphZoomLayer.append("g");
  graphEdges = graphEdgeGroup.selectAll("line")
    .data(mmGraph.edges)
    .join("line")
    .attr("class", "mm-edge")
    .attr("stroke-width", edgeWidth)
    .attr("stroke-opacity", e => {
      const s = typeof e.source === "object" ? e.source.id : e.source;
      const t = typeof e.target === "object" ? e.target.id : e.target;
      if (nodeKb[s] !== nodeKb[t]) return 1.0;
      if (isIndex[s] && isIndex[t]) {
        const lvl = Math.min(nodeLevel[s], nodeLevel[t]);
        return 1.0 - (lvl / maxLevel) * 0.15; // lvl0=1.0, deeper=0.85
      }
      return 0.65;
    })
    .attr("stroke-dasharray", e => {
      const s = typeof e.source === "object" ? e.source.id : e.source;
      const t = typeof e.target === "object" ? e.target.id : e.target;
      return nodeKb[s] !== nodeKb[t] ? "6 4" : null;
    });
  graphEdgeOverlayGroup = graphZoomLayer.append("g");
  graphEdgeOverlays = graphEdgeOverlayGroup.selectAll("line")
    .data(mmGraph.edges)
    .join("line")
    .attr("stroke", cssVar("--edge-overlay"))
    .attr("stroke-width", 1.0)
    .attr("stroke-linecap", "round")
    .attr("opacity", 0);

  // --- Nodes ---
  graphNodeGroup = graphZoomLayer.append("g");
  graphNodes = graphNodeGroup.selectAll("g")
    .data(mmGraph.nodes)
    .join("g")
    .attr("class", "mm-node");

  graphCircles = graphNodes.append("circle")
    .attr("r", d => d.radius)
    .attr("fill", d => nodeColor(d))
    .attr("stroke", d => d3.color(nodeColor(d)).darker(0.5))
    .attr("stroke-width", 1.5);

  // --- Skill icon (scroll-text) for nodes inside /skill/ folders ---
  function isSkillNode(d) { return d.id.includes("/skill/"); }
  function isMainSkillNode(d) { return d.id.endsWith("/skill/SKILL.md"); }

  graphNodes.filter(isSkillNode).each(function(d) {
    const g = d3.select(this);
    const iconScale = d.radius / 14; // 24px icon viewBox, fit inside radius
    const icon = g.append("g")
      .attr("class", "mm-skill-icon")
      .attr("transform", `scale(${iconScale}) translate(-12, -12)`);
    const strokeColor = d3.color(nodeColor(d)).darker(1.2).formatRgb();
    icon.selectAll("path")
      .data([
        "M15 12h-5",
        "M15 8h-5",
        "M19 17V5a2 2 0 0 0-2-2H4",
        "M8 21h12a2 2 0 0 0 2-2v-1a1 1 0 0 0-1-1H11a1 1 0 0 0-1 1v1a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v2a1 1 0 0 0 1 1h3",
      ])
      .join("path")
      .attr("d", p => p)
      .attr("fill", "none")
      .attr("stroke", strokeColor)
      .attr("stroke-width", 2)
      .attr("stroke-linecap", "round")
      .attr("stroke-linejoin", "round");
  });

  graphLabels = graphNodes.append("text")
    .attr("class", "mm-label")
    .attr("dy", d => d.radius + 14)
    .text(d => d.name.length > 25 ? d.name.slice(0, 23) + "\u2026" : d.name);

  // --- Drag ---
  // Use container for drag so it works alongside zoom in all browsers
  graphNodes.call(d3.drag()
    .container(graphZoomLayer.node())
    .on("start", (e, d) => {
      if (!e.active) mmSimulation.alphaTarget(0.3).restart();
      d.fx = d.x; d.fy = d.y;
    })
    .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
    .on("end", (e, d) => {
      if (!e.active) mmSimulation.alphaTarget(0);
      d.fx = null; d.fy = null;
    })
  );

  // --- Click -> open in new tab ---
  graphNodes.on("click", (e, d) => {
    if (e.defaultPrevented) return;
    const url = "/" + toUrlPath(d.id);
    window.open(url, "_blank");
  });

  // --- Click background -> clear focus ---
  // Listen on the wrap div so clicks outside the SVG also clear
  const wrapEl = document.getElementById("graph-wrap");
  wrapEl.addEventListener("pointerdown", (e) => {
    // Ignore clicks on nodes, hulls, or controls
    let el = e.target;
    while (el && el !== wrapEl) {
      const cl = el.getAttribute ? el.getAttribute("class") || "" : "";
      if (cl.includes("mm-node") || cl.includes("mm-hull") || (el.id && el.id === "graph-controls")) return;
      el = el.parentNode;
    }
    graphFocusedNode = null;
    deactivateAll();
  });

  // --- Visual helpers ---
  graphMaxConn = Math.max(1, d3.max(mmGraph.nodes, n => n.connections));

  function desaturate(color, t) {
    const c = d3.hsl(color);
    c.s *= t;
    c.l = c.l + (0.92 - c.l) * (1 - t);
    return c.formatRgb();
  }

  function zoomOpacity(d) {
    if (isMainSkillNode(d)) return 1; // always visible
    const fc = graphConfig.fadeCoef;
    if (fc === 0) return 1;
    const importance = Math.sqrt(d.connections) / Math.sqrt(graphMaxConn);
    const threshold = fc * (0.4 + (1 - importance) * 2.6);
    const t = (graphCurrentZoom - threshold) / 0.15;
    return Math.max(0, Math.min(1, t));
  }

  function zoomNodeFade(d) {
    if (isMainSkillNode(d)) return 1; // always visible
    const fc = graphConfig.fadeCoef;
    if (fc === 0) return 1;
    const importance = Math.sqrt(d.connections) / Math.sqrt(graphMaxConn);
    const threshold = fc * (0.1 + (1 - importance) * 2.6);
    const t = (graphCurrentZoom - threshold) / 0.5;
    return Math.max(0.15, Math.min(1, t));
  }

  // Active node = hovered OR focused from sidebar (both get same treatment)
  function activeNode() { return graphHoveredNode || graphFocusedNode; }

  function hoverBoost(d, t) {
    const active = activeNode();
    if (!active) return t;
    if (d === active) return 1;
    if (graphNeighbors[active.id] && graphNeighbors[active.id].has(d.id)) return 1;
    return Math.min(t, 0.1);
  }

  // Shared visual update (called on zoom + hover + controls)
  updateGraphVisuals = function() {
    graphLabels.attr("opacity", d => hoverBoost(d, zoomOpacity(d)));
    graphCircles.attr("fill", d => desaturate(nodeColor(d), hoverBoost(d, zoomNodeFade(d))));
    graphCircles.attr("stroke", d => {
      const t = hoverBoost(d, zoomNodeFade(d));
      const borderT = Math.min(1, t + 0.25);
      return desaturate(d3.color(nodeColor(d)).darker(0.5).formatRgb(), borderT);
    });
    // Update skill icon colors to match node saturation
    graphNodeGroup.selectAll(".mm-skill-icon").each(function() {
      const d = d3.select(this.parentNode).datum();
      const t = hoverBoost(d, zoomNodeFade(d));
      const iconColor = desaturate(d3.color(nodeColor(d)).darker(1.2).formatRgb(), t);
      d3.select(this).selectAll("path").attr("stroke", iconColor);
    });
    const edgeFade = Math.max(0.3, Math.min(0.8, (graphCurrentZoom - 0.1) / 1.5));
    const active = activeNode();
    graphEdges.attr("stroke-opacity", e => {
      if (!active) return edgeFade;
      const src = typeof e.source === "object" ? e.source.id : e.source;
      const tgt = typeof e.target === "object" ? e.target.id : e.target;
      if (src === active.id || tgt === active.id) return 0.25;
      return Math.min(edgeFade, 0.08);
    }).attr("stroke", e => {
      if (!active) return cssVar("--edge");
      const src = typeof e.source === "object" ? e.source.id : e.source;
      const tgt = typeof e.target === "object" ? e.target.id : e.target;
      if (src === active.id || tgt === active.id) return cssVar("--edge-active");
      return cssVar("--edge");
    });
  }

  // --- Hover + focus (shared activate/deactivate) ---
  graphHoveredNode = null;
  graphFocusedNode = null;
  graphFlowRAF = null;

  activateNode = function(d) {
    const hId = d.id;
    const isConn = nd => nd === d || (graphNeighbors[hId] && graphNeighbors[hId].has(nd.id));
    const isConnEdge = ed => {
      const s = typeof ed.source === "object" ? ed.source.id : ed.source;
      const t = typeof ed.target === "object" ? ed.target.id : ed.target;
      return s === hId || t === hId;
    };
    graphEdges.filter(isConnEdge).each(function() { graphZoomLayer.node().appendChild(this); });
    graphEdgeOverlays.filter(isConnEdge).each(function() { graphZoomLayer.node().appendChild(this); });
    graphNodes.filter(isConn).each(function() { graphZoomLayer.node().appendChild(this); });
    // Apply glow: strong on active node, soft on neighbors
    graphCircles.attr("filter", nd => {
      if (nd === d) return "url(#glow-strong)";
      if (graphNeighbors[hId] && graphNeighbors[hId].has(nd.id)) return "url(#glow-soft)";
      return null;
    }).attr("r", nd => {
      if (nd === d) return nd.radius * 1.3;
      return nd.radius;
    });
    // Scale skill icons with enlarged nodes
    graphNodeGroup.selectAll(".mm-skill-icon").each(function() {
      const nd = d3.select(this.parentNode).datum();
      const r = nd === d ? nd.radius * 1.3 : nd.radius;
      const s = r / 14;
      d3.select(this).attr("transform", `scale(${s}) translate(-12, -12)`);
    });
    updateGraphVisuals();
    if (graphFlowRAF) cancelAnimationFrame(graphFlowRAF);
    graphFlowRAF = null;
    animateFlow();
  }

  deactivateAll = function() {
    if (graphFlowRAF) { cancelAnimationFrame(graphFlowRAF); graphFlowRAF = null; }
    graphHoveredNode = null;
    graphEdgeOverlays.attr("opacity", 0)
      .attr("stroke-dasharray", null).attr("stroke-dashoffset", null);
    graphCircles.attr("filter", null).attr("r", d => d.radius);
    // Reset skill icon scale
    graphNodeGroup.selectAll(".mm-skill-icon").each(function() {
      const nd = d3.select(this.parentNode).datum();
      const s = nd.radius / 14;
      d3.select(this).attr("transform", `scale(${s}) translate(-12, -12)`);
    });
    // Restore DOM order
    graphZoomLayer.selectAll(".mm-edge").each(function() {
      if (this.parentNode !== graphEdgeGroup.node()) graphEdgeGroup.node().appendChild(this);
    });
    graphEdgeOverlays.each(function() {
      if (this.parentNode !== graphEdgeOverlayGroup.node()) graphEdgeOverlayGroup.node().appendChild(this);
    });
    graphZoomLayer.selectAll(".mm-node").each(function() {
      if (this.parentNode !== graphNodeGroup.node()) graphNodeGroup.node().appendChild(this);
    });
    updateGraphVisuals();
  }

  // Hover via pointermove on SVG — immune to DOM rearrangement by activateNode
  // Suppressed during zoom to prevent Safari pinch-to-zoom from triggering hover cycles
  svg.on("pointermove", (e) => {
    if (graphZooming) return;
    const target = e.target;
    const nodeEl = target.closest ? target.closest(".mm-node") : null;
    if (nodeEl) {
      const d = d3.select(nodeEl).datum();
      if (d && d !== graphHoveredNode) {
        graphHoveredNode = d;
        activateNode(d);
      }
    } else if (graphHoveredNode) {
      graphHoveredNode = null;
      if (graphFocusedNode) activateNode(graphFocusedNode);
      else deactivateAll();
    }
  });

  function animateFlow() {
    const active = activeNode();
    if (!active) { graphFlowRAF = null; return; }
    const offset = (Date.now() / 4) % 1000;
    const hId = active.id;
    graphEdgeOverlays.each(function(e) {
      const src = typeof e.source === "object" ? e.source.id : e.source;
      const tgt = typeof e.target === "object" ? e.target.id : e.target;
      if (src === hId || tgt === hId) {
        this.setAttribute("stroke-dasharray", "18 50");
        this.setAttribute("stroke-dashoffset", -offset);
        this.setAttribute("opacity", "0.85");
      } else {
        this.setAttribute("opacity", "0");
      }
    });
    graphFlowRAF = requestAnimationFrame(animateFlow);
  }

  // --- KB root index lookup (for hull click → focus) ---
  const kbRootIndex = {};
  for (const kb of kbNames) {
    const root = mmGraph.nodes.find(n => n.kb === kb && n.folder === "." && n.id.endsWith("/index.md"));
    if (root) kbRootIndex[kb] = root.id;
  }

  // --- Tick ---
  // Pre-create hull paths and labels once; updateHulls() only updates geometry
  hullEntries = {};
  hullLabelEntries = {};
  for (const kb of kbNames) {
    const kbNodes = mmGraph.nodes.filter(n => n.kb === kb);
    if (kbNodes.length < 3) continue;
    const bf = graphConfig.boundaryFade;
    const hullPath = graphHullGroup.append("path")
      .attr("fill", kbColor(kb)).attr("fill-opacity", 0.05 * bf)
      .attr("stroke", kbStroke(kb)).attr("stroke-opacity", bf)
      .attr("class", "mm-hull")
      .style("cursor", kbRootIndex[kb] ? "pointer" : "default");
    hullPath.on("click", (e) => { e.stopPropagation(); graphFocusedNode = null; deactivateAll(); });
    hullEntries[kb] = { path: hullPath, nodes: kbNodes };
    hullLabelEntries[kb] = graphLabelOverlay.append("text")
      .attr("class", "mm-hull-label")
      .attr("text-anchor", "middle").attr("fill", kbStroke(kb)).text(kb)
      .attr("opacity", bf)
      .style("font-size", "14px")
      .style("font-weight", "700")
      .style("letter-spacing", "1.5px")
      .style("text-transform", "uppercase")
      .style("pointer-events", "none");
  }

  function updateHulls() {
    for (const kb of kbNames) {
      const entry = hullEntries[kb];
      if (!entry) continue;
      const points = entry.nodes.map(n => [n.x, n.y]);
      const hull = d3.polygonHull(points);
      if (!hull) { entry.path.attr("d", ""); continue; }
      const cx = d3.mean(hull, p => p[0]);
      const cy = d3.mean(hull, p => p[1]);
      const padded = hull.map(([x, y]) => {
        const dx = x - cx, dy = y - cy;
        const dist = Math.sqrt(dx * dx + dy * dy);
        return [x + (dx / dist) * 40, y + (dy / dist) * 40];
      });
      entry.path.attr("d", "M" + padded.join("L") + "Z");
      const screenTop = graphZoomTransform.apply([cx, d3.min(padded, p => p[1]) - 18]);
      hullLabelEntries[kb].attr("x", screenTop[0]).attr("y", screenTop[1]);
    }
  }

  mmSimulation.on("tick", () => {
    graphEdges
      .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    if (activeNode()) {
      graphEdgeOverlays
        .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    }
    graphNodes.attr("transform", d => `translate(${d.x},${d.y})`);
    updateHulls();
  });

  // Build controls panel
  buildControlsPanel();
}

// ---------------------------------------------------------------------------
// Node sizing (recomputed when sizeMode changes)
// ---------------------------------------------------------------------------
function computeNodeSizes() {
  const inCount = {}, outCount = {};
  mmGraph.edges.forEach(e => {
    const src = typeof e.source === "object" ? e.source.id : e.source;
    const tgt = typeof e.target === "object" ? e.target.id : e.target;
    outCount[src] = (outCount[src] || 0) + 1;
    inCount[tgt] = (inCount[tgt] || 0) + 1;
  });
  mmGraph.nodes.forEach(n => {
    const inc = inCount[n.id] || 0;
    const out = outCount[n.id] || 0;
    if (graphConfig.sizeMode === "in") n.connections = inc;
    else if (graphConfig.sizeMode === "out") n.connections = out;
    else n.connections = inc + out;
    n.radius = 6 + Math.sqrt(n.connections) * 3.5;
  });

  // Build neighbor map
  graphNeighbors = {};
  mmGraph.edges.forEach(e => {
    const src = typeof e.source === "object" ? e.source.id : e.source;
    const tgt = typeof e.target === "object" ? e.target.id : e.target;
    (graphNeighbors[src] = graphNeighbors[src] || new Set()).add(tgt);
    (graphNeighbors[tgt] = graphNeighbors[tgt] || new Set()).add(src);
  });
}

// ---------------------------------------------------------------------------
// Apply config changes to live simulation
// ---------------------------------------------------------------------------
function applyGraphConfig() {
  if (!mmSimulation) return;
  recomputeKbCenters();
  mmSimulation.force("charge").strength(graphConfig.repel);
  mmSimulation.force("link").distance(graphConfig.edgeDistance).strength(e => {
    const src = typeof e.source === "object" ? e.source.id : e.source;
    const tgt = typeof e.target === "object" ? e.target.id : e.target;
    const srcKb = mmGraph.nodes.find(n => n.id === src);
    const tgtKb = mmGraph.nodes.find(n => n.id === tgt);
    if (srcKb && tgtKb && srcKb.kb !== tgtKb.kb) return 0.02;
    return 0.2;
  });
  mmSimulation.force("x").x(d => kbCenters[d.kb]?.x || graphW / 2).strength(graphConfig.centralForce);
  mmSimulation.force("y").y(d => kbCenters[d.kb]?.y || graphH / 2).strength(graphConfig.centralForce);

  computeNodeSizes();
  mmSimulation.force("collision").radius(d => d.radius + 8);
  if (graphCircles) graphCircles.attr("r", d => d.radius);
  if (graphLabels) graphLabels.attr("dy", d => d.radius + 14);
  graphMaxConn = Math.max(1, d3.max(mmGraph.nodes, n => n.connections));

  mmSimulation.alpha(0.5).restart();
}

// ---------------------------------------------------------------------------
// Controls panel
// ---------------------------------------------------------------------------
function buildControlsPanel() {
  let panel = document.getElementById("graph-controls");
  if (panel) return; // already built

  const wrap = document.getElementById("graph-wrap");
  panel = document.createElement("div");
  panel.id = "graph-controls";
  panel.className = "collapsed";
  const repelAbs = Math.abs(graphConfig.repel);
  panel.innerHTML = `
    <button class="gc-toggle" onclick="this.parentElement.classList.toggle('collapsed')">
      <span class="gc-icon">&#9881;</span>
    </button>
    <div class="gc-body">
      <label><span class="gc-label-text">Repel</span><input type="range" id="gc-repel" min="50" max="1500" step="10" value="${repelAbs}"><span id="gc-repel-v">${repelAbs}</span></label>
      <label><span class="gc-label-text">Edge dist</span><input type="range" id="gc-dist" min="30" max="400" step="5" value="${graphConfig.edgeDistance}"><span id="gc-dist-v">${graphConfig.edgeDistance}</span></label>
      <label><span class="gc-label-text">Spread</span><input type="range" id="gc-cluster" min="0" max="100" step="1" value="${100 - graphConfig.centralForce * 1000}"><span id="gc-cluster-v">${graphConfig.centralForce}</span></label>
      <label><span class="gc-label-text">Fade</span><input type="range" id="gc-fade" min="0" max="100" step="1" value="${graphConfig.fadeCoef * 100}"><span id="gc-fade-v">${Math.round(graphConfig.fadeCoef * 100)}%</span></label>
      <label><span class="gc-label-text">Boundary</span><input type="range" id="gc-boundary" min="0" max="100" step="1" value="${graphConfig.boundaryFade * 100}"><span id="gc-boundary-v">${Math.round(graphConfig.boundaryFade * 100)}%</span></label>
      <label><span class="gc-label-text">Size by</span>
        <select id="gc-size">
          <option value="both" ${graphConfig.sizeMode === "both" ? "selected" : ""}>All links</option>
          <option value="in" ${graphConfig.sizeMode === "in" ? "selected" : ""}>Incoming links</option>
          <option value="out" ${graphConfig.sizeMode === "out" ? "selected" : ""}>Outgoing links</option>
        </select>
      </label>
      <label><input type="checkbox" id="gc-orphans" ${graphConfig.showOrphans ? "checked" : ""}> Show orphans</label>
    </div>
  `;
  wrap.appendChild(panel);

  // Wire up events
  document.getElementById("gc-repel").addEventListener("input", function() {
    graphConfig.repel = -(+this.value);
    document.getElementById("gc-repel-v").textContent = this.value;
    applyGraphConfig();
  });
  document.getElementById("gc-dist").addEventListener("input", function() {
    graphConfig.edgeDistance = +this.value;
    document.getElementById("gc-dist-v").textContent = this.value;
    applyGraphConfig();
  });
  document.getElementById("gc-cluster").addEventListener("input", function() {
    graphConfig.centralForce = (100 - +this.value) / 1000;
    document.getElementById("gc-cluster-v").textContent = graphConfig.centralForce.toFixed(3);
    applyGraphConfig();
  });
  document.getElementById("gc-fade").addEventListener("input", function() {
    graphConfig.fadeCoef = +this.value / 100;
    document.getElementById("gc-fade-v").textContent = Math.round(graphConfig.fadeCoef * 100) + "%";
    updateGraphVisuals();
  });
  document.getElementById("gc-boundary").addEventListener("input", function() {
    graphConfig.boundaryFade = +this.value / 100;
    document.getElementById("gc-boundary-v").textContent = Math.round(graphConfig.boundaryFade * 100) + "%";
    const bf = graphConfig.boundaryFade;
    for (const kb of Object.keys(hullEntries)) {
      hullEntries[kb].path.attr("fill-opacity", 0.05 * bf).attr("stroke-opacity", bf);
      hullLabelEntries[kb].attr("opacity", bf);
    }
    if (mmSimulation) mmSimulation.alpha(0.01).restart();
  });
  document.getElementById("gc-size").addEventListener("change", function() {
    graphConfig.sizeMode = this.value;
    applyGraphConfig();
  });
  document.getElementById("gc-orphans").addEventListener("change", function() {
    graphConfig.showOrphans = this.checked;
    // Rebuild simulation with/without orphans (preserves connected node positions)
    const connIds = new Set();
    mmGraph.edges.forEach(e => {
      connIds.add(typeof e.source === "object" ? e.source.id : e.source);
      connIds.add(typeof e.target === "object" ? e.target.id : e.target);
    });
    // Save positions and zoom transform
    const positions = {};
    mmGraph.nodes.forEach(n => { if (connIds.has(n.id)) positions[n.id] = { x: n.x, y: n.y }; });
    const savedZoom = d3.zoomTransform(d3.select("#graph-svg").node());
    // Re-render then restore positions + zoom
    renderGraph();
    mmGraph.nodes.forEach(n => {
      if (positions[n.id]) { n.x = positions[n.id].x; n.y = positions[n.id].y; }
    });
    d3.select("#graph-svg").call(mmZoom.transform, savedZoom);
    mmSimulation.alpha(0.3).restart();
  });
}

// ---------------------------------------------------------------------------
// Focus on a node (called from sidebar when in graph view)
// ---------------------------------------------------------------------------
// Node.js export for testing
if (typeof module !== "undefined" && module.exports) {
  module.exports = { computeKbLayout };
}

function focusGraphNode(path) {
  if (currentView !== "graph" || !mmGraph || !mmZoom) return;

  const node = mmGraph.nodes.find(n => n.id === path);
  if (!node) return;

  // Activate as if hovered (highlight + flow animation)
  graphFocusedNode = node;
  activateNode(node);

  // Collect node + neighbors for bounding box
  const focused = [node];
  if (graphNeighbors[node.id]) {
    for (const nid of graphNeighbors[node.id]) {
      const n = mmGraph.nodes.find(nd => nd.id === nid);
      if (n) focused.push(n);
    }
  }

  const padding = 100;
  const xs = focused.map(n => n.x);
  const ys = focused.map(n => n.y);
  const x0 = d3.min(xs) - padding, x1 = d3.max(xs) + padding;
  const y0 = d3.min(ys) - padding, y1 = d3.max(ys) + padding;

  const wrap = document.getElementById("graph-wrap");
  const W = wrap.clientWidth, H = wrap.clientHeight;
  const scale = Math.min(W / (x1 - x0), H / (y1 - y0), 2.5);
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;

  const svg = d3.select("#graph-svg");
  svg.transition().duration(750).call(
    mmZoom.transform,
    d3.zoomIdentity.translate(W / 2, H / 2).scale(scale).translate(-cx, -cy)
  );
}
