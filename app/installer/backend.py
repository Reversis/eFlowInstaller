# app/installer/backend.py
import re
import os
import shutil
import tempfile
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Dict, Optional

# ===================== Logging =====================
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _new_log() -> Path:
    return LOG_DIR / f"backend_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

def _log(fp: Path, msg: str) -> None:
    with open(fp, "a", encoding="utf-8") as f:
        f.write(f"[{_ts()}] {msg}\n")

# ===================== Lectura robusta =====================
_PREFERRED_ENCODINGS = [
    "utf-8-sig",
    "utf-16",
    "utf-16le",
    "cp1252",
    "latin-1",
]

def _read_text_any(path: Path) -> str:
    last_err = None
    for enc in _PREFERRED_ENCODINGS:
        try:
            return path.read_text(encoding=enc, errors="strict")
        except Exception as e:
            last_err = e
            continue
    return path.read_text(encoding="utf-8", errors="replace")

# ===================== Sanitización (configurable) =====================
_BAD_CHARS = {
    "\u00B6",  # PILCROW (¶)
    "\uFEFF",  # BOM
    "\u200B",  # zero-width space
    "\u200C",  # ZWNJ
    "\u200D",  # ZWJ
    "\u2028",  # line sep
    "\u2029",  # para sep
    "\u00A0",  # NBSP
}

def _scan_non_ascii_lines(txt: str) -> list[tuple[int, str, list[str]]]:
    """
    Devuelve (line_number, excerpt, [U+XXXX...]) para líneas con no-ASCII (1-based).
    """
    out = []
    lines = txt.splitlines()
    for i, line in enumerate(lines, 1):
        bads = [c for c in line if c not in ("\r", "\n", "\t") and (ord(c) < 32 or ord(c) > 126)]
        if bads:
            hexes = [f"U+{ord(c):04X}" for c in bads]
            excerpt = line if len(line) <= 160 else (line[:157] + "...")
            out.append((i, excerpt, hexes))
    return out

def sanitize_sql_text_aggressive(txt: str) -> tuple[str, int, list[tuple[int, str, list[str]]]]:
    """
    AGGRESSIVE: elimina invisibles + TODO no-ASCII (excepto \r\n\t).
    Inserta espacio tras keywords si quedaron pegados.
    """
    import unicodedata, re as _re

    changes = 0
    non_ascii_report = _scan_non_ascii_lines(txt)

    n = unicodedata.normalize("NFKC", txt)
    for ch in _BAD_CHARS:
        if ch in n:
            n = n.replace(ch, "")
            changes += 1

    cleaned = []
    for c in n:
        if c in ("\r", "\n", "\t"):
            cleaned.append(c); continue
        o = ord(c)
        if 32 <= o <= 126:
            cleaned.append(c)
        else:
            changes += 1
            continue
    n = "".join(cleaned)

    # EOL -> CRLF
    n = n.replace("\r\n", "\n").replace("\r", "\n")
    n = n.replace("\n", "\r\n")

    # Keywords pegados
    n2 = _re.sub(r"\b(DELETE|UPDATE|INSERT|SELECT)(?!\s)", r"\1 ", n, flags=_re.IGNORECASE)
    if n2 != n:
        changes += 1
        n = n2

    return n, changes, non_ascii_report

def sanitize_sql_text_light(txt: str) -> tuple[str, int, list[tuple[int, str, list[str]]]]:
    """
    LIGHT: remueve invisibles (BOM/ZWSP/NBSP/¶) y controles peligrosos.
    Conserva acentos/ñ. Normaliza EOL. Arregla keywords pegados.
    """
    import unicodedata, re as _re

    changes = 0
    non_ascii_report = _scan_non_ascii_lines(txt)

    n = unicodedata.normalize("NFKC", txt)
    for ch in _BAD_CHARS:
        if ch in n:
            n = n.replace(ch, "")
            changes += 1

    cleaned = []
    for c in n:
        if c in ("\r", "\n", "\t"):
            cleaned.append(c); continue
        cat = unicodedata.category(c)
        if cat in ("Zl", "Zp", "Cc") and c != " ":
            changes += 1; continue
        cleaned.append(c)
    n = "".join(cleaned)

    n = n.replace("\r\n", "\n").replace("\r", "\n")
    n = n.replace("\n", "\r\n")

    n2 = _re.sub(r"\b(DELETE|UPDATE|INSERT|SELECT)(?!\s)", r"\1 ", n, flags=_re.IGNORECASE)
    if n2 != n:
        changes += 1
        n = n2

    return n, changes, non_ascii_report

