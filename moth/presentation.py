"""Plain-language descriptions for observations and assessment failures."""
import json

# Known observations also cover results saved by earlier versions of Moth.
OBSERVATIONS = {
'Web service observed': (
 ('Web service detected', 'The address responded as a web service. The HTTP status, server and detected technologies are listed below. This is an inventory result, not a vulnerability.', 'Check that the service and reported technologies are expected. Review any outdated versions separately.'),
 ('Serviciu web detectat', 'Adresa a răspuns ca serviciu web. Mai jos apar starea HTTP, serverul și tehnologiile detectate. Este un rezultat de inventariere, nu o vulnerabilitate.', 'Verifică dacă serviciul și tehnologiile sunt cele așteptate. Analizează separat versiunile învechite.'),
 ('Обнаружен веб-сервис', 'Адрес ответил как веб-сервис. Ниже указаны HTTP-статус, сервер и обнаруженные технологии. Это инвентаризация, а не уязвимость.', 'Убедитесь, что сервис и технологии ожидаемы. Отдельно проверьте устаревшие версии.')),
'Pages discovered': (
 ('Pages discovered', 'The crawler found the addresses listed below on this website. Finding an address does not prove it is vulnerable. The crawl has a depth and time limit.', 'Review the discovered pages. Check that private or administrative pages require the intended access permissions.'),
 ('Pagini descoperite', 'Instrumentul a găsit adresele de mai jos pe acest site. O adresă găsită nu este automat vulnerabilă. Explorarea are limite de adâncime și durată.', 'Verifică paginile găsite și dacă paginile private sau administrative cer permisiunile corespunzătoare.'),
 ('Найдены страницы', 'Обходчик нашёл перечисленные ниже адреса этого сайта. Найденный адрес сам по себе не означает уязвимость. Глубина и время обхода ограничены.', 'Проверьте найденные страницы и контроль доступа к личным и административным разделам.')),
'DNS records': (
 ('DNS records found', 'These records show which addresses or aliases the hostname resolves to. They describe routing and are not vulnerabilities by themselves.', 'Verify that the addresses and aliases belong to your intended infrastructure. Remove obsolete DNS records.'),
 ('Înregistrări DNS găsite', 'Înregistrările arată adresele sau aliasurile către care este direcționat domeniul. Ele nu reprezintă singure vulnerabilități.', 'Verifică dacă adresele și aliasurile aparțin infrastructurii dorite. Elimină înregistrările DNS nefolosite.'),
 ('Найдены записи DNS', 'Записи показывают адреса и псевдонимы домена. Сами по себе они не являются уязвимостями.', 'Проверьте соответствие адресов вашей инфраструктуре. Удалите устаревшие записи DNS.')),
'Subdomains discovered (not scanned)': (
 ('Subdomains discovered (not scanned)', 'Passive sources reported these subdomains. Moth has not scanned them or confirmed that every hostname is still active.', 'Review ownership and whether each hostname is still needed. Assess a subdomain separately only when authorized.'),
 ('Subdomenii descoperite (nescanate)', 'Surse pasive au raportat aceste subdomenii. Moth nu le-a scanat și nu a confirmat că toate sunt încă active.', 'Verifică proprietarul și utilitatea fiecărei adrese. Evaluează separat un subdomeniu doar dacă ai autorizare.'),
 ('Найдены поддомены (не проверялись)', 'Пассивные источники сообщили об этих поддоменах. Moth не сканировал их и не подтвердил активность каждого адреса.', 'Проверьте принадлежность и необходимость адресов. Проверяйте поддомены отдельно при наличии разрешения.')),
'Firewall identification result': (
 ('Web firewall detection result', 'The scanner looked for signs of a web application firewall (WAF). Detection can be inaccurate; having a WAF does not prove the application is secure.', 'Compare the result with your hosting or firewall configuration. Review application security independently of WAF detection.'),
 ('Rezultatul detectării firewallului web', 'Instrumentul a căutat indicii ale unui firewall web (WAF). Detectarea poate greși; existența unui WAF nu dovedește securitatea aplicației.', 'Compară rezultatul cu configurația găzduirii sau firewallului. Verifică securitatea aplicației și separat de WAF.'),
 ('Результат обнаружения веб-файрвола', 'Сканер искал признаки WAF. Обнаружение может быть неточным; наличие WAF не доказывает безопасность приложения.', 'Сравните результат с настройками хостинга или файрвола. Проверяйте безопасность приложения независимо от WAF.')),
'TLS configuration analysis completed': (
 ('TLS configuration analyzed', 'SSLyze analyzed the encrypted connection. This result records the completed analysis; individual protocol warnings are listed separately. It is not a blanket security verdict.', 'Review the TLS evidence and any separate protocol warnings. Maintain a current certificate and TLS configuration.'),
 ('Configurație TLS analizată', 'SSLyze a analizat conexiunea criptată. Rezultatul confirmă analiza; avertizările despre protocoale apar separat. Nu este un verdict general de securitate.', 'Verifică datele TLS și avertizările separate despre protocoale. Menține certificatul și configurația TLS actualizate.'),
 ('Конфигурация TLS проанализирована', 'SSLyze проанализировал шифрованное соединение. Предупреждения о протоколах показаны отдельно. Это не общий вердикт о безопасности.', 'Проверьте данные TLS и отдельные предупреждения о протоколах. Поддерживайте сертификат и TLS в актуальном состоянии.')),
'Legacy TLS protocol supported': (
 ('Obsolete encryption protocol accepted', 'The server accepted the obsolete protocol named below. Old protocols can weaken encrypted connections, depending on the configuration and clients.', 'Review client compatibility, then disable SSL 2.0/3.0 and TLS 1.0/1.1 where supported. Retest with current TLS versions.'),
 ('Protocol de criptare învechit acceptat', 'Serverul acceptă protocolul învechit indicat mai jos. Acesta poate slăbi protecția conexiunilor, în funcție de configurație și clienți.', 'Verifică compatibilitatea clienților, apoi dezactivează SSL 2.0/3.0 și TLS 1.0/1.1 unde este posibil. Retestează cu versiuni TLS actuale.'),
 ('Принимается устаревший протокол шифрования', 'Сервер принимает указанный ниже устаревший протокол. Это может ослаблять защиту соединения в зависимости от настроек и клиентов.', 'Проверьте совместимость клиентов, затем отключите SSL 2.0/3.0 и TLS 1.0/1.1, где возможно. Повторите проверку с современным TLS.')),
'JavaScript library with known advisories': (
 ('JavaScript library has published security advisories', 'The detected library/version matches published advisories listed below. This does not confirm that your application exposes the vulnerable functionality.', 'Confirm the library version and affected features. Upgrade to a maintained version that fixes the listed advisories, then test your application.'),
 ('Bibliotecă JavaScript cu avertizări de securitate publicate', 'Versiunea detectată corespunde avertizărilor de mai jos. Aceasta nu confirmă că aplicația expune funcționalitatea vulnerabilă.', 'Confirmă versiunea și funcțiile afectate. Actualizează biblioteca la o versiune menținută care rezolvă avertizările, apoi testează aplicația.'),
 ('Для JavaScript-библиотеки опубликованы предупреждения', 'Обнаруженная версия соответствует перечисленным предупреждениям. Это не подтверждает доступность уязвимых функций в приложении.', 'Подтвердите версию и затронутые функции. Обновите библиотеку до поддерживаемой исправленной версии и протестируйте приложение.')),
'Web port observed': (
 ('Web port checked', 'Nmap checked the selected website port. An open port means a service is reachable; this alone is not a vulnerability.', 'Check that this service should be reachable. Close or restrict access to services that should not be exposed.'),
 ('Portul web a fost verificat', 'Nmap a verificat portul site-ului ales. Un port deschis indică un serviciu accesibil, nu automat o vulnerabilitate.', 'Verifică dacă serviciul trebuie să fie accesibil. Închide sau limitează accesul la serviciile care nu trebuie expuse.'),
 ('Проверен веб-порт', 'Nmap проверил выбранный порт сайта. Открытый порт означает доступность сервиса, но сам по себе не является уязвимостью.', 'Проверьте, должен ли сервис быть доступен. Закройте или ограничьте доступ к лишним сервисам.')),
}
LANGS = {'en': 0, 'ro': 1, 'ru': 2}
SCANNER = (
 ('A scanner rule reported a possible issue. Review the evidence below and the scanner details before deciding whether it affects this application.', 'Confirm the condition manually, apply the relevant configuration or software fix, and retest.'),
 ('O regulă a instrumentului a raportat o posibilă problemă. Verifică dovezile și detaliile instrumentului înainte de a decide dacă afectează aplicația.', 'Confirmă manual problema, aplică modificarea de configurație sau software potrivită și repetă verificarea.'),
 ('Правило сканера сообщило о возможной проблеме. Проверьте данные и описание сканера, прежде чем решать, затрагивает ли она приложение.', 'Подтвердите проблему вручную, внесите подходящее исправление настроек или ПО и повторите проверку.'))


