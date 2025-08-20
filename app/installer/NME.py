import os, re, shutil, datetime

# ----------------------------------------------------
# Helper: reemplazo seguro con backup + logging simple
# ----------------------------------------------------
def replace_cadena(file_path: str, pattern: str, replacement: str, log_file: str, dt: str):
    """
    Reemplaza 'pattern' (regex) por 'replacement' en file_path.
    - Crea backup: <archivo>.<YYYYmmdd_HHMMSS>.bak
    - Escribe en log_file (append).
    """
    # Normaliza ruta para Windows
    file_path = os.path.normpath(file_path)

    # Logging helper
    def _log(msg: str):
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{dt}] {msg}\n")
        except Exception:
            pass

    if not os.path.isfile(file_path):
        _log(f"WARNING: no existe el archivo: {file_path}")
        return False

    # Backup
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.{ts}.bak"
    try:
        shutil.copy2(file_path, backup_path)
        _log(f"Backup creado: {backup_path}")
    except Exception as e:
        _log(f"ERROR al crear backup de {file_path}: {e}")

    # Lee y reemplaza
    try:
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="cp1252", errors="replace") as f:
                text = f.read()

        new_text, n = re.subn(pattern, replacement, text, flags=re.IGNORECASE | re.MULTILINE)
        if n == 0:
            _log(f"AVISO: no hubo coincidencias en {file_path} con patrón: {pattern}")
        else:
            _log(f"OK: {n} reemplazo(s) en {file_path} con patrón: {pattern}")

        if n > 0:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_text)
        return n > 0
    except Exception as e:
        _log(f"ERROR al reemplazar en {file_path}: {e}")
        return False


# ----------------------------------------------------
# Configuraciones Emission según lo que pediste
# ----------------------------------------------------
def configurarNME(path: str, server: str, eflow: str, eflowApi: str, loggin: str, dt: str):
    """
    Actualiza:
      - FrontEnd/Sidesys.eFlow.Emission.API/Web.config  -> eFlowServiceUrl
      - FrontEnd/STE/SPA/assets/configuration/emission.config.json -> emissionApiEndpoint

    Ejemplo resultante:
      eFlowServiceUrl = http://{server}/{eflow}/Services/EmissionService.svc
      emissionApiEndpoint = http://{server}/{eflowApi}
    """
    web_config = os.path.join(path, r'FrontEnd', r'Sidesys.eFlow.Emission.API', 'Web.config')
    json_cfg   = os.path.join(path, r'FrontEnd', r'STE', r'SPA', r'assets', r'configuration', 'emission.config.json')

    # Patrón XML (clave eFlowServiceUrl) -> usamos regex robusto (hasta la comilla)
    pattern_service_url = r'<add\s+key="eFlowServiceUrl"\s+value="http://[^"]+/Services/EmissionService\.svc"'
    repl_service_url    = f'<add key="eFlowServiceUrl" value="http://{server}/{eflow}/Services/EmissionService.svc"'

    replace_cadena(web_config, pattern_service_url, repl_service_url, loggin, dt)

    # Patrón JSON emissionApiEndpoint (valor hasta comilla)
    pattern_api_endpoint = r'"emissionApiEndpoint"\s*:\s*"[^"]*",'
    repl_api_endpoint    = f'"emissionApiEndpoint": "http://{server}/{eflowApi}",'

    replace_cadena(json_cfg, pattern_api_endpoint, repl_api_endpoint, loggin, dt)


def configurarNMESite(path: str, server: str, eflow: str, eflowApi: str, loggin: str, dt: str):
    """
    Variante con PUERTO (Site):
      - FrontEnd/Sidesys.eFlow.Emission.API/Web.config:
          eFlowServiceUrl = http://{server}:{eflow}/Services/EmissionService.svc
          AllowedCrossOrigins = http://{server}:{eflow}
      - FrontEnd/STE/SPA/assets/configuration/emission.config.json:
          emissionApiEndpoint = http://{server}:{eflowApi}
    """
    web_config = os.path.join(path, r'FrontEnd', r'Sidesys.eFlow.Emission.API', 'Web.config')
    json_cfg   = os.path.join(path, r'FrontEnd', r'STE', r'SPA', r'assets', r'configuration', 'emission.config.json')

    # eFlowServiceUrl con puerto
    pattern_service_url = r'<add\s+key="eFlowServiceUrl"\s+value="http://[^"]+/Services/EmissionService\.svc"'
    repl_service_url    = f'<add key="eFlowServiceUrl" value="http://{server}:{eflow}/Services/EmissionService.svc"'
    replace_cadena(web_config, pattern_service_url, repl_service_url, loggin, dt)

    # AllowedCrossOrigins (valor hasta comilla). Dejamos flexible espacios.
    pattern_allowed = r'<add\s+key="AllowedCrossOrigins"\s+value="[^"]+"'
    repl_allowed    = f'<add key="AllowedCrossOrigins" value="http://{server}:{eflow}"'
    replace_cadena(web_config, pattern_allowed, repl_allowed, loggin, dt)

    # emissionApiEndpoint con puerto
    pattern_api_endpoint = r'"emissionApiEndpoint"\s*:\s*"[^"]*",'
    repl_api_endpoint    = f'"emissionApiEndpoint": "http://{server}:{eflowApi}",'
    replace_cadena(json_cfg, pattern_api_endpoint, repl_api_endpoint, loggin, dt)