def sanitize_sql_file(path: Path, log: Path, *, level: str = "light", report_non_ascii: bool = True) -> None:
    try:
        txt = _read_text_any(path)
        if level == "aggressive":
            new_txt, changes, non_ascii_report = sanitize_sql_text_aggressive(txt)
        elif level == "light":
            new_txt, changes, non_ascii_report = sanitize_sql_text_light(txt)
        else:
            _log(log, f"🧪 {path.name}: sanitización nivel 'none', sin cambios")
            return

        if report_non_ascii and non_ascii_report:
            _log(log, f"🔎 {path.name}: líneas con no-ASCII detectadas ({len(non_ascii_report)}):")
            for ln, excerpt, hexes in non_ascii_report[:30]:
                _log(log, f"    L{ln:04d}: {' '.join(hexes)}  ::  {excerpt}")
            if len(non_ascii_report) > 30:
                _log(log, f"    … {len(non_ascii_report)-30} líneas adicionales")

        if changes > 0:
            path.write_text(new_txt, encoding="utf-8")
            _log(log, f"🧼 Sanitizado {path.name}: {changes} limpieza(s) aplicada(s)")
        else:
            _log(log, f"✅ {path.name}: sin cambios de sanitización")
    except Exception as e:
        _log(log, f"⚠️ No se pudo sanear {path.name}: {e}")

# ===================== Reemplazo de nombre de BD en [] =====================
_RESERVED_BKT = {
    "dbo", "PRIMARY", "MGMT", "SYS", "INFORMATION_SCHEMA", "TEMPDB", "MODEL", "MSDB", "MASTER"
}

_RE_USE_DB     = re.compile(r'(\bUSE\s*\[)([^\]]*)(\])', re.IGNORECASE)
_RE_CREATE_DB  = re.compile(r'(\bCREATE\s+DATABASE\s*\[)([^\]]*)(\])', re.IGNORECASE)
_RE_ALTER_DB   = re.compile(r'(\bALTER\s+DATABASE\s*\[)([^\]]*)(\])', re.IGNORECASE)
_RE_DROP_DB    = re.compile(r'(\bDROP\s+DATABASE\s*\[)([^\]]*)(\])', re.IGNORECASE)
_RE_BACKUP_DB  = re.compile(r'(\bBACKUP\s+DATABASE\s*\[)([^\]]*)(\])', re.IGNORECASE)
_RE_RESTORE_DB = re.compile(r'(\bRESTORE\s+DATABASE\s*\[)([^\]]*)(\])', re.IGNORECASE)
_RE_DATABASE_SCOPE = re.compile(r'(\bDATABASE::\s*\[)([^\]]*)(\])', re.IGNORECASE)
_RE_ALTER_AUTH = re.compile(r'(\bALTER\s+AUTHORIZATION\s+ON\s+DATABASE::\s*\[)([^\]]*)(\])', re.IGNORECASE)
_RE_EMPTY_BKT  = re.compile(r'\[\s*\]')

def _is_reserved(name: str) -> bool:
    return name.strip().strip('"').strip("'").upper() in (s.upper() for s in _RESERVED_BKT)

def _sub_db(regex: re.Pattern, text: str, db_name: str) -> tuple[str, int]:
    cnt = 0
    def _sub(m):
        nonlocal cnt
        name = (m.group(2) or "").strip()
        if name and _is_reserved(name):
            return m.group(0)
        cnt += 1
        return f"{m.group(1)}{db_name}{m.group(3)}"
    return regex.sub(_sub, text), cnt

