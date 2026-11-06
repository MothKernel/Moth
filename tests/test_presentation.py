import json
import pytest
from moth.adapters import observation
from moth.presentation import describe, error_help, evidence_text, OBSERVATIONS


@pytest.mark.parametrize('language', ['en', 'ro', 'ru'])
@pytest.mark.parametrize('title', list(OBSERVATIONS))
def test_inventory_results_have_specific_localized_guidance(title, language):
    item = observation('katana', 'https://example.com', title, '/page')
    text = describe(item, language)
    assert all(text)
    assert 'Reported by the external tool.' not in text[1]
    assert 'Review this observation in its application context.' not in text[2]


def test_old_saved_generic_observation_is_enriched_without_modifying_it():
    item = observation('katana', 'https://example.com', 'Pages discovered', '/account')
    item['text'] = {lang: ['Pages discovered', 'Reported by the external tool.', 'Review this observation in its application context.'] for lang in ('en', 'ro', 'ru')}
    original = json.dumps(item)
    assert 'private' in describe(item, 'en')[2]
    assert describe(item, 'ro')[0] == 'Pagini descoperite'
    assert json.dumps(item) == original


@pytest.mark.parametrize('message,fragment', [
    ('Private/local addresses require the local laboratory option.', 'Local laboratory'),
    ('Select an HTTPS URL for SSLyze.', 'HTTPS'),
    ('[Errno -2] Name or service not known', 'resolved'),
    ('[Errno 111] Connection refused', 'reached'),
    ('Tool exceeded its execution time limit.', 'limit'),
    ('Certificate validation failed', 'encrypted'),
    ('Tool exited with code 1: unsupported option', 'could not finish'),
])
def test_errors_have_a_reason_and_action(message, fragment):
    title, explanation, action = error_help(message)
    assert fragment in title
    assert explanation and action
    assert error_help(message, 'ro') != (title, explanation, action)


def test_evidence_is_readable_and_values_are_preserved():
    text = evidence_text('{"status_code":200,"tech":["Express"],"host":"127.0.0.1"}')
    assert 'Status code: 200' in text
    assert 'Express' in text and '127.0.0.1' in text
    assert evidence_text('TCP 3000: open') == 'TCP 3000: open'


def test_scanner_description_is_preserved_without_repeating_the_intro():
    from moth.presentation import SCANNER
    item = observation('zap', 'https://example.com', 'Scanner rule', 'ZAP rule 1', explanation='Specific scanner description.', recommendation='Specific fix.')
    for language in ('en', 'ro', 'ru'):
        assert all(describe(item, language))
    english = describe(item, 'en')
    assert english[1].count(SCANNER[0][0]) == 1
    assert 'Specific scanner description.' in english[1]
    assert english[2] == 'Specific fix.'


def test_findings_sort_by_numeric_severity_and_recorded_tool_completion():
    from moth.findings import finding
    from moth.presentation import finding_sort_keys
    findings = [finding('one','https://example.com','1','info',tool='httpx'),
                finding('two','https://example.com','2','high',tool='nuclei'),
                finding('three','https://example.com','3','medium',tool='moth'),
                finding('four','https://example.com','4','low',tool='nuclei')]
    scan = dict(findings=findings, steps=[dict(tool='moth',completion_order=0),dict(tool='nuclei',completion_order=2),dict(tool='httpx',completion_order=1)])
    original = list(findings)
    def order(mode):
        keys=finding_sort_keys(scan,mode)
        return [f['code'] for f in sorted(findings,key=lambda f:keys[f['id']])]
    assert order('severity_desc')==['two','three','four','one']
    assert order('severity_asc')==['one','four','three','two']
    assert order('completion_oldest')==['three','one','two','four']
    assert order('completion_newest')==['two','four','one','three']
    assert order('tool_az')==['one','three','two','four']
    assert scan['findings']==original
    for step in scan['steps']:
        step.pop('completion_order')
    assert order('completion_oldest')==['three','two','four','one']
