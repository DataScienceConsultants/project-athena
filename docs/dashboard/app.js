"use strict";

const RAW_FILES = [
  "metadata.json","catalog.csv","catalog_plan.json","fault_associations.csv","faults.geojson",
  "event_plate_context.csv","plate_boundaries.geojson","interaction_pairs.csv","interaction_windows.csv",
  "interaction_summary.json","along_boundary_pairs.csv","along_boundary_windows.csv","along_boundary_summary.json"
];

const state = {
  events: [], byId: new Map(), majorPairs: [], majorWindows: [], study: null, manifest: null,
  filtered: [], tableLimit: 100, selectedEvent: null, selectedMajor: null, majorMin: 7,
  map: null, eventLayer: null, boundaryLayer: null, faultLayer: null,
  charts: {}, boundaryGeo: null, faultGeo: null
};

const $ = id => document.getElementById(id);
const fmt = (n, d=0) => n == null || !Number.isFinite(Number(n)) ? "—" : Number(n).toLocaleString(undefined,{maximumFractionDigits:d,minimumFractionDigits:d});
const dateFmt = v => v ? new Date(v).toLocaleDateString(undefined,{year:"numeric",month:"short",day:"2-digit"}) : "—";
const yearOf = e => e.time ? new Date(e.time).getUTCFullYear() : null;
const ratio = (post, pre) => !pre ? (post ? Infinity : null) : post/pre;
const ratioText = v => v === Infinity ? "∞" : (v == null || !Number.isFinite(v) ? "—" : `${v.toFixed(2)}×`);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c]);

function toast(message){ const el=$("toast"); el.textContent=message; el.hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>el.hidden=true,2600); }
function colorForMag(m){ return m>=9?"#b88cf3":m>=8?"#f06f69":m>=7?"#f1b35b":"#67a9f6"; }
function radiusForMag(m){ return Math.max(3, (m-5.5)*3.6); }
function css(name){ return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
function destroyChart(name){ if(state.charts[name]){ state.charts[name].destroy(); delete state.charts[name]; } }
function chartBase(){ return {responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:"#b7c7ce"}}},scales:{x:{ticks:{color:"#8298a4"},grid:{color:"#1b2d37"}},y:{ticks:{color:"#8298a4"},grid:{color:"#1b2d37"}}}}; }

async function getJSON(path){ const r=await fetch(path); if(!r.ok) throw new Error(`${path}: ${r.status}`); return r.json(); }

async function load(){
  try{
    $("loadingMessage").textContent="Loading catalog and research indexes";
    const [manifest,events,pairs,windows,study]=await Promise.all([
      getJSON("data/manifest.json"),getJSON("data/events.json"),getJSON("data/major_pairs.json"),
      getJSON("data/major_windows.json"),getJSON("data/study.json")
    ]);
    state.manifest=manifest; state.events=events; state.majorPairs=pairs; state.majorWindows=windows; state.study=study;
    state.byId=new Map(events.map(e=>[e.event_id,e]));
    initSummary(); initFilters(); initMap(); initTabs(); initMajorControls(); initStudyControls(); initDataView();
    applyFilters(); renderMajorList(); renderStudy();
    $("loading").classList.add("done");
  }catch(err){ console.error(err); $("loadingMessage").textContent=`Unable to load dashboard data: ${err.message}`; }
}

function initSummary(){
  const earthquakes=state.events.filter(e=>e.event_type==="earthquake");
  const m7=earthquakes.filter(e=>e.magnitude>=7).length, m8=earthquakes.filter(e=>e.magnitude>=8).length, m9=earthquakes.filter(e=>e.magnitude>=9).length;
  const plate=state.events.filter(e=>e.boundary_id).length;
  const coverage=state.study.along_boundary.coverage;
  $("metricEvents").textContent=fmt(state.events.length); $("metricM7").textContent=fmt(m7); $("metricM8").textContent=fmt(m8); $("metricM9").textContent=fmt(m9);
  $("metricPlateCoverage").textContent=`${(100*plate/state.events.length).toFixed(1)}%`; $("metricRoutes").textContent=fmt(coverage.route_available_pair_count);
  $("releaseLabel").textContent=`${state.manifest.release_tag} · schema v${state.manifest.bundle_schema_version}`;
  $("generatedLabel").textContent=`Bundle generated ${dateFmt(state.manifest.generated_at_utc)}`;
 }