def _replace_db_name_in_sql_text(sql: str, db_name: str) -> tuple[str, int]:
    total = 0
    sql, c = _sub_db(_RE_USE_DB,     sql, db_name); total += c
    sql, c = _sub_db(_RE_CREATE_DB,  sql, db_name); total += c
    sql, c = _sub_db(_RE_ALTER_DB,   sql, db_name); total += c
    sql, c = _sub_db(_RE_DROP_DB,    sql, db_name); total += c
    sql, c = _sub_db(_RE_BACKUP_DB,  sql, db_name); total += c
    sql, c = _sub_db(_RE_RESTORE_DB, sql, db_name); total += c
    sql, c = _sub_db(_RE_ALTER_AUTH, sql, db_name); total += c
    sql, c = _sub_db(_RE_DATABASE_SCOPE, sql, db_name); total += c

    def _empty_sub(_m):
        nonlocal total
        total += 1
        return f"[{db_name}]"
    sql = _RE_EMPTY_BKT.sub(_empty_sub, sql)
    return sql, total

def replace_db_brackets_in_file(path: Path, db_name: str, log: Path) -> None:
    try:
        txt = _read_text_any(path)
        new_txt, n = _replace_db_name_in_sql_text(txt, db_name)
        if n > 0:
            path.write_text(new_txt, encoding="utf-8")
            _log(log, f"🔁 {path.name}: reemplazos de BD en [] = {n}")
        else:
            _log(log, f"ℹ️ {path.name}: sin reemplazos de BD en []")
    except Exception as e:
        _log(log, f"❌ Error procesando {path.name} para corchetes de BD: {e}")

# ===================== Detección de CREATE DATABASE =====================
CREATE_DB_RE = re.compile(r'\bCREATE\s+DATABASE\b', re.IGNORECASE)

def _script_contains_create_db(path: Path) -> bool:
    try:
        txt = _read_text_any(path)
        return bool(CREATE_DB_RE.search(txt))
    except Exception:
        return False

# ===================== Reescritura MDF/LDF =====================
MDF_RE = re.compile(r"(FILENAME\s*=\s*N?['\"])([^'\"]*?\.mdf)(['\"])", re.IGNORECASE)
LDF_RE = re.compile(r"(FILENAME\s*=\s*N?['\"])([^'\"]*?\.ldf)(['\"])", re.IGNORECASE)
NAME_DATA_RE = re.compile(r"(NAME\s*=\s*N?['\"])([^'\"\\]*?)(_?Data)(['\"])", re.IGNORECASE)
NAME_LOG_RE  = re.compile(r"(NAME\s*=\s*N?['\"])([^'\"\\]*?)(_?Log)(['\"])",  re.IGNORECASE)

def _rewrite_file_paths_in_sql_text(sql: str, db_name: str, mdf_dir: Optional[str], ldf_dir: Optional[str]) -> tuple[str, int, int]:
    changes_path = 0
    changes_name = 0

    def norm_dir(d: Optional[str]) -> Optional[str]:
        if not d: return None
        d = d.rstrip("\\/"); return d + "\\"
    mdf_dir = norm_dir(mdf_dir)
    ldf_dir = norm_dir(ldf_dir) or mdf_dir

    def _mdf_sub(m: re.Match) -> str:
        nonlocal changes_path
        if not mdf_dir: return m.group(0)
        changes_path += 1
        return f"{m.group(1)}{mdf_dir}{db_name}_Data.mdf{m.group(3)}"

    def _ldf_sub(m: re.Match) -> str:
        nonlocal changes_path
        if not ldf_dir: return m.group(0)
        changes_path += 1
        return f"{m.group(1)}{ldf_dir}{db_name}_Log.ldf{m.group(3)}"

    sql = MDF_RE.sub(_mdf_sub, sql)
    sql = LDF_RE.sub(_ldf_sub, sql)

    def _name_data_sub(m: re.Match) -> str:
        nonlocal changes_name
        changes_name += 1
        return f"{m.group(1)}{db_name}_Data{m.group(4)}"

    def _name_log_sub(m: re.Match) -> str:
        nonlocal changes_name
        changes_name += 1
        return f"{m.group(1)}{db_name}_Log{m.group(4)}"

    sql = NAME_DATA_RE.sub(_name_data_sub, sql)
    sql = NAME_LOG_RE.sub(_name_log_sub, sql)
    return sql, changes_path, changes_name

