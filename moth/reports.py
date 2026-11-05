import html


def render(scan, language="en"):
    language = language if language in ("en", "ro", "ru") else "en"
    labels = {
        "en": ["Assessment report", "Status", "Coverage", "Recommendation", "Technical details", "Errors", "No findings were reported. This does not establish that the site is secure."],
        "ro": ["Raport de evaluare", "Stare", "Acoperire", "Recomandare", "Detalii tehnice", "Erori", "Nu au fost raportate constatări. Aceasta nu dovedește că site-ul este sigur."],
        "ru": ["Отчёт о проверке", "Статус", "Охват", "Рекомендация", "Технические сведения", "Ошибки", "Замечаний не обнаружено. Это не доказывает безопасность сайта."],
    }[language]
    esc = lambda value: html.escape(str(value))
    cards = []
    for item in scan["findings"]:
        title, description, remediation = item["text"].get(language, item["text"]["en"])
        cards.append(f"<article><small>{esc(item['severity'])} · {esc(item['tool'])} · {esc(item['kind'])}</small>"
                     f"<h2>{esc(title)}</h2><p>{esc(description)}</p><h3>{labels[3]}</h3><p>{esc(remediation)}</p>"
                     f"<h3>{labels[4]}</h3><pre>{esc(item['evidence'])}</pre><p>{esc(item['technical'])}</p></article>")
    errors = "".join(f"<p>{esc(e['tool'])}: {esc(e['message'])}</p>" for e in scan["errors"])
    return f"""<!doctype html><html lang="{language}"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Moth — {labels[0]}</title><style>
body{{max-width:900px;margin:48px auto;padding:0 24px;font:16px/1.65 system-ui;color:#18372e}}
article{{border:1px solid #d8ded8;padding:24px;margin:20px 0;break-inside:avoid}}h1{{font-size:36px}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f0;padding:16px}}small{{color:#586b60}}
@media print{{body{{margin:0}}}}
</style><body><p>MOTH / {esc(scan['created'])}</p><h1>{labels[0]}</h1>
<p>{esc(scan['target'])}</p><p>{labels[1]}: {esc(scan['status'])}</p>
<h2>{labels[2]}</h2><pre>{esc(scan.get('coverage', {}))}</pre><pre>{esc(scan.get('tool_versions', {}))}</pre>
{''.join(cards) or f'<p>{labels[6]}</p>'}<h2>{labels[5]}</h2>{errors or '—'}
</body></html>"""