function initTabs(){
  document.querySelectorAll(".tab").forEach(btn=>btn.addEventListener("click",()=>{
    document.querySelectorAll(".tab").forEach(b=>b.classList.toggle("active",b===btn));
    document.querySelectorAll(".view").forEach(v=>v.classList.toggle("active",v.id===`view-${btn.dataset.view}`));
    if(btn.dataset.view==="explorer" && state.map) setTimeout(()=>state.map.invalidateSize(),60);
  }));
}

function initFilters(){
  const classes=[...new Set(state.events.map(e=>e.boundary_class).filter(Boolean))].sort();
  classes.forEach(v=>$("boundaryClass").insertAdjacentHTML("beforeend",`<option value="${esc(v)}">${esc(v)}</option>`));
  ["magnitudeFilter","yearFrom","yearTo","boundaryClass","eventType"].forEach(id=>$(id).addEventListener("change",applyFilters));
  $("searchFilter").addEventListener("input",debounce(applyFilters,180));
  $("resetFilters").addEventListener("click",()=>{ $("magnitudeFilter").value="6"; $("yearFrom").value=1976; $("yearTo").value=2025; $("boundaryClass").value="all"; $("eventType").value="earthquake"; $("searchFilter").value=""; applyFilters(); });
  document.querySelectorAll("[data-preset]").forEach(b=>b.addEventListener("click",()=>{ if(b.dataset.preset==="m9") $("magnitudeFilter").value="9"; if(b.dataset.preset==="m8") $("magnitudeFilter").value="8"; if(b.dataset.preset==="recent"){ $("yearFrom").value=2015; $("yearTo").value=2025; } applyFilters(); }));
  document.querySelectorAll("[data-search]").forEach(b=>b.addEventListener("click",()=>{ $("searchFilter").value=b.dataset.search; applyFilters(); }));
  $("showMoreEvents").addEventListener("click",()=>{ state.tableLimit+=100; renderTable(); });
}

function eventMatches(e){
  const min=Number($("magnitudeFilter").value), from=Number($("yearFrom").value), to=Number($("yearTo").value), klass=$("boundaryClass").value, type=$("eventType").value;
  const q=$("searchFilter").value.trim().toLowerCase(), y=yearOf(e);
  if(e.magnitude==null || e.magnitude<min || y<from || y>to) return false;
  if(klass!=="all" && e.boundary_class!==klass) return false;
  if(type!=="all" && e.event_type!==type) return false;
  if(q){ const hay=[e.event_id,e.place,e.boundary_id,e.boundary_class,e.fault_name,e.left_plate,e.right_plate].filter(Boolean).join(" ").toLowerCase(); if(!hay.includes(q)) return false; }
  return true;
}

function applyFilters(){
  state.tableLimit=100; state.filtered=state.events.filter(eventMatches).sort((a,b)=>(b.magnitude-a.magnitude)||(new Date(b.time)-new Date(a.time)));
  $("filteredCount").textContent=`${fmt(state.filtered.length)} records`; $("mapTitle").textContent=`Filtered catalog · M${$("magnitudeFilter").value}+`;
  renderMapEvents(); renderTable(); renderExplorerCharts();
}

function initMap(){
  state.map=L.map("map",{worldCopyJump:true,preferCanvas:true,minZoom:1}).setView([12,0],2);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:18,attribution:"© OpenStreetMap contributors"}).addTo(state.map);
  state.eventLayer=L.layerGroup().addTo(state.map);
  $("toggleBoundaries").addEventListener("change",toggleBoundaries); $("toggleFaults").addEventListener("change",toggleFaults);
}

function renderMapEvents(){
  if(!state.eventLayer) return; state.eventLayer.clearLayers();
  state.filtered.forEach(e=>{ if(e.latitude==null||e.longitude==null) return; const c=L.circleMarker([e.latitude,e.longitude],{radius:radiusForMag(e.magnitude),color:colorForMag(e.magnitude),fillColor:colorForMag(e.magnitude),fillOpacity:.72,weight:e.magnitude>=8?2:1}); c.bindTooltip(`M${fmt(e.magnitude,1)} · ${esc(e.place)}`); c.on("click",()=>selectEvent(e.event_id,true)); c.addTo(state.eventLayer); });
}