def _rewrite_file_paths_in_file(path: Path, db_name: str, mdf_dir: Optional[str], ldf_dir: Optional[str], log: Path) -> None:
    if not (mdf_dir or ldf_dir):
        return
    try:
        txt = _read_text_any(path)
        new_txt, n_path, n_name = _rewrite_file_paths_in_sql_text(txt, db_name, mdf_dir, ldf_dir)
        if n_path > 0 or n_name > 0:
            path.write_text(new_txt, encoding="utf-8")
            det = []
            if n_path: det.append(f"rutas: {n_path}")
            if n_name: det.append(f"name: {n_name}")
            _log(log, f"🛠️ {path.name}: reescrituras ({', '.join(det)})")
        else:
            _log(log, f"ℹ️ {path.name}: sin match de FILENAME/NAME para MDF/LDF (revisa comillas o prefijo N)")
    except Exception as e:
        _log(log, f"⚠️ No se pudo reescribir rutas en {path.name}: {e}")

# ===================== Personalización de 1-2 usuarios =====================
CREATE_LOGIN_BLOCK = re.compile(
    r"(?P<head>\bCREATE\s+LOGIN\s+\[?)(?P<name>[^\]\s]+)(?P<mid>\]?\s+WITH\b)(?P<body>.*?)(?=(;|\r?\nGO\b|\Z))",
    re.IGNORECASE | re.DOTALL
)
RE_LOGIN_PWD  = re.compile(r"(\bPASSWORD\s*=\s*N?['\"])([^'\"\r\n]*)(['\"])", re.IGNORECASE)
CREATE_USER_BLOCK = re.compile(
    r"(?P<head>\bCREATE\s+USER\s+\[?)(?P<uname>[^\]\s]+)(?P<end>\]?)(?P<body>.*?)(?=(;|\r?\nGO\b|\Z))",
    re.IGNORECASE | re.DOTALL
)
RE_FOR_LOGIN  = re.compile(r"(\bFOR\s+LOGIN\s+\[?)([^\]\s]+)(\]?)", re.IGNORECASE)
RE_PLACE_U  = re.compile(r"\{\{\s*APP_USER\s*\}\}", re.IGNORECASE)
RE_PLACE_P  = re.compile(r"\{\{\s*APP_PASS\s*\}\}", re.IGNORECASE)
RE_PLACE_U2 = re.compile(r"\{\{\s*APP_USER2\s*\}\}", re.IGNORECASE)
RE_PLACE_P2 = re.compile(r"\{\{\s*APP_PASS2\s*\}\}", re.IGNORECASE)