def describe(item, language='en'):
    index = LANGS.get(language, 0)
    known = OBSERVATIONS.get(item.get('code', ''))
    if known:
        return known[index]
    text = item['text'].get(language, item['text']['en'])
    if item['tool'] == 'moth':
        return text
    original = item['text']['en']
    explanation, action = SCANNER[index]
    if language == 'en':
        if original[1] and not original[1].startswith('Reported by the external tool.'):
            explanation = original[1] if original[1].startswith(SCANNER[0][0]) else explanation + "\n\n" + original[1]
        if original[2] and original[2] != 'Review this observation in its application context.':
            action = original[2]
    return original[0], explanation, action


def evidence_text(value):
    try:
        data = json.loads(value)
    except (ValueError, TypeError):
        return value
    def lines(obj, depth=0):
        indent = '  ' * depth
        if isinstance(obj, dict):
            for key, val in obj.items():
                label = key.replace('_', ' ').capitalize()
                if isinstance(val, (dict, list)):
                    yield indent + label + ':'
                    yield from lines(val, depth+1)
                else:
                    yield indent + label + ': ' + str(val)
        elif isinstance(obj, list):
            for val in obj:
                if isinstance(val, (dict, list)):
                    yield from lines(val, depth)
                    yield ''
                else:
                    yield indent + '• ' + str(val)
        else:
            yield indent + str(obj)
    return '\n'.join(lines(data)).strip()