async function toggleBoundaries(){
  if(!$("toggleBoundaries").checked){ if(state.boundaryLayer) state.map.removeLayer(state.boundaryLayer); return; }
  try{ if(!state.boundaryGeo){ toast("Loading PB2002 boundary layer…"); state.boundaryGeo=await getJSON("data/raw/plate_boundaries.geojson"); }
    if(!state.boundaryLayer) state.boundaryLayer=L.geoJSON(state.boundaryGeo,{style:{color:"#56d6c4",weight:1,opacity:.55}});
    state.boundaryLayer.addTo(state.map);
  }catch(e){ $("toggleBoundaries").checked=false; toast("Could not load PB2002 layer"); }
}
async function toggleFaults(){
  if(!$("toggleFaults").checked){ if(state.faultLayer) state.map.removeLayer(state.faultLayer); return; }
  try{ if(!state.faultGeo){ toast("Loading GEM fault layer…"); state.faultGeo=await getJSON("data/raw/faults.geojson"); }
    if(!state.faultLayer) state.faultLayer=L.geoJSON(state.faultGeo,{style:{color:"#b88cf3",weight:.8,opacity:.38}});
    state.faultLayer.addTo(state.map);
  }catch(e){ $("toggleFaults").checked=false; toast("Could not load GEM fault layer"); }
}

function selectEvent(id, pan=false){
  const e=state.byId.get(id); if(!e) return; state.selectedEvent=e;
  if(pan && state.map && e.latitude!=null) state.map.setView([e.latitude,e.longitude],Math.max(state.map.getZoom(),5));
  const pair=[e.left_plate,e.right_plate].filter(Boolean).join(" / ")||"—";
  $("eventPanel").innerHTML=`<div class="event-title"><div class="mag-badge" style="color:${colorForMag(e.magnitude)}">M${fmt(e.magnitude,1)}</div><div><h2>${esc(e.place)}</h2><p>${dateFmt(e.time)} · ${esc(e.magnitude_type||"")} · ${esc(e.event_type||"")}</p></div></div><div class="facts"><div class="fact"><small>Depth</small><strong>${fmt(e.depth_km,1)} km</strong></div><div class="fact"><small>Coordinates</small><strong>${fmt(e.latitude,2)}, ${fmt(e.longitude,2)}</strong></div><div class="fact"><small>PB2002 boundary</small><strong>${esc(e.boundary_id||"Unassigned")}</strong></div><div class="fact"><small>Plate pair</small><strong>${esc(pair)}</strong></div><div class="fact"><small>Boundary class</small><strong>${esc(e.boundary_class||"—")}</strong></div><div class="fact"><small>Boundary distance</small><strong>${e.distance_to_boundary_km==null?"—":fmt(e.distance_to_boundary_km,1)+" km"}</strong></div><div class="fact"><small>Nearest GEM fault</small><strong>${esc(e.fault_name||"No match ≤250 km")}</strong></div><div class="fact"><small>Fault distance</small><strong>${e.distance_to_fault_km==null?"—":fmt(e.distance_to_fault_km,1)+" km"}</strong></div></div><div class="muted">Event ID: ${esc(e.event_id)}</div>${e.magnitude>=7&&e.event_type==="earthquake"?`<button class="major-link" id="openMajor">Open major-event drilldown →</button>`:""}`;
  const b=$("openMajor"); if(b) b.addEventListener("click",()=>{ setView("major"); selectMajor(e.event_id); });
}

function renderTable(){
  const rows=state.filtered.slice(0,state.tableLimit); $("eventRows").innerHTML=rows.map(e=>`<tr data-id="${esc(e.event_id)}"><td><strong style="color:${colorForMag(e.magnitude)}">M${fmt(e.magnitude,1)}</strong></td><td>${dateFmt(e.time)}</td><td>${esc(e.place)}</td><td>${fmt(e.depth_km,1)} km</td><td>${esc(e.boundary_id||"—")}</td><td>${esc(e.boundary_class||"—")}</td><td>${esc(e.fault_name||"—")}</td></tr>`).join("");
  $("tableCaption").textContent=`Showing ${fmt(rows.length)} of ${fmt(state.filtered.length)}`; $("showMoreEvents").hidden=rows.length>=state.filtered.length;
  $("eventRows").querySelectorAll("tr").forEach(r=>r.addEventListener("click",()=>selectEvent(r.dataset.id,true)));
}