def _customize_two_users_sql_text(sql: str, users: List[Tuple[Optional[str], Optional[str]]]) -> tuple[str, int]:
    if not users:
        return sql, 0
    changes = 0

    # placeholders explícitos
    if len(users) >= 1:
        u1, p1 = users[0]
        if u1 and RE_PLACE_U.search(sql): sql = RE_PLACE_U.sub(u1, sql); changes += 1
        if p1 and RE_PLACE_P.search(sql): sql = RE_PLACE_P.sub(p1, sql); changes += 1
    if len(users) >= 2:
        u2, p2 = users[1]
        if u2 and RE_PLACE_U2.search(sql): sql = RE_PLACE_U2.sub(u2, sql); changes += 1
        if p2 and RE_PLACE_P2.search(sql): sql = RE_PLACE_P2.sub(p2, sql); changes += 1

    # bloques CREATE LOGIN / CREATE USER (primeros 2 match)
    idx = 0
    def sub_login(m: re.Match) -> str:
        nonlocal changes, idx
        if idx >= len(users): return m.group(0)
        name_new, pass_new = users[idx]
        head = m.group('head'); mid = m.group('mid'); body = m.group('body')
        if pass_new:
            body, n = RE_LOGIN_PWD.subn(rf"\1{pass_new}\3", body); changes += n
        if name_new:
            changes += 1
            repl = f"{head}{name_new}{mid}{body}"
        else:
            repl = f"{head}{m.group('name')}{mid}{body}"
        idx += 1
        return repl
    sql = CREATE_LOGIN_BLOCK.sub(sub_login, sql)

    idx_user = 0
    def sub_user(m: re.Match) -> str:
        nonlocal changes, idx_user
        if idx_user >= len(users): return m.group(0)
        name_new = users[idx_user][0]
        head = m.group('head'); end = m.group('end'); body = m.group('body')
        if name_new:
            changes += 1
            uname_part = f"{head}{name_new}{end}"
            body, n = RE_FOR_LOGIN.subn(rf"\1{name_new}\3", body); changes += n
        else:
            uname_part = f"{head}{m.group('uname')}{end}"
        idx_user += 1
        return f"{uname_part}{body}"
    sql = CREATE_USER_BLOCK.sub(sub_user, sql)

    return sql, changes

def _customize_users_in_file(path: Path, users: List[Tuple[Optional[str], Optional[str]]], log: Path) -> None:
    try:
        txt = _read_text_any(path)
        needs = (
            CREATE_LOGIN_BLOCK.search(txt) or
            CREATE_USER_BLOCK.search(txt) or
            re.search(r"user|usuarios", path.name, re.IGNORECASE)
        )
        if not needs: return
        new_txt, n = _customize_two_users_sql_text(txt, users)
        if n > 0:
            path.write_text(new_txt, encoding="utf-8")
            _log(log, f"👤 {path.name}: personalización de usuarios ({n} cambio/s)")
    except Exception as e:
        _log(log, f"⚠️ No se pudo personalizar usuarios en {path.name}: {e}")

# ===================== sqlcmd helpers =====================
def _db_exists(sql_server: str, user: str, password: str, windows_auth: bool, db_name: str) -> bool:
    safe_db = db_name.replace("'", "''")
    q = f"SET NOCOUNT ON; IF DB_ID(N'{safe_db}') IS NOT NULL SELECT 1 ELSE SELECT 0;"
    if windows_auth:
        cmd = f'sqlcmd -S "{sql_server}" -E -d "master" -Q "{q}" -h -1 -W -b'
    else:
        cmd = f'sqlcmd -S "{sql_server}" -U "{user}" -P "{password}" -d "master" -Q "{q}" -h -1 -W -b'
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0: return False
    try:
        last = res.stdout.strip().splitlines()[-1].strip()
        return last == "1"
    except Exception:
        return False

def _sqlcmd(sql_server: str, user: str, password: str, database: str,
            script_path: Path, windows_auth: bool) -> Tuple[int, str, str]:
    script = str(script_path)
    if windows_auth:
        cmd = f'sqlcmd -S "{sql_server}" -E -d "{database}" -i "{script}" -b -r1'
    else:
        cmd = f'sqlcmd -S "{sql_server}" -U "{user}" -P "{password}" -d "{database}" -i "{script}" -b -r1'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def _exec_tsql(sql_server: str, user: str, password: str, windows_auth: bool,
               database: str, query: str) -> Tuple[int, str, str]:
    if windows_auth:
        cmd = f'sqlcmd -S "{sql_server}" -E -d "{database}" -Q "{query}" -b -r1'
    else:
        cmd = f'sqlcmd -S "{sql_server}" -U "{user}" -P "{password}" -d "{database}" -Q "{query}" -b -r1'
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr

