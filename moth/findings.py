"""Reviewed explanations. Missing hardening is not proof of exploitation."""
import hashlib

# title, explanation, recommendation in English, Romanian and Russian.
CATALOG = {
    "certificate_expiring": {
        "en": ["The TLS certificate expires soon", "The validated certificate has fewer than 30 days remaining. Automatic renewal may already be configured.", "Check that automatic renewal is working and renew before expiry."],
        "ro": ["Certificatul TLS expiră în curând", "Certificatul validat mai are mai puțin de 30 de zile. Reînnoirea automată poate fi deja configurată.", "Verifică reînnoirea automată și reînnoiește certificatul înainte de expirare."],
        "ru": ["Срок сертификата TLS скоро истечёт", "До истечения проверенного сертификата осталось менее 30 дней. Возможно, автоматическое продление уже настроено.", "Проверьте автоматическое продление и обновите сертификат до истечения срока."]},
    "http": {
        "en": ["This page uses unencrypted HTTP", "Traffic to this URL is not encrypted. A separate HTTPS version may exist; Moth did not follow redirects.", "Serve the site over HTTPS and redirect HTTP traffic to HTTPS."],
        "ro": ["Pagina folosește HTTP necriptat", "Traficul către această adresă nu este criptat. Poate exista o versiune HTTPS; Moth nu a urmat redirecționările.", "Folosește HTTPS și redirecționează traficul HTTP către HTTPS."],
        "ru": ["Страница использует незашифрованный HTTP", "Трафик к этому адресу не зашифрован. HTTPS-версия может существовать; Moth не переходил по перенаправлениям.", "Используйте HTTPS и перенаправляйте HTTP на HTTPS."]},
    "csp": {
        "en": ["No enforced content security policy was observed", "An additional browser protection was not found in response headers. This alone does not prove an XSS vulnerability; a policy may also be set in the page.", "Review the page and deploy a suitable Content-Security-Policy, testing compatibility first."],
        "ro": ["Nu a fost observată o politică CSP aplicată", "O protecție suplimentară a browserului lipsește din antete. Aceasta nu dovedește XSS; politica poate exista în pagină.", "Verifică pagina și configurează Content-Security-Policy după testarea compatibilității."],
        "ru": ["Применяемая политика CSP не обнаружена", "Дополнительная защита браузера не найдена в заголовках. Это не доказывает XSS; политика может быть задана в странице.", "Проверьте страницу и настройте Content-Security-Policy после тестирования совместимости."]},
    "hsts": {
        "en": ["HTTPS-only browser policy was not observed", "The HTTPS response does not tell browsers to require HTTPS on future visits.", "After confirming HTTPS works reliably, configure Strict-Transport-Security."],
        "ro": ["Politica HTTPS pentru browser lipsește", "Răspunsul HTTPS nu cere browserului să folosească obligatoriu HTTPS la vizitele viitoare.", "După verificarea HTTPS, configurează Strict-Transport-Security."],
        "ru": ["Политика обязательного HTTPS не обнаружена", "HTTPS-ответ не требует от браузера использовать HTTPS при будущих посещениях.", "Убедившись в корректной работе HTTPS, настройте Strict-Transport-Security."]},
    "nosniff": {
        "en": ["Content-type protection is missing or invalid", "The browser was not explicitly instructed to avoid guessing response content types.", "Send X-Content-Type-Options: nosniff and correct Content-Type headers."],
        "ro": ["Protecția tipului de conținut lipsește sau este invalidă", "Browserului nu i se cere explicit să evite ghicirea tipului de conținut.", "Trimite X-Content-Type-Options: nosniff și antete Content-Type corecte."],
        "ru": ["Защита типа содержимого отсутствует или некорректна", "Браузеру явно не запрещено угадывать тип содержимого ответа.", "Отправляйте X-Content-Type-Options: nosniff и корректные заголовки Content-Type."]},
    "frame": {
        "en": ["Frame embedding restrictions were not observed", "The response does not advertise frame restrictions in its headers. Clickjacking risk depends on page content and other defenses.", "Set an appropriate CSP frame-ancestors policy; consider X-Frame-Options for compatibility."],
        "ro": ["Nu au fost observate restricții pentru încadrarea paginii", "Antetele nu limitează afișarea paginii în cadre. Riscul de clickjacking depinde de conținut și de celelalte protecții.", "Configurează CSP frame-ancestors; ia în calcul X-Frame-Options pentru compatibilitate."],
        "ru": ["Ограничения встраивания страницы не обнаружены", "Заголовки не ограничивают встраивание страницы во фреймы. Риск кликджекинга зависит от содержимого и других мер защиты.", "Настройте CSP frame-ancestors; при необходимости добавьте X-Frame-Options."]},
    "cookie_secure": {
        "en": ["A cookie has no Secure attribute", "This cookie is not explicitly restricted to HTTPS. Its sensitivity requires manual review.", "Use Secure for sensitive cookies and serve them over HTTPS."],
        "ro": ["Un cookie nu are atributul Secure", "Cookie-ul nu este limitat explicit la HTTPS. Sensibilitatea lui necesită verificare manuală.", "Folosește Secure pentru cookie-urile sensibile și transmite-le prin HTTPS."],
        "ru": ["У cookie нет атрибута Secure", "Этот cookie явно не ограничен HTTPS. Его назначение требует ручной проверки.", "Для чувствительных cookie используйте Secure и HTTPS."]},
    "cookie_httponly": {
        "en": ["A cookie is accessible to JavaScript", "HttpOnly is absent. This may be intentional for non-session cookies; it is not proof of a vulnerability.", "Determine the cookie's purpose and apply HttpOnly if scripts do not need access."],
        "ro": ["Un cookie este accesibil din JavaScript", "HttpOnly lipsește. Pentru unele cookie-uri este intenționat; nu dovedește o vulnerabilitate.", "Verifică scopul cookie-ului și aplică HttpOnly dacă scripturile nu au nevoie de acces."],
        "ru": ["Cookie доступен JavaScript", "Атрибут HttpOnly отсутствует. Для некоторых cookie это нормально и не доказывает уязвимость.", "Проверьте назначение cookie и добавьте HttpOnly, если доступ из скриптов не нужен."]},
    "cookie_samesite": {
        "en": ["A cookie has no explicit SameSite policy", "Cross-site cookie behavior is left to browser defaults. This alone does not establish CSRF.", "Choose an explicit SameSite policy compatible with the application's authentication flow."],
        "ro": ["Un cookie nu are o politică SameSite explicită", "Comportamentul între site-uri depinde de setările browserului. Aceasta nu dovedește CSRF.", "Alege o politică SameSite compatibilă cu autentificarea aplicației."],
        "ru": ["У cookie не задана политика SameSite", "Поведение между сайтами зависит от настроек браузера. Это не доказывает CSRF.", "Выберите явную политику SameSite, совместимую с аутентификацией приложения."]},
    "redirect": {
        "en": ["The page redirects elsewhere", "Only the initial response was checked. The destination was not requested and is outside this result's coverage.", "Review the destination and start a separate assessment if it is authorized."],
        "ro": ["Pagina redirecționează către altă adresă", "A fost verificat doar răspunsul inițial. Destinația nu a fost accesată și nu este acoperită de rezultat.", "Verifică destinația și pornește o evaluare separată dacă este autorizată."],
        "ru": ["Страница перенаправляет на другой адрес", "Проверен только исходный ответ. Адрес назначения не запрашивался и не охвачен результатом.", "Проверьте адрес назначения и запустите отдельную проверку при наличии разрешения."]},
    "certificate": {
        "en": ["The TLS certificate could not be validated", "A verified HTTPS connection could not be established. The page was not analyzed over an insecure fallback.", "Check the certificate expiry, hostname, chain, and the computer's trust store and clock."],
        "ro": ["Certificatul TLS nu a putut fi validat", "Nu s-a putut stabili o conexiune HTTPS verificată. Pagina nu a fost analizată printr-o conexiune nesigură.", "Verifică expirarea, domeniul, lanțul certificatului, certificatele de încredere și ceasul calculatorului."],
        "ru": ["Не удалось проверить сертификат TLS", "Проверенное HTTPS-соединение не установлено. Небезопасное соединение не использовалось.", "Проверьте срок, имя, цепочку сертификата, доверенные сертификаты и часы компьютера."]},
}


def finding(code, target, evidence, severity="low", kind="hardening", technical="", tool="moth"):
    text = CATALOG.get(code)
    if text is None:
        text = {lang: [code, "", "Review this result manually."] for lang in ("en", "ro", "ru")}
    digest = hashlib.sha256(f"{tool}|{code}|{target}|{evidence}".encode()).hexdigest()[:16]
    return dict(id=digest, code=code, target=target, severity=severity, kind=kind,
                confidence="observed" if tool == "moth" else "tool-reported",
                tool=tool, evidence=evidence[:3000], technical=technical[:6000], text=text)