function renderExplorerCharts(){
  const years=[]; for(let y=1976;y<=2025;y++) years.push(y); const counts=Object.fromEntries(years.map(y=>[y,0])); state.filtered.forEach(e=>{ const y=yearOf(e); if(counts[y]!=null) counts[y]++; });
  destroyChart("timeline"); state.charts.timeline=new Chart($("timelineChart"),{type:"bar",data:{labels:years,datasets:[{label:"Filtered records",data:years.map(y=>counts[y]),backgroundColor:"#4b8fa0"}]},options:chartBase()});
  const bins=["6.0–6.4","6.5–6.9","7.0–7.4","7.5–7.9","8.0–8.4","8.5–8.9","9.0+"]; const bc=Array(7).fill(0); state.filtered.forEach(e=>{ const m=e.magnitude; let i=m>=9?6:m>=8.5?5:m>=8?4:m>=7.5?3:m>=7?2:m>=6.5?1:0; bc[i]++; });
  destroyChart("mag"); state.charts.mag=new Chart($("magnitudeChart"),{type:"bar",data:{labels:bins,datasets:[{label:"Records",data:bc,backgroundColor:["#67a9f6","#5c9ddf","#f1b35b","#e39a52","#f06f69","#dc5e79","#b88cf3"]}]},options:chartBase()});
}

function setView(name){ const b=document.querySelector(`.tab[data-view="${name}"]`); if(b) b.click(); }

function initMajorControls(){
  $("majorSearch").addEventListener("input",debounce(renderMajorList,160));
  document.querySelectorAll("[data-major-min]").forEach(b=>b.addEventListener("click",()=>{ state.majorMin=Number(b.dataset.majorMin); document.querySelectorAll("[data-major-min]").forEach(x=>x.classList.toggle("active",x===b)); renderMajorList(); }));
  $("majorTimeWindow").addEventListener("change",renderSelectedMajor);
}

function majorEvents(){ const q=$("majorSearch").value.trim().toLowerCase(); return state.events.filter(e=>e.event_type==="earthquake"&&e.magnitude>=state.majorMin&&(!q||`${e.place} ${e.event_id}`.toLowerCase().includes(q))).sort((a,b)=>(b.magnitude-a.magnitude)||(new Date(b.time)-new Date(a.time))); }
function renderMajorList(){ const list=majorEvents(); $("majorList").innerHTML=list.map(e=>`<div class="major-item ${state.selectedMajor===e.event_id?"active":""}" data-id="${esc(e.event_id)}"><strong style="color:${colorForMag(e.magnitude)}">M${fmt(e.magnitude,1)}</strong><span>${esc(e.place)}</span><small>${dateFmt(e.time)} · ${esc(e.boundary_class||"No PB2002 class")}</small></div>`).join(""); $("majorList").querySelectorAll(".major-item").forEach(x=>x.addEventListener("click",()=>selectMajor(x.dataset.id))); if(!state.selectedMajor&&list.length) selectMajor(list[0].event_id); }
function selectMajor(id){ state.selectedMajor=id; renderMajorList(); renderSelectedMajor(); }

function relationshipsFor(id){ return state.majorPairs.map(p=>{ if(p.earlier_event_id===id) return {...p,other_id:p.later_event_id,signed_lag:p.lag_days,direction:"after"}; if(p.later_event_id===id) return {...p,other_id:p.earlier_event_id,signed_lag:-p.lag_days,direction:"before"}; return null; }).filter(Boolean).sort((a,b)=>Math.abs(a.signed_lag)-Math.abs(b.signed_lag)); }