# ===================== Preprovisión/mapeo de logins/usuarios =====================
def _ensure_login(sql_server: str, user: str, password: str, windows_auth: bool,
                  login_name: str, login_pass: Optional[str], log: Path) -> None:
    if not login_name: return
    safe_login = login_name.replace("'", "''")
    q = (
        "SET NOCOUNT ON; "
        f"IF SUSER_ID(N'{safe_login}') IS NULL "
        f"BEGIN CREATE LOGIN [{login_name}] WITH PASSWORD = N'{login_pass or 'Temp#1234'}'; END "
        "ELSE BEGIN SELECT 1; END"
    )
    code, out, err = _exec_tsql(sql_server, user, password, windows_auth, "master", q)
    if code != 0:
        _log(log, f"⚠️ ensure_login: error creando/verificando [{login_name}]:\n{err or out}")
        return
    _log(log, f"🔐 LOGIN '{login_name}': existe/creado OK")

    if login_pass:
        q2 = f"ALTER LOGIN [{login_name}] WITH PASSWORD = N'{login_pass}';"
        code2, out2, err2 = _exec_tsql(sql_server, user, password, windows_auth, "master", q2)
        if code2 == 0:
            _log(log, f"🔑 LOGIN '{login_name}': password actualizado")
        else:
            _log(log, f"⚠️ LOGIN '{login_name}': no se pudo actualizar password:\n{err2 or out2}")

def _ensure_db_user(sql_server: str, user: str, password: str, windows_auth: bool,
                    db_name: str, db_user: str, login_name: str, log: Path) -> None:
    if not db_user or not login_name: return
    safe_user = db_user.replace("'", "''")
    q = (
        "SET NOCOUNT ON; "
        f"IF USER_ID(N'{safe_user}') IS NULL "
        f"BEGIN CREATE USER [{db_user}] FOR LOGIN [{login_name}]; END "
        f"ELSE BEGIN ALTER USER [{db_user}] WITH LOGIN = [{login_name}]; END"
    )
    code, out, err = _exec_tsql(sql_server, user, password, windows_auth, db_name, q)
    if code == 0:
        _log(log, f"👤 USER '{db_user}'@'{db_name}': creado/mapeado a LOGIN '{login_name}'")
    else:
        _log(log, f"⚠️ USER '{db_user}': fallo en mapeo/creación:\n{err or out}")

def _preprovision_users(sql_server: str, admin_user: str, admin_pass: str, windows_auth: bool,
                        db_name: str, users: List[Tuple[Optional[str], Optional[str]]], log: Path) -> None:
    for idx, (uname, upass) in enumerate(users, start=1):
        if not uname:
            continue
        _log(log, f"▶ Preprovisión U{idx}: login='{uname}'")
        _ensure_login(sql_server, admin_user, admin_pass, windows_auth, uname, upass, log)
        _ensure_db_user(sql_server, admin_user, admin_pass, windows_auth, db_name, uname, uname, log)

# ===================== Ordenamiento =====================
NUM_RE = re.compile(r'(^|[^0-9])(?P<num>\d+)')

def ordenar_scripts(scripts: List[Path]) -> List[Path]:
    def key(p: Path):
        m = NUM_RE.search(p.name)
        num = int(m.group("num")) if m else 10**9
        return (num, p.name.lower())
    return sorted(scripts, key=key)

# ===================== Reemplazos literales (sólo CREATE DATABASE) =====================
def reemplazar_en_archivo(ruta: Path, reemplazos: Dict[str, str], log: Path) -> None:
    if not ruta.exists():
        _log(log, f"⚠️  No existe: {ruta}")
        return
    try:
        content = _read_text_any(ruta)
        original = content
        for k, v in reemplazos.items():
            content = content.replace(k, v)
        if content != original:
            ruta.write_text(content, encoding="utf-8")
            _log(log, f"✅ Reemplazos aplicados: {ruta.name}")
        else:
            _log(log, f"ℹ️  Sin cambios (no coincidencias): {ruta.name}")
    except Exception as e:
        _log(log, f"❌ Error reemplazando en {ruta.name}: {e}")

