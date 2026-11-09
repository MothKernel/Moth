import html
import json
from .presentation import describe, error_help
from .results import grouped, priorities
from .config import ROOT


def render(scan, language="en"):
    language = language if language in ("en", "ro", "ru") else "en"
    labels = {
        "en": ["Assessment report", "Status", "Coverage", "Recommendation", "Technical details", "Errors", "No findings were reported. This does not establish that the site is secure."],
        "ro": ["Raport de evaluare", "Stare", "Acoperire", "Recomandare", "Detalii tehnice", "Erori", "Nu au fost raportate constatări. Aceasta nu dovedește că site-ul este sigur."],
        "ru": ["Отчёт о проверке", "Статус", "Охват", "Рекомендация", "Технические сведения", "Ошибки", "Замечаний не обнаружено. Это не доказывает безопасность сайта."],
    }[language]
    esc = lambda value: html.escape(str(value))
    cards = []
    translated = json.loads((ROOT / "resources/translations.json").read_text(encoding="utf-8"))[language]
    for item in grouped(scan["findings"]):
        title, description, remediation = describe(item, language)
        cards.append(f"<article><small>{esc(item['severity'])} · {esc(item['tool'])} · {esc(item['kind'])}</small>"
                     f"<h2>{esc(title)}</h2><p>{esc(description)}</p><h3>{labels[3]}</h3><p>{esc(remediation)}</p>"
                     f"<p>{esc(translated.get(item['verification'], item['verification']))}</p><p>{esc(translated['sources'])}: {esc(', '.join(item['source_tools']))}</p><h3>{labels[4]}</h3><pre>{esc(item['evidence'])}</pre><p>{esc(item['technical'])}</p></article>")
    errors = "".join(f"<article><h3>{esc(e['tool'])}: {esc(error_help(e['message'], language)[0])}</h3><p>{esc(error_help(e['message'], language)[1])}</p><p>{esc(error_help(e['message'], language)[2])}</p><pre>{esc(e['message'])}</pre></article>" for e in scan["errors"])
    priority_html = '<h2>' + esc(translated['priorities']) + '</h2><p>' + esc(translated['priority_note']) + '</p>'
    for item in priorities(scan)[:3]:
        title, description, remediation = describe(item, language)
        priority_html += '<p><strong>' + esc(item['severity'] + ' · ' + title) + '</strong><br>' + esc(item['target']) + '<br>' + esc(remediation) + '</p>'
    comparison = scan.get('comparison', {})
    comparison_html = '<h2>' + esc(translated['comparison']) + '</h2><p>' + esc(translated.get(comparison.get('reason', 'no_baseline'), '')) + '</p>'
    for row in comparison.get('rows', []):
        comparison_html += '<p>' + esc(translated.get('change_' + row['status'], row['status'])) + ': ' + esc(describe(row['finding'], language)[0]) + ' · ' + esc(row['finding']['target']) + '</p>'
    return f"""<!doctype html><html lang="{language}"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Moth — {labels[0]}</title><style>
body{{max-width:900px;margin:48px auto;padding:0 24px;font:16px/1.65 system-ui;color:#18372e}}
article{{border:1px solid #d8ded8;padding:24px;margin:20px 0;break-inside:avoid}}h1{{font-size:36px}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f0;padding:16px}}small{{color:#586b60}}
@media print{{body{{margin:0}}}}
</style><body><p>MOTH / {esc(scan['created'])}</p><h1>{labels[0]}</h1>
<p>{esc(scan['target'])}</p><p>{labels[1]}: {esc(scan['status'])} · {esc(scan.get("profile", "low").title())}</p>
<h2>{labels[2]}</h2><pre>{esc(scan.get('coverage', {}))}</pre><pre>{esc(scan.get('tool_versions', {}))}</pre><pre>{esc(scan.get("tool_scope", {}))}</pre>
<h2>ZAP Spider</h2><pre>{esc(json.dumps(scan.get('spider', {}), ensure_ascii=False, indent=2))}</pre>
{priority_html}{comparison_html}
{''.join(cards) or f'<p>{labels[6]}</p>'}<h2>{labels[5]}</h2>{errors or '—'}
</body></html>"""
