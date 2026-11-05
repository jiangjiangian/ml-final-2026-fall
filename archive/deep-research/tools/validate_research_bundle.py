"""Check the research handoff offline; optionally hash its private public-source evidence."""

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit


def validate(repo, evidence_root=None):
    project = repo / 'ml_financial_prediction'
    docs = project / 'docs/deep-research'
    sources = json.loads((docs / 'sources.json').read_text())['sources']
    ids = {s['id'] for s in sources}
    if len(ids) != len(sources):
        raise ValueError('duplicate source IDs')
    for source in sources:
        if source['http_status'] != 200 or not source['read_scope'] or not source['evidence_locator']:
            raise ValueError('source needs successful retrieval and qualified reading scope')
        if not re.fullmatch(r'[a-f0-9]{64}', source['payload_sha256']):
            raise ValueError('invalid source hash')
        if datetime.fromisoformat(source['retrieved_at']).utcoffset() is None:
            raise ValueError('source retrieval timestamp must be aware')
        for key in ('url', 'retrieval_url'):
            parts = urlsplit(source[key])
            if parts.scheme != 'https' or not parts.netloc or parts.username or parts.password:
                raise ValueError('source URL must be HTTPS without embedded credentials')
        if source.get('supports_production_performance_claim') is not False:
            raise ValueError('sources are not this project production performance evidence')
        if evidence_root:
            path = (evidence_root / source['evidence_path']).resolve()
            if not path.is_relative_to(evidence_root.resolve()):
                raise ValueError('evidence path escaped the private store')
            if hashlib.sha256(path.read_bytes()).hexdigest() != source['payload_sha256']:
                raise ValueError('actual retrieved source hash mismatch')

    config = json.loads((project / 'configs/research/model_families.json').read_text())
    models = config['models']
    if {m['id'] for m in models} != {'M1', 'M2', 'M3', 'M4'}:
        raise ValueError('four distinct model definitions required')
    if len({m['family'] for m in models}) != 4:
        raise ValueError('model families must be distinct')
    if config['status'] != 'design_only_not_loaded_by_existing_runner':
        raise ValueError('do not claim unimplemented blueprints as trained')
    if sum(len(m['initial_tuning']['values']) for m in models) != config['validation']['initial_configuration_budget']:
        raise ValueError('experiment settings exceed the declared initial budget')
    validation = config['validation']
    ablations = validation['feature_ablation_budget']
    ablation_count = len(ablations['groups']) * len(ablations['fixed_models'])
    if validation['initial_configuration_budget_scope'] != 'R2_model_comparison_only':
        raise ValueError('separate feature and model experiment budgets')
    if ablation_count != ablations['maximum_configurations']:
        raise ValueError('feature ablations exceed the declared budget')
    total_fits = ((ablation_count + validation['initial_configuration_budget'])
                  * validation['quarter_folds_per_configuration'])
    if total_fits != validation['maximum_fits_R1_plus_R2']:
        raise ValueError('fit budget must include feature ablations and all folds')
    if config['objective']['expected_stocks'] != 50:
        raise ValueError('official 50-stock universe changed')
    for model in models:
        if set(model['sources']) - ids:
            raise ValueError('model cites an unverified source ID')

    audit = json.loads((docs / 'citation_audit.json').read_text())
    entries = audit['entries']
    keys = {e['key'] for e in entries}
    if len(keys) != len(entries) or any(not re.fullmatch(r'[A-Za-z0-9]+', k) for k in keys):
        raise ValueError('citation keys must be unique and safe')
    dois = [e['fields']['doi'].lower() for e in entries if e['fields'].get('doi')]
    if len(dois) != len(set(dois)):
        raise ValueError('duplicate scholarly DOI')
    bib = (docs / 'references.bib').read_text()
    if set(re.findall(r'@\w+\{([A-Za-z0-9]+),', bib)) != keys or bib.count('{') != bib.count('}'):
        raise ValueError('bibliography structure disagrees with audit')
    for entry in entries:
        fields = entry['fields']
        if not all(fields.get(k) for k in ('title', 'author', 'year')):
            raise ValueError('missing required bibliographic identity')
        if not re.fullmatch(r'\d{4}', fields['year']) or entry['metadata_source'] not in ids:
            raise ValueError('unverified bibliography year or source')

    for document in docs.glob('*.md'):
        text = document.read_text()
        for match in re.finditer(r'\[[^\]]*\]\(([^)]+)\)', text):
            target = match.group(1).strip('<>')
            if urlsplit(target).scheme or target.startswith('#'):
                continue
            path_text, _, anchor = target.partition('#')
            path = (document.parent / unquote(path_text)).resolve()
            if not path.is_file():
                raise ValueError('broken local Markdown link: ' + str(path))
            if path.name == 'SOURCES.md' and anchor and anchor.upper() not in ids:
                raise ValueError('unresolved source anchor')
        cited = set(re.findall(r'\b(?:AGT|DAT|CMPAPI|CMP|FIN|MOD)\d+\b', text))
        if cited - ids:
            raise ValueError('unverified source reference in ' + document.name + ': ' + ', '.join(sorted(cited - ids)))

    return {'status': 'passed', 'reviewed_source_records': len(sources), 'bibliography_entries': len(entries),
            'model_architectures': len(models), 'initial_candidate_settings': config['validation']['initial_configuration_budget'],
            'feature_ablation_settings': ablation_count, 'maximum_future_fits': total_fits,
            'private_evidence_hashes_checked': len(sources) if evidence_root else 0,
            'new_model_performance_verified': False, 'daily_collection_deployed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(Path(__file__).resolve().parents[1], args.evidence_root), ensure_ascii=False))


if __name__ == '__main__':
    main()
