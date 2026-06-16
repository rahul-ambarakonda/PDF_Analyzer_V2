"""Browser UI for folder-batch comparison.

Upload a folder of reference PDFs and a folder of candidate PDFs; files are paired by
filename (legacy behaviour), each pair is run through the comparison pipeline, and the
per-pair HTML reports are served back with a summary table.

Run:  python -m comparator.web   (then open http://127.0.0.1:5000)
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file
from werkzeug.utils import secure_filename

from .config import Config
from .pipeline import run_comparison, write_reports
from .report import CLASS_COLOR

_DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"
_RUNS_ROOT = Path(tempfile.mkdtemp(prefix="comparator_web_"))
_RUNS: dict[str, dict[str, Path]] = {}  # run_id -> {display_name: pair_dir}


def create_app(config_path: str | os.PathLike | None = None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024  # 512 MB upload cap
    cfg_path = Path(config_path or os.environ.get("COMPARATOR_CONFIG", _DEFAULT_CONFIG))

    @app.get("/")
    def index():
        return INDEX_HTML

    @app.post("/compare")
    def compare():
        config = Config.load(cfg_path)
        ref_files = {os.path.basename(f.filename): f for f in request.files.getlist("reference")
                     if f.filename and f.filename.lower().endswith(".pdf")}
        cand_files = {os.path.basename(f.filename): f for f in request.files.getlist("candidate")
                      if f.filename and f.filename.lower().endswith(".pdf")}
        if not ref_files or not cand_files:
            return jsonify({"error": "Upload at least one reference PDF and one candidate PDF."}), 400

        matched = sorted(set(ref_files) & set(cand_files))
        if not matched:
            return jsonify({"error": "No filenames match between the reference and candidate sets."}), 400

        run_id = uuid.uuid4().hex[:12]
        run_dir = _RUNS_ROOT / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        _RUNS[run_id] = {}

        pairs = []
        for name in matched:
            pair_dir = run_dir / (secure_filename(name) or "pair")
            pair_dir.mkdir(parents=True, exist_ok=True)
            ref_path = pair_dir / "reference.pdf"
            cand_path = pair_dir / "candidate.pdf"
            ref_files[name].save(ref_path)
            cand_files[name].seek(0)
            cand_files[name].save(cand_path)
            try:
                report = run_comparison(str(ref_path), str(cand_path), config)
                write_reports(report, str(cand_path), config, pair_dir)
            except Exception as exc:  # surface per-file failure without aborting the batch
                pairs.append({"name": name, "error": str(exc)})
                continue
            _RUNS[run_id][name] = pair_dir
            m = report["meta"]
            pairs.append({
                "name": name,
                "total": m["total_defects"],
                "defect": m["counts_by_status"]["defect"],
                "review": m["counts_by_status"]["review"],
                "status": "defect" if m["counts_by_status"]["defect"] else "clean",
                "report_url": f"/report/{run_id}/{name}",
            })

        return jsonify({
            "run_id": run_id,
            "pairs": pairs,
            "unmatched_reference": sorted(set(ref_files) - set(cand_files)),
            "unmatched_candidate": sorted(set(cand_files) - set(ref_files)),
        })

    @app.get("/report/<run_id>/<path:name>")
    def report(run_id: str, name: str):
        pair_dir = _RUNS.get(run_id, {}).get(name)
        if pair_dir is None:
            abort(404)
        html = pair_dir / "report.html"
        if not html.exists():
            abort(404)
        return send_file(html)

    return app


_dots = "".join(
    f'<span class="dot" style="background:rgb{c}"></span>{n.replace("_"," ")} '
    for n, c in CLASS_COLOR.items()
)

INDEX_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Text-Fidelity Comparator</title>
<style>
 body{font-family:system-ui,sans-serif;background:#0b0f19;color:#e5e7eb;margin:0;padding:40px}
 .wrap{max-width:1000px;margin:0 auto}
 h1{font-size:1.6rem;margin:0 0 6px}
 p.sub{color:#9ca3af;margin:0 0 28px}
 .pickers{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:20px}
 .card{flex:1;min-width:280px;background:#141b2d;border:1px solid #243049;border-radius:12px;padding:20px}
 .card h2{font-size:1rem;margin:0 0 4px}.card p{color:#9ca3af;font-size:.82rem;margin:0 0 12px}
 input[type=file]{width:100%;color:#cbd5e1;font-size:.85rem}
 .count{font-size:.8rem;color:#a5b4fc;margin-top:8px;min-height:1em}
 button{appearance:none;border:none;border-radius:999px;padding:13px 28px;font-weight:700;font-size:.95rem;
   cursor:pointer;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff}
 button:disabled{opacity:.6;cursor:wait}
 .legend{font-size:.75rem;color:#9ca3af;margin:14px 0 24px}
 .dot{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 5px 0 12px;vertical-align:middle}
 table{width:100%;border-collapse:collapse;margin-top:10px;font-size:.88rem}
 th,td{text-align:left;padding:10px 12px;border-bottom:1px solid #243049}
 th{color:#9ca3af;text-transform:uppercase;font-size:.7rem;letter-spacing:.5px}
 .st-defect{color:#ef4444;font-weight:700}.st-clean{color:#10b981;font-weight:700}.st-error{color:#f59e0b;font-weight:700}
 a.view{color:#a5b4fc;font-weight:700;text-decoration:none}
 .warn{background:#3b2f15;border:1px solid #6b5121;color:#fcd34d;border-radius:8px;padding:10px 14px;margin-top:16px;font-size:.82rem}
 .err{background:#3b1518;border:1px solid #7f1d1d;color:#fca5a5;border-radius:8px;padding:10px 14px;margin-top:16px;font-size:.85rem}
 #status{margin-top:16px;color:#9ca3af}
</style></head><body><div class="wrap">
<h1>🔍 Text-Fidelity Comparator</h1>
<p class="sub">Upload a reference folder and a candidate (Creo) folder. PDFs are paired by filename and compared.</p>
<div class="pickers">
 <div class="card"><h2>Reference folder</h2><p>Correct / legacy CAD exports</p>
   <input id="ref" type="file" webkitdirectory multiple accept="application/pdf"><div class="count" id="refCount"></div></div>
 <div class="card"><h2>Candidate folder</h2><p>Creo exports under review</p>
   <input id="cand" type="file" webkitdirectory multiple accept="application/pdf"><div class="count" id="candCount"></div></div>
</div>
<button id="go">Compare</button>
<div class="legend">Defect classes: """ + _dots + """</div>
<div id="status"></div>
<div id="results"></div>
</div>
<script>
const $=id=>document.getElementById(id);
const pdfs=inp=>[...inp.files].filter(f=>f.name.toLowerCase().endsWith('.pdf'));
function upd(inp,lbl){const n=pdfs(inp).length;$(lbl).textContent=n?`${n} PDF(s) selected`:'';}
$('ref').onchange=()=>upd($('ref'),'refCount');
$('cand').onchange=()=>upd($('cand'),'candCount');

$('go').onclick=async()=>{
 const ref=pdfs($('ref')),cand=pdfs($('cand'));
 if(!ref.length||!cand.length){$('status').innerHTML='<div class="err">Select both a reference and a candidate folder.</div>';return;}
 const fd=new FormData();
 ref.forEach(f=>fd.append('reference',f,f.name));
 cand.forEach(f=>fd.append('candidate',f,f.name));
 $('go').disabled=true;$('results').innerHTML='';$('status').textContent='Comparing '+Math.min(ref.length,cand.length)+' pair(s)…';
 try{
  const r=await fetch('/compare',{method:'POST',body:fd});
  const d=await r.json();
  if(d.error){$('status').innerHTML='<div class="err">'+d.error+'</div>';return;}
  $('status').textContent='';
  render(d);
 }catch(e){$('status').innerHTML='<div class="err">Request failed: '+e+'</div>';}
 finally{$('go').disabled=false;}
};

function render(d){
 let h='<table><thead><tr><th>Drawing</th><th>Status</th><th>Defects</th><th>Review</th><th>Report</th></tr></thead><tbody>';
 for(const p of d.pairs){
  if(p.error){h+=`<tr><td>${p.name}</td><td class="st-error">error</td><td colspan=3>${p.error}</td></tr>`;continue;}
  h+=`<tr><td>${p.name}</td><td class="st-${p.status}">${p.status}</td><td>${p.defect}</td><td>${p.review}</td>`
    +`<td><a class="view" href="${p.report_url}" target="_blank">View report →</a></td></tr>`;
 }
 h+='</tbody></table>';
 const un=[];
 if(d.unmatched_reference.length)un.push('Reference PDFs with no candidate match: '+d.unmatched_reference.join(', '));
 if(d.unmatched_candidate.length)un.push('Candidate PDFs with no reference match: '+d.unmatched_candidate.join(', '));
 if(un.length)h+='<div class="warn">'+un.join('<br>')+'</div>';
 $('results').innerHTML=h;
}
</script></body></html>"""


def main() -> None:
    host = os.environ.get("COMPARATOR_HOST", "127.0.0.1")
    port = int(os.environ.get("COMPARATOR_PORT", "5000"))
    print(f"Text-Fidelity Comparator UI → http://{host}:{port}")
    create_app().run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