function renderSelectedMajor(){
  const e=state.byId.get(state.selectedMajor); if(!e) return; const rel=relationshipsFor(e.event_id), time=Number($("majorTimeWindow").value), windows=state.majorWindows.filter(w=>w.source_event_id===e.event_id&&w.time_window_days===time).sort((a,b)=>a.distance_window_km-b.distance_window_km);
  const w250=windows.find(w=>w.distance_window_km===250), pair=[e.left_plate,e.right_plate].filter(Boolean).join(" / ")||"—";
  $("majorHero").innerHTML=`<div class="major-hero-grid"><div class="event-title"><div class="mag-badge" style="color:${colorForMag(e.magnitude)}">M${fmt(e.magnitude,1)}</div><div><span class="kicker">${dateFmt(e.time)}</span><h2>${esc(e.place)}</h2><p>${esc(e.boundary_id||"No PB2002 assignment")} · ${esc(pair)} · ${esc(e.boundary_class||"—")}</p></div></div><div class="hero-stat"><small>Depth</small><strong>${fmt(e.depth_km,1)} km</strong></div><div class="hero-stat"><small>Boundary offset</small><strong>${fmt(e.distance_to_boundary_km,1)} km</strong></div><div class="hero-stat"><small>${time}d ≤250 km along</small><strong>${w250?`${w250.post_count_along_boundary}/${w250.pre_count_along_boundary}`:"—"}</strong></div><div class="hero-stat"><small>Routed relationships</small><strong>${fmt(rel.length)}</strong></div></div>`;
  renderMajorWindowChart(windows); renderRelations(rel);
}

function renderMajorWindowChart(rows){
  destroyChart("majorWindow"); const labels=rows.map(w=>`≤${fmt(w.distance_window_km)} km`);
  state.charts.majorWindow=new Chart($("majorWindowChart"),{type:"bar",data:{labels,datasets:[{label:"Along pre",data:rows.map(w=>w.pre_count_along_boundary),backgroundColor:"#315d66"},{label:"Along post",data:rows.map(w=>w.post_count_along_boundary),backgroundColor:"#56d6c4"},{label:"Radial pre",data:rows.map(w=>w.pre_count_routed_radial),backgroundColor:"#5b4d72"},{label:"Radial post",data:rows.map(w=>w.post_count_routed_radial),backgroundColor:"#b88cf3"}]},options:chartBase()});
}
function renderRelations(rel){
  $("relationCount").textContent=`${fmt(rel.length)} routed`; const points=rel.filter(r=>r.within_along_boundary_limit&&Number.isFinite(r.along_boundary_distance_km));
  destroyChart("relations"); const opts=chartBase(); opts.scales.x.title={display:true,text:"Days before / after source",color:"#8298a4"}; opts.scales.y.title={display:true,text:"Along-boundary distance (km)",color:"#8298a4"};
  state.charts.relations=new Chart($("relationScatter"),{type:"scatter",data:{datasets:[{label:"Before",data:points.filter(r=>r.direction==="before").map(r=>({x:r.signed_lag,y:r.along_boundary_distance_km})),backgroundColor:"#67a9f6"},{label:"After",data:points.filter(r=>r.direction==="after").map(r=>({x:r.signed_lag,y:r.along_boundary_distance_km})),backgroundColor:"#f1b35b"}]},options:opts});
  $("relationRows").innerHTML=rel.slice(0,120).map(r=>{ const o=state.byId.get(r.other_id)||{}; return `<tr data-id="${esc(r.other_id)}"><td>${r.direction}</td><td>M${fmt(o.magnitude??(r.direction==="after"?r.later_magnitude:r.earlier_magnitude),1)}</td><td>${esc(o.place||r.other_id)}</td><td>${r.signed_lag>=0?"+":""}${fmt(r.signed_lag,1)} d</td><td>${fmt(r.radial_distance_km,0)} km</td><td>${fmt(r.along_boundary_distance_km,0)} km</td><td>${r.same_boundary_id?"yes":"no"}</td></tr>`; }).join("");
  $("relationRows").querySelectorAll("tr").forEach(r=>r.addEventListener("click",()=>{ setView("explorer"); selectEvent(r.dataset.id,true); }));
}

