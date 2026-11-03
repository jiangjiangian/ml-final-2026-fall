"""Bounded normal-TLS diagnostics; no credentials or response contents are printed.

Run this in the failing runner, rather than treating a successful developer-laptop
request as proof the cloud runner can connect. Optional curl IPv4 is a connection
comparison only, never a replacement dataset or an insecure TLS workaround.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.ingestion.external import (  # noqa: E402
    ExternalDataError, MAX_PAYLOAD_BYTES, SOURCE_SPECS, download_external,
)


def requests_diagnostic(source):
    try:
        with tempfile.TemporaryDirectory(prefix='finpred-source-diagnostic-') as temporary:
            manifest = download_external(source, temporary)
            audit = manifest['metadata']['audit']
            return {'status': 'validated_raw', 'tls_verification': True,
                    'payload_sha256': manifest['sha256'], 'size_bytes': manifest['size_bytes'],
                    'row_count': audit['row_count'], 'date_min': audit['date_min'],
                    'date_max': audit['date_max'], 'unit': audit['unit'],
                    'historical_availability_verified': False}
    except ExternalDataError as error:
        return {'status': 'failed', 'error_type': 'ExternalDataError',
                'network_category': error.network_category or 'not_a_network_exception',
                'response_contents_omitted': True}
    except (OSError, ValueError):
        return {'status': 'failed', 'error_type': 'diagnostic_storage_or_validation_error',
                'response_contents_omitted': True}


def curl_ipv4_diagnostic(source):
    binary = shutil.which('curl')
    if binary is None:
        return {'status': 'unavailable', 'reason': 'curl_not_installed'}
    # URL is from the fixed adapter registry; no arbitrary headers, credentials,
    # redirects, shell expansion or --insecure flags can enter this invocation.
    arguments = [binary, '--silent', '--show-error', '--ipv4', '--connect-timeout', '10',
                 '--max-time', '45', '--max-filesize', str(MAX_PAYLOAD_BYTES),
                 '--output', os.devnull, '--write-out', '%{http_code} %{ssl_verify_result}',
                 SOURCE_SPECS[source]['url']]
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=50, check=False)
        fields = result.stdout.strip().split()
        status = int(fields[0]) if len(fields) == 2 and fields[0].isdigit() else None
        ssl_result = int(fields[1]) if len(fields) == 2 and fields[1].isdigit() else None
        return {'status': 'connection_checked', 'curl_exit_code': result.returncode,
                'http_status': status, 'ssl_verify_result': ssl_result,
                'tls_verification': result.returncode == 0 and ssl_result == 0,
                'dataset_validated': False, 'stderr_omitted': True}
    except (OSError, subprocess.TimeoutExpired):
        return {'status': 'failed', 'reason': 'curl_unavailable_or_timed_out', 'stderr_omitted': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='append', choices=sorted(SOURCE_SPECS), required=True)
    parser.add_argument('--include-curl-ipv4', action='store_true')
    args = parser.parse_args()
    records = []
    for source in dict.fromkeys(args.source):
        record = {'source': source, 'requests': requests_diagnostic(source)}
        if args.include_curl_ipv4:
            record['curl_ipv4'] = curl_ipv4_diagnostic(source)
        records.append(record)
    print(json.dumps({'diagnosed_at': datetime.now(timezone.utc).isoformat(), 'sources': records},
                     ensure_ascii=False))
    return 0  # This reports source failures; it does not certify pipeline success.


if __name__ == '__main__':
    raise SystemExit(main())
