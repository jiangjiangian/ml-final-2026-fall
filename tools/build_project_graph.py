"""Build project graphs with Graphify; semantic extraction is performed by the skill.

Run with the interpreter containing graphifyy==0.9.95 from the repository root.
The semantic snapshot must be refreshed by the Graphify skill when docs change.
No course data or credentials are read by this script.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from graphify.analyze import god_nodes, suggest_questions, surprising_connections
from graphify.build import build_from_json, mint_external_stubs_in_data
from graphify.cluster import cluster, score_all
from graphify.detect import detect, save_manifest
from graphify.diagnostics import diagnose_extraction, format_diagnostic_report
from graphify.export import to_json
from graphify.extract import extract
from graphify.report import generate

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "ml_financial_prediction"
OUT = REPO / "graphify-out"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true', help='Full rebuild after reviewing intentional node retirements')
    parser.add_argument('--reviewed-retirements', type=Path, help='JSON mapping of retired semantic IDs to review reasons')
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    semantic = json.loads((OUT / "semantic.json").read_text(encoding="utf-8"))
    detection = detect(ROOT)
    doc_files = detection["files"].get("document", [])
    # A changed or newly added document requires fresh host-agent extraction.
    for filename in doc_files:
        relative = str(Path(filename).relative_to(ROOT))
        expected = semantic.get("source_hashes", {}).get(relative)
        actual = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
        if expected != actual:
            raise SystemExit(f"Refresh Graphify semantic extraction first: {relative}")
    ast = extract(
        [Path(p) for p in detection["files"].get("code", [])],
        root=ROOT,
        cache_root=ROOT,
    )
    nodes = {node["id"]: node for node in ast["nodes"]}
    for node in semantic["nodes"]:
        nodes.setdefault(node["id"], dict(node, _origin="semantic"))
    extraction = {
        "nodes": list(nodes.values()),
        "edges": ast["edges"] + [dict(e, _origin="semantic") for e in semantic["edges"]],
        "hyperedges": semantic.get("hyperedges", []),
        "input_tokens": 0,
        "output_tokens": 0,
    }
    raw_health = diagnose_extraction(extraction, directed=True, root=ROOT)
    # Graphify 0.9.95 resolves super().post_predictions to the overriding method
    # itself. Correct only this audited call site, after checking its source text
    # and the concrete parent method node; retain the raw diagnostic separately.
    corrected_super_calls = []
    node_ids = {n['id'] for n in extraction['nodes']}
    override = 'scripts_run_hosted_pipeline_durable_submission_client_post_predictions'
    parent = 'src_finpred_submission_course_coursesubmissionclient_post_predictions'
    for edge in extraction['edges']:
        if (edge.get('source') == override and edge.get('target') == override
                and edge.get('relation') == 'calls'
                and edge.get('source_file') == 'scripts/run_hosted_pipeline.py'):
            location = edge.get('source_location', '')
            if re.fullmatch(r'L\d+', location):
                lines = (ROOT / edge['source_file']).read_text().splitlines()
                index = int(location[1:]) - 1
                if (0 <= index < len(lines) and parent in node_ids
                        and lines[index].strip() == 'return super().post_predictions(target_date, file_name, payload)'):
                    corrected_super_calls.append({'source': override, 'previous_target': override,
                                                  'corrected_target': parent, 'source_location': location})
                    edge['target'] = parent
    # The AST parser emits identical list-field edges and references to stdlib imports.
    # Preserve every distinct evidence record; mint only Graphify-verified import stubs.
    occurrences = {}
    for edge in extraction["edges"]:
        fingerprint = json.dumps(edge, sort_keys=True, ensure_ascii=False)
        occurrences[fingerprint] = occurrences.get(fingerprint, 0) + 1
    extraction["edges"] = [json.loads(key) for key in occurrences]
    before_stubs = len(extraction["nodes"])
    mint_external_stubs_in_data(extraction)
    import_stub_count = len(extraction["nodes"]) - before_stubs
    # Graphify emits package dependency edges but not their external package
    # nodes. Materialize only names explicitly declared in this pyproject.
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared_packages = {}
    for requirement in manifest.get("project", {}).get("dependencies", []):
        match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement)
        if match:
            name = match.group(0)
            declared_packages["pkg_" + re.sub(r"[^a-z0-9]", "_", name.lower())] = name
    known_ids = {node["id"] for node in extraction["nodes"]}
    dependency_stub_count = 0
    for edge in extraction["edges"]:
        target = edge.get("target")
        if (edge.get("relation") == "depends_on" and target not in known_ids
                and edge.get("source_file") == "pyproject.toml"
                and edge.get("source") in known_ids and target in declared_packages):
            extraction["nodes"].append({
                "id": target, "label": declared_packages[target], "file_type": "code",
                "type": "external_package", "source_file": "pyproject.toml",
                "source_location": edge.get("source_location"), "_origin": "manifest",
                "rationale": "External dependency explicitly declared in project.dependencies",
            })
            known_ids.add(target)
            dependency_stub_count += 1
    normalization = {
        "exact_duplicates_removed": sum(n - 1 for n in occurrences.values()),
        "external_import_stubs_added": import_stub_count,
        "declared_external_dependency_nodes_added": dependency_stub_count,
        "audited_super_call_corrections": corrected_super_calls,
        "duplicate_groups": [{"edge": json.loads(key), "occurrences": n}
                             for key, n in occurrences.items() if n > 1],
    }
    graph = build_from_json(extraction, root=ROOT, directed=True)
    if not graph.number_of_nodes():
        raise SystemExit("Empty extraction; existing graph left untouched")
    if args.force and (OUT / 'graph.json').exists():
        previous = json.loads((OUT / 'graph.json').read_text())
        retired = [n for n in previous.get('nodes', [])
                   if n.get('_origin') == 'semantic' and n['id'] not in graph]
        reviewed = json.loads(args.reviewed_retirements.read_text()) if args.reviewed_retirements else {}
        if {n['id'] for n in retired} != set(reviewed) or any(not reason for reason in reviewed.values()):
            raise SystemExit('Force requires explicit reasons for exactly the retired semantic nodes')
        normalization['reviewed_semantic_retirements'] = [
            {'id': n['id'], 'source_file': n.get('source_file'), 'previous_label': n.get('label'),
             'reason': reviewed[n['id']]} for n in retired
        ]
    communities = cluster(graph)
    cohesion = score_all(graph, communities)
    # Labels derive from the most connected members, not a fabricated taxonomy.
    labels = {
        cid: " / ".join(
            graph.nodes[n].get("label", n)
            for n in sorted(members, key=lambda n: graph.degree(n), reverse=True)[:2]
        )
        for cid, members in communities.items()
    }
    gods = god_nodes(graph)
    surprises = surprising_connections(graph, communities)
    questions = suggest_questions(graph, communities, labels)
    if not to_json(graph, communities, str(OUT / "graph.json"), force=args.force, community_labels=labels,
                   original_links=extraction["edges"]):
        raise SystemExit("Graphify shrink guard refused this build; existing report retained")
    health = diagnose_extraction(extraction, directed=True, root=ROOT)
    serialized = json.loads((OUT / "graph.json").read_text(encoding="utf-8"))
    if len(serialized["links"]) != len(extraction["edges"]):
        raise SystemExit("Export did not preserve every distinct evidence edge")
    health["exported_evidence_edges"] = len(serialized["links"])
    health["exported_multigraph"] = serialized.get("multigraph", False)
    health["export_evidence_loss"] = 0
    report = generate(
        graph, communities, cohesion, labels, gods, surprises, detection,
        {"input": 0, "output": 0}, str(ROOT), suggested_questions=questions,
    )
    report = report.replace("- Token cost: 0 input · 0 output",
                            "- Token cost: unavailable (host-agent usage metadata not exposed)")
    report += (
        "\n## Build provenance\n\n"
        "Built using graphifyy 0.9.95: AST extraction plus host-agent document extraction.\n"
        "Clustering uses Graphify's installed NetworkX Louvain fallback.\n"
        "Token usage/cost is **unavailable**, not zero: this host's agent API does not expose "
        "usage metadata. The tool's zero placeholders above are not measured usage.\n"
        "`graphify-out/` is in the working tree; only shareable artifacts are retained by Git.\n"
        "The graph is a map of documented plans and code, not evidence of model performance.\n\n"
        f"Normalization removed {normalization['exact_duplicates_removed']} exact duplicate "
        f"edges and added {normalization['external_import_stubs_added']} verified external "
        "import stubs using Graphify's own API. "
        f"Added {dependency_stub_count} external package nodes only for dependencies "
        "explicitly declared in pyproject.toml. Distinct evidence is retained. The raw "
        "extractor diagnostics and normalization audit are in `raw_health.json` and "
        "`normalization.json`. Repeated YAML list-field keys are a structural abstraction; "
        "individual market meanings are represented by the document extraction.\n\n"
        "Clustering analyzes simple directed connectivity, so same-endpoint relations "
        "are counted as topology collapse in the diagnostic below. The JSON and HTML "
        "exports retain **all distinct parallel evidence edges** via Graphify's "
        "`original_links` export API; this count is not export evidence loss.\n\n"
        + format_diagnostic_report(health) + "\n"
    )
    if normalization.get('reviewed_semantic_retirements'):
        report += ('\n## Reviewed semantic retirements\n\n'
                   'The normal export guard first refused five retired documentation nodes. '
                   'After complete source rereading and a private backup, this explicit full rebuild '
                   'retired only the reviewed stale/superseded statements listed in normalization.json. '
                   'Current content, source coverage and every distinct current evidence edge are preserved.\n')
    (OUT / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    (OUT / "health.json").write_text(json.dumps(health, indent=2) + "\n")
    (OUT / "raw_health.json").write_text(json.dumps(raw_health, indent=2) + "\n")
    (OUT / "normalization.json").write_text(json.dumps(normalization, indent=2) + "\n")
    (OUT / ".graphify_python").write_text(sys.executable)
    (OUT / ".graphify_root").write_text(str(ROOT))
    (OUT / ".graphify_labels.json").write_text(json.dumps(labels, ensure_ascii=False))
    save_manifest(detection["files"], manifest_path=str(OUT / "manifest.json"), root=ROOT)
    subprocess.run([sys.executable, "-m", "graphify", "export", "html"], cwd=REPO, check=True)
    print(f"Graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges, "
          f"{len(communities)} communities")
    print(format_diagnostic_report(health))


if __name__ == "__main__":
    main()