# ===================== Pipeline principal =====================
def run_backend_installation(form, files=None) -> Dict[str, str]:
    """
    Soporta carpeta o drag&drop de .sql.
    - Tokens sólo en scripts con CREATE DATABASE. MDF_DIR/LDF_DIR reescriben FILENAME.
    - Reemplazo de [DB] en corchetes.
    - Personalización y preprovisión de 1-2 usuarios (logins + users).
    - Sanitización selectiva: scope/level/regex/report.
    """
    log = _new_log()
    staged_dir: Optional[Path] = None

    try:
        sql_server   = (form.get('sql_server') or '').strip()
        db_name      = (form.get('db_name') or 'master').strip()
        admin_user   = (form.get('user') or '').strip()
        admin_pass   = (form.get('password') or '').strip()
        windows_auth = (form.get('windows_auth') or '').lower() in ('1','true','on','yes')
        target_path  = (form.get('target_path') or '').strip()
        scripts_dir  = (form.get('scripts_dir') or '').strip()

        tokens_raw = (form.get('tokens') or '').strip()
        tokens: Dict[str, str] = {}
        if tokens_raw:
            for line in tokens_raw.splitlines():
                if '=' in line:
                    k, v = line.split('=', 1)
                    tokens[k.strip()] = v.strip()
        mdf_dir = tokens.get("MDF_DIR")
        ldf_dir = tokens.get("LDF_DIR")

        u1 = (form.get('app_login') or '').strip() or None
        p1 = (form.get('app_password') or '').strip() or None
        u2 = (form.get('app_login2') or '').strip() or None
        p2 = (form.get('app_password2') or '').strip() or None
        users: List[Tuple[Optional[str], Optional[str]]] = []
        if u1 or p1: users.append((u1, p1))
        if u2 or p2: users.append((u2, p2))

        # Controles de sanitización desde el front
        sanitize_scope  = (form.get('sanitize_scope')  or 'matching').lower()   # none|all|matching
        sanitize_level  = (form.get('sanitize_level')  or 'light').lower()      # none|light|aggressive
        sanitize_match  = (form.get('sanitize_match')  or r'^002.*\.sql$').strip()
        sanitize_report = (form.get('sanitize_report') or 'on').lower() in ('1','true','on','yes')

        _log(log, f"▶ Parámetros: server={sql_server}, db={db_name}, winAuth={windows_auth}, scripts_dir={scripts_dir or '(upload)'}")

        # Fuente de scripts
        scripts: List[Path] = []
        if scripts_dir:
            base = Path(scripts_dir).expanduser()
            if not base.exists():
                raise FileNotFoundError(f"Carpeta de scripts no existe: {base}")
            scripts = [p for p in base.glob("*.sql") if p.is_file()]
        else:
            staged_dir = Path(tempfile.mkdtemp(prefix="sqlscripts_"))
            if files:
                for f in files.getlist('scripts[]'):
                    if not f.filename.lower().endswith('.sql'):
                        continue
                    dest = staged_dir / Path(f.filename).name
                    f.save(dest)
                    scripts.append(dest)

        if not scripts:
            raise RuntimeError("No se encontraron scripts .sql para ejecutar.")

        scripts = ordenar_scripts(scripts)
        _log(log, "🗂  Orden de ejecución:")
        for i, s in enumerate(scripts, 1):
            _log(log, f"   {i:02d}. {s.name}")

        # Tokens sólo en CREATE DATABASE
        if tokens:
            db_scripts = [p for p in scripts if _script_contains_create_db(p)]
            if db_scripts:
                _log(log, f"🔁 Aplicando tokens literales en {len(db_scripts)} script(s) con CREATE DATABASE. Claves: {', '.join(tokens.keys())}")
                for s in db_scripts:
                    reemplazar_en_archivo(s, tokens, log)
            else:
                _log(log, "⏭️  Tokens definidos pero NO aplicados: no hay scripts con 'CREATE DATABASE'.")

        # Regex para sanitización "matching"
        match_re = None
        if sanitize_scope == 'matching' and sanitize_level != 'none':
            try:
                match_re = re.compile(sanitize_match, re.IGNORECASE)
            except Exception:
                match_re = None

        total_ok = 0
        users_provisioned = False

        for idx, s in enumerate(scripts, 1):
            _log(log, f"▶ Ejecutando [{idx}/{len(scripts)}] {s.name} …")

            # 0) SANITIZACIÓN selectiva
            do_sanitize = False
            if sanitize_level == 'none' or sanitize_scope == 'none':
                do_sanitize = False
            elif sanitize_scope == 'all':
                do_sanitize = True
            elif sanitize_scope == 'matching':
                do_sanitize = bool(match_re and match_re.search(s.name))

            if do_sanitize:
                sanitize_sql_file(s, log, level=sanitize_level, report_non_ascii=sanitize_report)
            else:
                _log(log, f"🧪 {s.name}: sanitización omitida (scope={sanitize_scope}, level={sanitize_level})")

            # 0.5) Personalizar usuarios (si aplica)
            if users:
                _customize_users_in_file(s, users, log)

            # 1) Reemplazo [DB]
            replace_db_brackets_in_file(s, db_name, log)

            # 1.5) Reescribir MDF/LDF
            _rewrite_file_paths_in_file(s, db_name, mdf_dir, ldf_dir, log)

            # 2) Elegir DB de conexión
            connect_db = db_name
            try:
                creates_db = _script_contains_create_db(s)
                exists = _db_exists(sql_server, admin_user, admin_pass, windows_auth, db_name)
                if creates_db or not exists:
                    connect_db = "master"
                    _log(log, f"ℹ️ {s.name}: conectando a master (creates_db={creates_db}, exists={exists})")
                else:
                    _log(log, f"ℹ️ {s.name}: conectando a {db_name} (exists={exists})")
                    if users and not users_provisioned:
                        _log(log, f"▶ Preprovisión de logins/usuarios en '{db_name}' (una sola vez)")
                        _preprovision_users(sql_server, admin_user, admin_pass, windows_auth, db_name, users, log)
                        users_provisioned = True
            except Exception as e:
                connect_db = "master"
                _log(log, f"⚠️ No se pudo verificar existencia de BD: {e}. Usando master para {s.name}.")

            # 3) Ejecutar script
            code, out, err = _sqlcmd(sql_server, admin_user, admin_pass, connect_db, s, windows_auth)
            if out: _log(log, f"STDOUT:\n{out}")
            if err: _log(log, f"STDERR:\n{err}")
            if code != 0:
                _log(log, f"❌ Error en {s.name} (exit={code}). Abortando.")
                raise RuntimeError(f"Error ejecutando {s.name} (exit={code}).")
            _log(log, f"✅ OK {s.name}")
            total_ok += 1

            # Preprovisión post-CREATE DATABASE (si aplica)
            if users and not users_provisioned and _script_contains_create_db(s):
                if _db_exists(sql_server, admin_user, admin_pass, windows_auth, db_name):
                    _log(log, f"▶ Preprovisión posterior a CREATE DATABASE en '{db_name}'")
                    _preprovision_users(sql_server, admin_user, admin_pass, windows_auth, db_name, users, log)
                    users_provisioned = True

        # .BAT opcional
        if target_path:
            bat_path = Path(target_path) / "ejecutar_restantes.bat"
            if bat_path.exists():
                _log(log, f"▶ Ejecutando .BAT opcional: {bat_path}")
                res = subprocess.run(str(bat_path), shell=True, capture_output=True, text=True)
                _log(log, f"STDOUT:\n{res.stdout}")
                _log(log, f"STDERR:\n{res.stderr}")
                if res.returncode != 0:
                    raise RuntimeError(f"El .BAT devolvió código {res.returncode}")

        _log(log, f"🎉 Finalizado. Scripts OK: {total_ok}/{len(scripts)}")
        return {"status": "success", "output": log.read_text(encoding="utf-8"), "log_file": str(log)}

    except Exception as e:
        _log(log, f"💥 ERROR: {e}")
        return {"status": "error", "output": log.read_text(encoding="utf-8"), "log_file": str(log)}

    finally:
        try:
            if staged_dir and staged_dir.exists():
                shutil.rmtree(staged_dir, ignore_errors=True)
        except Exception:
            pass