ERRORS = {
'local': (
 ('Local laboratory option is required', 'The target resolves to a private or local address. Moth stopped before scanning it.', 'For your authorized local lab, enable “Local laboratory” and start again.'),
 ('Este necesară opțiunea de laborator local', 'Adresa este locală sau privată. Moth s-a oprit înainte de scanare.', 'Pentru laboratorul local autorizat, bifează „Local laboratory” și pornește din nou.'),
 ('Нужен режим локальной лаборатории', 'Адрес является локальным или частным. Moth остановился до сканирования.', 'Для разрешённой локальной лаборатории включите «Local laboratory» и запустите проверку снова.')),
'https': (
 ('This check needs an HTTPS address', 'SSLyze analyzes encrypted TLS connections. The selected address uses HTTP.', 'Use the site’s working HTTPS address, or deselect SSLyze for this HTTP assessment.'),
 ('Verificarea necesită o adresă HTTPS', 'SSLyze analizează conexiuni criptate TLS. Adresa aleasă folosește HTTP.', 'Introdu adresa HTTPS funcțională sau debifează SSLyze pentru evaluarea HTTP.'),
 ('Для проверки нужен HTTPS-адрес', 'SSLyze анализирует шифрованные TLS-соединения. Выбранный адрес использует HTTP.', 'Укажите работающий HTTPS-адрес или отключите SSLyze для этой HTTP-проверки.')),
'dns': (
 ('The hostname could not be resolved', 'Moth could not find a network address for this hostname.', 'Check the hostname spelling, internet/VPN connection and DNS settings, then retry.'),
 ('Numele domeniului nu a putut fi rezolvat', 'Moth nu a putut găsi o adresă de rețea pentru acest domeniu.', 'Verifică numele domeniului, conexiunea internet/VPN și setările DNS, apoi reîncearcă.'),
 ('Не удалось определить адрес домена', 'Moth не смог найти сетевой адрес для этого домена.', 'Проверьте имя домена, интернет/VPN и настройки DNS, затем повторите попытку.')),
'connection': (
 ('The service could not be reached', 'The connection failed. The website may be stopped, inaccessible or using a different port.', 'Open the same address yourself. Check that the server is running and the hostname, protocol and port are correct.'),
 ('Serviciul nu a putut fi accesat', 'Conexiunea a eșuat. Site-ul poate fi oprit, inaccesibil sau poate folosi alt port.', 'Deschide aceeași adresă manual. Verifică dacă serverul rulează și dacă domeniul, protocolul și portul sunt corecte.'),
 ('Сервис недоступен', 'Подключение не удалось. Сайт может быть остановлен, недоступен или использовать другой порт.', 'Откройте тот же адрес вручную. Проверьте работу сервера, имя, протокол и порт.')),
'certificate': (
 ('The encrypted connection could not be verified', 'The TLS certificate or handshake could not be validated.', 'Check the HTTPS address, certificate chain/expiry and the computer clock. Review self-signed certificates in local labs.'),
 ('Conexiunea criptată nu a putut fi verificată', 'Certificatul TLS sau negocierea conexiunii nu au putut fi validate.', 'Verifică adresa HTTPS, lanțul și expirarea certificatului și ceasul calculatorului. În laborator, verifică certificatele autosemnate.'),
 ('Не удалось проверить шифрованное соединение', 'Сертификат TLS или согласование соединения не прошли проверку.', 'Проверьте HTTPS-адрес, цепочку/срок сертификата и часы компьютера. В лаборатории проверьте самоподписанные сертификаты.')),
'limit': (
 ('The check reached a limit', 'The instrument stopped because its time or output limit was reached. Its coverage is incomplete.', 'Check target responsiveness and review the technical message. Retry the check separately if needed.'),
 ('Verificarea a atins o limită', 'Instrumentul s-a oprit la limita de timp sau volum de date. Verificarea este incompletă.', 'Verifică dacă site-ul răspunde și citește mesajul tehnic. Repetă verificarea separat dacă este necesar.'),
 ('Проверка достигла лимита', 'Инструмент остановился из-за лимита времени или объёма данных. Проверка неполная.', 'Проверьте доступность сайта и техническое сообщение. При необходимости повторите проверку отдельно.')),
'generic': (
 ('The instrument could not finish this check', 'This check failed to produce a complete result. This is an execution error, not a confirmed website vulnerability.', 'Read the technical message below. Check the tool installation, target compatibility and connection, then retry this tool separately.'),
 ('Instrumentul nu a putut termina verificarea', 'Nu există un rezultat complet. Este o eroare de execuție, nu o vulnerabilitate confirmată a site-ului.', 'Citește mesajul tehnic de mai jos. Verifică instalarea, compatibilitatea țintei și conexiunea, apoi reîncearcă separat cu acest instrument.'),
 ('Инструмент не смог завершить проверку', 'Полный результат не получен. Это ошибка выполнения, а не подтверждённая уязвимость сайта.', 'Прочтите техническое сообщение ниже. Проверьте установку инструмента, совместимость и соединение, затем запустите инструмент отдельно.')),
}