function initStudyControls(){ ["studyMagnitude","studyTime","studyDistance"].forEach(id=>$(id).addEventListener("change",renderStudy)); }
function finite(v){ return v!=null&&Number.isFinite(Number(v)); }
function pearson(xs,ys){ const n=xs.length;if(!n)return null;const mx=xs.reduce((a,b)=>a+b,0)/n,my=ys.reduce((a,b)=>a+b,0)/n;let num=0,dx=0,dy=0;for(let i=0;i<n;i++){const a=xs[i]-mx,b=ys[i]-my;num+=a*b;dx+=a*a;dy+=b*b}return num/Math.sqrt(dx*dy); }
function renderStudy(){
  const a=state.study.along_boundary, stats=a.source_magnitude_statistics, ann=a.annular_statistics;
  const m8=stats.find(x=>x.source_minimum_magnitude===8&&x.time_window_days===1&&x.distance_window_km===250);
  $("studyM8Along").textContent=ratioText(m8?.post_to_pre_along_boundary_ratio); $("studyM8Radial").textContent=ratioText(m8?.post_to_pre_routed_radial_ratio); $("studyWithinLimit").textContent=fmt(a.coverage.within_along_boundary_limit_pair_count);
  const valid=stats.filter(x=>finite(x.post_to_pre_along_boundary_ratio)&&finite(x.post_to_pre_routed_radial_ratio)); const corr=pearson(valid.map(x=>Number(x.post_to_pre_along_boundary_ratio)),valid.map(x=>Number(x.post_to_pre_routed_radial_ratio))); $("studyCorrelation").textContent=corr?.toFixed(3)||"—";
  const mag=Number($("studyMagnitude").value), time=Number($("studyTime").value), dist=Number($("studyDistance").value);
  const ar=ann.filter(x=>x.source_minimum_magnitude===mag&&x.time_window_days===time).sort((x,y)=>x.distance_min_km-y.distance_min_km);
  destroyChart("annular"); const ao=chartBase(); ao.scales.y.title={display:true,text:"Post / pre ratio",color:"#8298a4"}; ao.plugins.annotation=undefined; state.charts.annular=new Chart($("annularChart"),{type:"bar",data:{labels:ar.map(x=>`${fmt(x.distance_min_km)}–${fmt(x.distance_max_km)} km`),datasets:[{label:"Along boundary",data:ar.map(x=>x.post_to_pre_along_boundary_ratio),backgroundColor:"#56d6c4"},{label:"Matched radial",data:ar.map(x=>x.post_to_pre_routed_radial_ratio),backgroundColor:"#b88cf3"}]},options:ao});
  const tr=stats.filter(x=>x.source_minimum_magnitude===mag&&x.distance_window_km===dist).sort((x,y)=>x.time_window_days-y.time_window_days);
  destroyChart("decay"); state.charts.decay=new Chart($("timeDecayChart"),{type:"line",data:{labels:tr.map(x=>`${fmt(x.time_window_days)}d`),datasets:[{label:"Along boundary",data:tr.map(x=>x.post_to_pre_along_boundary_ratio),borderColor:"#56d6c4",backgroundColor:"#56d6c4",tension:.2},{label:"Matched radial",data:tr.map(x=>x.post_to_pre_routed_radial_ratio),borderColor:"#b88cf3",backgroundColor:"#b88cf3",tension:.2}]},options:chartBase()});
  destroyChart("cells"); const so=chartBase(); so.scales.x.title={display:true,text:"Matched radial ratio",color:"#8298a4"}; so.scales.y.title={display:true,text:"Along-boundary ratio",color:"#8298a4"}; state.charts.cells=new Chart($("cellScatter"),{type:"scatter",data:{datasets:[{label:"Study cells",data:valid.map(x=>({x:x.post_to_pre_routed_radial_ratio,y:x.post_to_pre_along_boundary_ratio})),backgroundColor:"#f1b35b"}]},options:so});
}

function initDataView(){
  $("rawFiles").innerHTML=RAW_FILES.map(n=>`<a href="data/raw/${n}" download><span>${esc(n)}</span><b>download ↓</b></a>`).join("");
  const citations=state.study.metadata.source_citations||[]; $("citations").innerHTML=citations.map(c=>{ const x=c.citation||{}; return `<div><strong>${esc(x.formatted||x.title||c.source_key)}</strong><small>${x.doi?`DOI ${esc(x.doi)}`:""}${c.license||c.distribution_license?` · ${esc(c.license||c.distribution_license)}`:""}</small></div>`; }).join("");
  $("limitations").innerHTML=(state.study.along_boundary.limitations||[]).map(x=>`<li>${esc(x)}</li>`).join("");
}

function debounce(fn,ms){ let t; return (...args)=>{clearTimeout(t);t=setTimeout(()=>fn(...args),ms)}; }

load();
