import os, shutil, subprocess, sys, json
from dataclasses import dataclass
from typing import List, Dict

try:
    import winreg
except ImportError:
    winreg = None  # por si no es Windows (fallará los checks)

MIN_DOTNET_RELEASE_461 = 394254  # .NET 4.6.1
REWRITE_URL = "https://www.iis.net/downloads/microsoft/url-rewrite"

@dataclass
class CheckResult:
    name: str
    ok: bool
    info: str = ""
    fix: str = ""

def _ps(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
        capture_output=True, text=True, shell=False
    )

def _reg_get(hive, path, name):
    try:
        k = winreg.OpenKey(hive, path)
        val, _ = winreg.QueryValueEx(k, name)
        winreg.CloseKey(k)
        return val
    except Exception:
        return None

def check_windows_server() -> CheckResult:
    if winreg is None:
        return CheckResult("Windows Server 64-bits 2016 o superior", False, info="Sistema no Windows")
    product = _reg_get(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "ProductName") or ""
    build = _reg_get(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "CurrentBuildNumber") or "0"
    try:
        build_n = int(build)
    except:
        build_n = 0
    ok = ("Server" in str(product)) and (build_n >= 14393)  # 14393 = Server 2016 RTM
    info = f"{product} (build {build})"
    fix = "Requiere Windows Server 2016 o superior x64."
    return CheckResult("Windows Server 64-bits 2016 o superior", ok, info, fix)

def check_iis_version() -> CheckResult:
    if winreg is None:
        return CheckResult("Internet Information Services (IIS) 10 o superior", False, info="Sistema no Windows")
    major = _reg_get(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\InetStp", "MajorVersion")
    info = f"IIS MajorVersion={major}" if major is not None else "IIS no detectado"
    ok = isinstance(major, int) and major >= 10
    fix = "Instala/activa IIS 10+ (Características de Windows: Servidor web (IIS))."
    return CheckResult("Internet Information Services (IIS) 10 o superior", ok, info, fix)

def check_url_rewrite() -> CheckResult:
    # dos señales típicas
    paths = [
        r"C:\Program Files\IIS\URL Rewrite",
        r"C:\Windows\System32\inetsrv\rewrite.dll"
    ]
    exists = any(os.path.exists(p) for p in paths)
    info = "Instalado" if exists else "No detectado"
    fix = f"Instala URL Rewrite desde {REWRITE_URL} (elige arquitectura e idioma del SO)."
    return CheckResult('IIS debe contar con la extensión "URL Rewrite"', exists, info, fix)

def check_dotnet_461() -> CheckResult:
    if winreg is None:
        return CheckResult(".NET Framework 4.6.1 o superior", False, info="Sistema no Windows")
    rel = _reg_get(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full", "Release")
    ok = isinstance(rel, int) and rel >= MIN_DOTNET_RELEASE_461
    info = f"Release={rel}" if rel is not None else "No detectado"
    fix = "Instala .NET Framework 4.6.1 o superior."
    return CheckResult(".NET Framework 4.6.1 o superior", ok, info, fix)

def check_disk_space() -> CheckResult:
    usage = shutil.disk_usage("C:\\")
    free_mb = usage.free // (1024*1024)
    ok = free_mb >= 200
    info = f"Libre: {free_mb} MB (C:)"
    fix = "Libera espacio: requiere al menos 200 MB libres."
    return CheckResult("200 MB de espacio libre para la aplicación", ok, info, fix)

def _service_running(name: str) -> bool:
    cp = _ps(f"Get-Service -Name {name} | Select-Object -ExpandProperty Status")
    return cp.returncode == 0 and "Running" in (cp.stdout or "")

def check_w3svc() -> CheckResult:
    ok = _service_running("W3SVC")
    info = "Running" if ok else "No iniciado / no instalado"
    fix = "Habilita el rol IIS y arranca el servicio 'World Wide Web Publishing Service' (W3SVC)."
    return CheckResult('Servicio "Servidor de publicación World Wide Web"', ok, info, fix)

def check_aspnet_state() -> CheckResult:
    # Service name: aspnet_state (ASP.NET State Service). Se usa como señal de ASP.NET.
    ok = _service_running("aspnet_state")
    info = "Running" if ok else "No iniciado / no instalado"
    fix = "Habilita ASP.NET y el servicio 'ASP.NET State Service' (aspnet_state)."
    return CheckResult('Servicio "Servicio de estado de ASP.NET v4.0.30319"', ok, info, fix)

def run_prereq_check(product: str) -> Dict:
    checks: List[CheckResult] = [
        check_windows_server(),
        check_iis_version(),
        check_url_rewrite(),
        check_dotnet_461(),
        check_disk_space(),
        check_w3svc(),
        check_aspnet_state(),
    ]
    missing = [c.name for c in checks if not c.ok]
    return {
        "product": product,
        "ok": len(missing) == 0,
        "results": [c.__dict__ for c in checks],
        "missing": missing,
        "rewrite_download": REWRITE_URL,
    }