def error_help(message, language='en'):
    lower = message.lower()
    if 'local laboratory' in lower:
        key = 'local'
    elif 'https url for sslyze' in lower:
        key = 'https'
    elif any(s in lower for s in ('getaddrinfo', 'name or service not known', 'did not resolve', 'name resolution')):
        key = 'dns'
    elif any(s in lower for s in ('certificate', 'tls handshake', 'ssl:')):
        key = 'certificate'
    elif any(s in lower for s in ('timed out', 'time limit', 'size limit', 'output exceeded')):
        key = 'limit'
    elif any(s in lower for s in ('connection refused', 'unreachable', 'connection reset', 'no server analysis', 'no site data', 'no web response', 'could not complete the tls')):
        key = 'connection'
    else:
        key = 'generic'
    return ERRORS[key][LANGS.get(language, 0)]


def finding_sort_keys(scan, mode, language='en'):
    """Stable display order; old sequential assessments use recorded step order."""
    severity = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3, 'info': 4}
    steps = scan.get('steps', [])
    ranks = {step['tool']: step.get('completion_order', index) for index, step in enumerate(steps)}
    keys = {}
    for index, finding in enumerate(scan['findings']):
        level = severity.get(finding['severity'])
        if mode == 'severity_desc':
            value = level if level is not None else 5
        elif mode == 'severity_asc':
            value = 4-level if level is not None else 5
        elif mode == 'completion_newest':
            value = -max((ranks.get(tool, -1) for tool in finding.get('source_tools', [finding['tool']])), default=-1)
        elif mode == 'tool_az':
            value = finding['tool'].casefold()
        elif mode == 'title_az':
            value = describe(finding, language)[0].casefold()
        else:
            value = min((ranks.get(tool, len(steps)) for tool in finding.get('source_tools', [finding['tool']])), default=len(steps))
        keys[finding['id']] = (value, index)
    return keys
