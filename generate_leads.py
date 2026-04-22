"""
generate_leads.py — Builds the standalone new-facility leads site (leads.html).
"""
import json, os
from datetime import date
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NF_CSV     = os.path.join(SCRIPT_DIR, "new_facilities.csv")
OUT_HTML   = os.path.join(SCRIPT_DIR, "leads.html")

print("generate_leads.py — building leads.html")

if not os.path.exists(NF_CSV):
    print(f"  ERROR: {NF_CSV} not found"); raise SystemExit(1)

df = pd.read_csv(NF_CSV, dtype=str)
records  = df.fillna("").to_dict("records")
today    = str(date.today())
n_total  = len(records)
n_fresh  = sum(1 for r in records if int(r.get("days_since_enrollment") or 99) <= 14)
n_standalone = sum(1 for r in records if r.get("group_indicator","") == "Standalone")
n_group      = n_total - n_standalone
print(f"  Records: {n_total:,}  fresh: {n_fresh:,}  standalone: {n_standalone:,}  group: {n_group:,}")

nf_json = json.dumps(records, ensure_ascii=False)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>New Facility Leads — Daniels Health</title>
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;font-size:13px;background:#f0f2f6;color:#1a1a2e}}

    header{{background:#1a1a2e;color:#fff;padding:14px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}}
    header h1{{font-size:18px;font-weight:700}}
    header .sub{{font-size:11px;color:#9ba4c0;margin-top:2px}}
    .export-btn{{padding:7px 16px;background:#4a6cf7;color:#fff;border:none;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer}}
    .export-btn:hover{{background:#3a5ce7}}

    .stats{{display:flex;gap:12px;padding:16px 24px;flex-wrap:wrap}}
    .stat-card{{background:#fff;border-radius:10px;padding:14px 20px;flex:1;min-width:130px;box-shadow:0 1px 4px rgba(0,0,0,.07);border-left:4px solid #4a6cf7}}
    .stat-card.green{{border-left-color:#2e7d32}}
    .stat-card.orange{{border-left-color:#e65100}}
    .stat-card.purple{{border-left-color:#6a1b9a}}
    .stat-card .val{{font-size:26px;font-weight:700;line-height:1.1}}
    .stat-card .lbl{{font-size:11px;color:#666;margin-top:3px}}

    .controls{{background:#fff;border-bottom:1px solid #dde2ec;padding:10px 24px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;position:sticky;top:0;z-index:10;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
    .control-group{{display:flex;align-items:center;gap:5px}}
    .controls label{{font-size:11px;font-weight:600;color:#555;white-space:nowrap}}
    input[type=text]{{padding:6px 10px;border:1px solid #ccd0da;border-radius:6px;font-size:12px;width:190px;outline:none}}
    input[type=text]:focus{{border-color:#4a6cf7}}
    select{{padding:6px 8px;border:1px solid #ccd0da;border-radius:6px;font-size:12px;background:#fff;cursor:pointer;outline:none}}
    select:focus{{border-color:#4a6cf7}}
    .row-count{{margin-left:auto;font-size:11px;color:#666;white-space:nowrap;font-weight:600}}

    .table-wrap{{padding:16px 24px 40px;overflow-x:auto}}
    table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
    thead tr{{background:#1a1a2e;color:#fff}}
    th{{padding:9px 11px;text-align:left;font-size:11px;font-weight:600;letter-spacing:.3px;white-space:nowrap;cursor:pointer;user-select:none}}
    th:hover{{background:#2c2c4e}}
    th.sort-asc::after{{content:" ▲";font-size:9px}}
    th.sort-desc::after{{content:" ▼";font-size:9px}}
    td{{padding:8px 11px;border-bottom:1px solid #eef0f5;vertical-align:middle;font-size:12px}}
    tbody tr:last-child td{{border-bottom:none}}
    tbody tr:hover{{filter:brightness(0.97)}}

    tr.fresh  {{background:#e8f5e9}}
    tr.recent {{background:#fffde7}}
    tr.older  {{background:#fff}}

    .org-name{{font-weight:600;color:#1a1a2e;line-height:1.3}}
    .addr{{font-size:11px;color:#666;margin-top:2px;line-height:1.4}}
    .phone-link{{color:#1a6ef7;text-decoration:none;font-weight:500;white-space:nowrap}}
    .phone-link:hover{{text-decoration:underline}}
    .contact-name{{font-weight:500}}
    .contact-title{{font-size:11px;color:#888}}

    /* Facility type badges */
    .badge{{display:inline-block;padding:3px 8px;border-radius:12px;font-size:10px;font-weight:700;white-space:nowrap}}
    .badge.home-health{{background:#e3f2fd;color:#0d47a1}}
    .badge.skilled-nursing{{background:#fce4ec;color:#880e4f}}
    .badge.assisted-living{{background:#f3e5f5;color:#4a148c}}
    .badge.clinical-lab{{background:#e8f5e9;color:#1b5e20}}
    .badge.urgent-care{{background:#fff3e0;color:#e65100}}
    .badge.asc{{background:#e0f7fa;color:#006064}}
    .badge.esrd{{background:#fbe9e7;color:#bf360c}}
    .badge.hospital{{background:#e8eaf6;color:#1a237e}}
    .badge.default{{background:#f5f5f5;color:#333}}

    /* Group indicator badges */
    .grp-badge{{display:inline-block;padding:3px 9px;border-radius:12px;font-size:10px;font-weight:700;white-space:nowrap;max-width:220px;overflow:hidden;text-overflow:ellipsis}}
    .grp-standalone{{background:#e8f5e9;color:#1b5e20}}
    .grp-subpart{{background:#fce4ec;color:#880e4f}}
    .grp-owner{{background:#fff3e0;color:#e65100}}
    .parent-name{{font-size:10px;color:#666;margin-top:2px;font-style:italic;max-width:220px;white-space:normal;line-height:1.3}}

    .days-badge{{display:inline-block;padding:3px 8px;border-radius:10px;font-size:11px;font-weight:700;text-align:center}}
    .days-fresh {{background:#c8e6c9;color:#1b5e20}}
    .days-recent{{background:#fff9c4;color:#f57f17}}
    .days-old   {{background:#f5f5f5;color:#555}}

    .partial-flag{{font-size:10px;color:#e65100;font-weight:600}}
    .npi-link{{font-family:monospace;font-size:11px;color:#4a6cf7;text-decoration:none}}
    .npi-link:hover{{text-decoration:underline}}
    .empty-msg{{text-align:center;padding:48px;color:#999;font-size:14px;display:none}}
    .legend{{padding:6px 24px 12px;display:flex;gap:16px;flex-wrap:wrap;font-size:11px;color:#555;align-items:center}}
    .legend-item{{display:flex;align-items:center;gap:5px}}
    .swatch{{width:11px;height:11px;border-radius:2px;display:inline-block}}
  </style>
</head>
<body>

<header>
  <div>
    <h1>New Facility Leads</h1>
    <div class="sub">Newly enrolled healthcare organizations · NPPES NPI Registry · 90-day window · Updated {today}</div>
  </div>
  <button class="export-btn" onclick="exportCsv()">⬇ Export CSV</button>
</header>

<div class="stats">
  <div class="stat-card">
    <div class="val" id="statTotal">{n_total:,}</div>
    <div class="lbl">Total Leads</div>
  </div>
  <div class="stat-card green">
    <div class="val" id="statFresh">{n_fresh:,}</div>
    <div class="lbl">New in Last 14 Days</div>
  </div>
  <div class="stat-card purple">
    <div class="val" id="statStandalone">{n_standalone:,}</div>
    <div class="lbl">Standalone</div>
  </div>
  <div class="stat-card orange">
    <div class="val" id="statShowing">—</div>
    <div class="lbl">Showing (filtered)</div>
  </div>
</div>

<div class="controls">
  <div class="control-group"><label>🔍</label><input type="text" id="search" placeholder="Search org, city, parent…" oninput="render()"/></div>
  <div class="control-group"><label for="selType">Type</label><select id="selType" onchange="render()"><option value="">All Types</option></select></div>
  <div class="control-group"><label for="selState">State</label><select id="selState" onchange="render()"><option value="">All States</option></select></div>
  <div class="control-group"><label for="selRecency">Recency</label>
    <select id="selRecency" onchange="render()">
      <option value="">All</option>
      <option value="14">≤ 14 days</option>
      <option value="30">≤ 30 days</option>
      <option value="60">≤ 60 days</option>
    </select>
  </div>
  <div class="control-group"><label for="selGroup">Group</label>
    <select id="selGroup" onchange="render()">
      <option value="">All</option>
      <option value="standalone">Standalone only</option>
      <option value="group">Group / Subpart only</option>
    </select>
  </div>
  <span class="row-count" id="rowCount"></span>
</div>

<div class="legend">
  <span style="font-weight:600;color:#333">Row color:</span>
  <span class="legend-item"><span class="swatch" style="background:#e8f5e9;border:1px solid #a5d6a7"></span> ≤ 14 days</span>
  <span class="legend-item"><span class="swatch" style="background:#fffde7;border:1px solid #ffe082"></span> 15–30 days</span>
  <span class="legend-item"><span class="swatch" style="background:#fff;border:1px solid #ddd"></span> 31+ days</span>
  &nbsp;·&nbsp;
  <span class="legend-item"><span class="grp-badge grp-standalone">Standalone</span></span>
  <span class="legend-item"><span class="grp-badge grp-subpart">Part of group</span> NPPES-reported subpart</span>
  <span class="legend-item"><span class="grp-badge grp-owner">Group — N locations</span> same owner or shared phone detected</span>
</div>

<div class="table-wrap">
  <table id="leadsTable">
    <thead><tr>
      <th data-col="organization_name">Organization</th>
      <th data-col="phone">Phone</th>
      <th data-col="city">City</th>
      <th data-col="state">ST</th>
      <th data-col="taxonomy_description">Facility Type</th>
      <th data-col="authorized_official">Contact</th>
      <th data-col="group_indicator">Standalone / Group</th>
      <th data-col="enumeration_date">Enrolled</th>
      <th data-col="days_since_enrollment">Days Ago</th>
      <th data-col="npi">NPI</th>
    </tr></thead>
    <tbody id="leadsBody"></tbody>
  </table>
  <p class="empty-msg" id="emptyMsg">No matching leads found.</p>
</div>

<script>
const DATA = {nf_json};

const TYPE_BADGE = {{
  "Home Health":"home-health","Home Health — Supports":"home-health",
  "Skilled Nursing Facility":"skilled-nursing","Hospice — Inpatient":"skilled-nursing","Intermediate Care Facility":"skilled-nursing",
  "Assisted Living Facility":"assisted-living",
  "Clinical Medical Laboratory":"clinical-lab",
  "Urgent Care Center":"urgent-care",
  "Ambulatory Surgery Center":"asc",
  "Dialysis / ESRD Treatment Facility":"esrd",
  "General Acute Care Hospital":"hospital","General Acute Care Hospital — Women's":"hospital",
  "Outpatient Clinic":"default",
}};

function esc(s){{return String(s??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}}
function fmtPhone(p){{
  const d=(p||"").replace(/\\D/g,"");
  if(d.length===10) return `(${{d.slice(0,3)}}) ${{d.slice(3,6)}}-${{d.slice(6)}}`;
  if(d.length===11&&d[0]==="1") return `(${{d.slice(1,4)}}) ${{d.slice(4,7)}}-${{d.slice(7)}}`;
  return p||"";
}}
function grpBadge(gi){{
  if(!gi||gi==="Standalone") return `<span class="grp-badge grp-standalone">Standalone</span>`;
  if(gi.startsWith("Part of group:")){{
    const parent=gi.slice("Part of group:".length).trim();
    return `<span class="grp-badge grp-subpart">Part of group</span><div class="parent-name">${{esc(parent)}}</div>`;
  }}
  if(gi==="Part of group") return `<span class="grp-badge grp-subpart">Part of group</span>`;
  if(gi.includes("shared phone")) return `<span class="grp-badge grp-owner">${{esc(gi)}}</span><div class="parent-name" style="color:#b45309">Same central phone — likely same entity</div>`;
  if(gi.startsWith("Group —")) return `<span class="grp-badge grp-owner">${{esc(gi)}}</span>`;
  return `<span class="grp-badge grp-standalone">${{esc(gi)}}</span>`;
}}

let sortCol="enumeration_date", sortAsc=false;

(function init(){{
  const typeEl=document.getElementById("selType"), stateEl=document.getElementById("selState");
  [...new Set(DATA.map(r=>r.taxonomy_description))].sort().forEach(t=>{{const o=document.createElement("option");o.value=o.textContent=t;typeEl.appendChild(o);}});
  [...new Set(DATA.map(r=>r.state))].sort().forEach(s=>{{const o=document.createElement("option");o.value=o.textContent=s;stateEl.appendChild(o);}});
}})();

document.querySelectorAll("th[data-col]").forEach(th=>{{
  th.addEventListener("click",()=>{{
    if(sortCol===th.dataset.col) sortAsc=!sortAsc; else{{sortCol=th.dataset.col;sortAsc=true;}}
    render();
  }});
}});

function render(){{
  const search  =document.getElementById("search").value.toLowerCase().trim();
  const selType =document.getElementById("selType").value;
  const selState=document.getElementById("selState").value;
  const selRec  =parseInt(document.getElementById("selRecency").value)||0;
  const selGrp  =document.getElementById("selGroup").value;
  const numCols =["days_since_enrollment"];

  let rows=DATA.filter(r=>{{
    const gi=r.group_indicator||"";
    const isStandalone=!gi||gi==="Standalone";
    if(selGrp==="standalone"&&!isStandalone) return false;
    if(selGrp==="group"&&isStandalone) return false;
    return (
      (!search||(r.organization_name||"").toLowerCase().includes(search)||(r.city||"").toLowerCase().includes(search)||(r.authorized_official||"").toLowerCase().includes(search)||(r.parent_org||"").toLowerCase().includes(search))
      &&(!selType||r.taxonomy_description===selType)
      &&(!selState||r.state===selState)
      &&(!selRec||parseInt(r.days_since_enrollment||999)<=selRec)
    );
  }});

  rows.sort((a,b)=>{{
    let va=a[sortCol]??"",vb=b[sortCol]??"";
    if(numCols.includes(sortCol)){{va=parseFloat(va)||0;vb=parseFloat(vb)||0;}}
    else{{va=String(va).toLowerCase();vb=String(vb).toLowerCase();}}
    return va<vb?(sortAsc?-1:1):va>vb?(sortAsc?1:-1):0;
  }});

  const tbody=document.getElementById("leadsBody");tbody.innerHTML="";
  rows.forEach(r=>{{
    const days=parseInt(r.days_since_enrollment||99);
    const rowCls=days<=14?"fresh":days<=30?"recent":"older";
    const daysCls=days<=14?"days-fresh":days<=30?"days-recent":"days-old";
    const phone=fmtPhone(r.phone);
    const phoneHref=phone?`tel:${{(r.phone||"").replace(/\\D/g,"")}}`:"";
    const tr=document.createElement("tr");tr.className=rowCls;
    tr.innerHTML=`
      <td>
        <div class="org-name">${{esc(r.organization_name)}}</div>
        <div class="addr">${{esc(r.practice_address)}}, ${{esc(r.city)}}, ${{esc(r.state)}} ${{esc(r.zip)}}</div>
      </td>
      <td>${{phone?`<a class="phone-link" href="${{phoneHref}}">${{esc(phone)}}</a>`:"—"}}</td>
      <td>${{esc(r.city)}}</td>
      <td>${{esc(r.state)}}</td>
      <td><span class="badge ${{TYPE_BADGE[r.taxonomy_description]||"default"}}">${{esc(r.taxonomy_description)}}</span></td>
      <td>
        ${{r.authorized_official?`<div class="contact-name">${{esc(r.authorized_official)}}</div>`:"—"}}
        ${{r.official_title?`<div class="contact-title">${{esc(r.official_title)}}</div>`:""}}
      </td>
      <td>${{grpBadge(r.group_indicator)}}</td>
      <td style="white-space:nowrap">${{esc(r.enumeration_date)}}</td>
      <td><span class="days-badge ${{daysCls}}">${{days}}</span></td>
      <td><a class="npi-link" href="https://npiregistry.cms.hhs.gov/search?number=${{esc(r.npi)}}" target="_blank" rel="noopener">${{esc(r.npi)}}</a></td>`;
    tbody.appendChild(tr);
  }});

  document.getElementById("emptyMsg").style.display=rows.length?"none":"block";
  document.getElementById("rowCount").textContent=`${{rows.length.toLocaleString()}} of ${{DATA.length.toLocaleString()}} leads`;
  document.getElementById("statShowing").textContent=rows.length.toLocaleString();
  document.querySelectorAll("th[data-col]").forEach(th=>{{
    th.classList.remove("sort-asc","sort-desc");
    if(th.dataset.col===sortCol)th.classList.add(sortAsc?"sort-asc":"sort-desc");
  }});
}}

function exportCsv(){{
  const search  =document.getElementById("search").value.toLowerCase().trim();
  const selType =document.getElementById("selType").value;
  const selState=document.getElementById("selState").value;
  const selRec  =parseInt(document.getElementById("selRecency").value)||0;
  const selGrp  =document.getElementById("selGroup").value;
  let rows=DATA.filter(r=>{{
    const gi=r.group_indicator||"";
    const isStandalone=!gi||gi==="Standalone";
    if(selGrp==="standalone"&&!isStandalone) return false;
    if(selGrp==="group"&&isStandalone) return false;
    return(!search||(r.organization_name||"").toLowerCase().includes(search)||(r.city||"").toLowerCase().includes(search)||(r.authorized_official||"").toLowerCase().includes(search)||(r.parent_org||"").toLowerCase().includes(search))&&(!selType||r.taxonomy_description===selType)&&(!selState||r.state===selState)&&(!selRec||parseInt(r.days_since_enrollment||999)<=selRec);
  }});
  const cols=["organization_name","practice_address","city","state","zip","phone","authorized_official","official_title","group_indicator","parent_org","taxonomy_description","enumeration_date","days_since_enrollment","npi"];
  const csvRows=rows.map(r=>cols.map(c=>{{const v=String(r[c]??"");return v.includes(",")||v.includes('"')?`"${{v.replace(/"/g,'""')}}"`:v;}}).join(","));
  const blob=new Blob([cols.join(",")+"\\n"+csvRows.join("\\n")],{{type:"text/csv"}});
  const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="facility_leads_{today}.csv";a.click();
}}

render();
</script>
</body>
</html>"""

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)
print(f"  leads.html written — {n_total:,} records")
