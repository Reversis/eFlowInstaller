import os
import subprocess
from datetime import datetime

LOG_DIR = "logs"


def guardar_log(logs):
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    fecha = datetime.now().strftime('%Y-%m-%d')
    log_file_path = os.path.join(LOG_DIR, f"ncache_{fecha}.log")
    with open(log_file_path, "a", encoding="utf-8") as f:
        for linea in logs:
            f.write(f"{linea}\n")
    return log_file_path


def reemplazar_en_archivo(ruta, reemplazos):
    with open(ruta, 'r', encoding='utf-8') as file:
        contenido = file.read()
    for original, nuevo in reemplazos.items():
        contenido = contenido.replace(original, nuevo)
    with open(ruta, 'w', encoding='utf-8') as file:
        file.write(contenido)


def run_ncache_installation(form_data):
    try:
        ruta_msi = form_data.get("ncache_msi")  # Ruta al archivo ncache.opensource.clr40.x64.msi
        server_name = form_data.get("server_name")  # IP o nombre del servidor
        server_port = form_data.get("server_port", "9800")
        cache_name = form_data.get("cache_name", "myCache")
        ruta_frontend = form_data.get("frontend_path")
        ruta_middleware = form_data.get("middleware_path")

        logs = []

        # 1. Ejecutar instalador MSI
        command = f'msiexec.exe /i "{ruta_msi}" /qn'
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        logs.append(f"[{datetime.now()}] ▶ Instalación NCache:\n{result.stdout or result.stderr}")
        if result.returncode != 0:
            raise Exception("❌ Error instalando NCache")

        # 2. Iniciar servicio NCache (en caso no se haya levantado)
        subprocess.run("net start NCacheSvc", shell=True)
        logs.append(f"[{datetime.now()}] ✔ Servicio NCache iniciado")

        # 3. Ejecutar PowerShell para iniciar cache
        subprocess.run(f'powershell -Command "Start-Cache -Name {cache_name}"', shell=True)
        logs.append(f"[{datetime.now()}] ✔ Cache '{cache_name}' iniciado")

        # 4. Verificar estado
        subprocess.run('powershell -Command "Get-Caches -Detail"', shell=True)

        # 5. Modificar archivos ServiceBus.NCache.config
        archivos = [
            os.path.join(ruta_frontend, "STE", "ConfigFiles", "ServiceBus.NCache.config"),
            os.path.join(ruta_middleware, "STE", "bin", "ServiceBus.NCache.config")
        ]
        for archivo in archivos:
            reemplazar_en_archivo(archivo, {
                "localhost": server_name,
                "9800": server_port,
                "myCache": cache_name
            })
            logs.append(f"[{datetime.now()}] ✔ Configurado: {archivo}")

        log_file = guardar_log(logs)
        return {
            "status": "success",
            "output": "\n".join(logs),
            "log_file": log_file
        }

    except Exception as e:
        logs.append(f"[{datetime.now()}] ❌ Error inesperado:\n{str(e)}")
        log_file = guardar_log(logs)
        return {
            "status": "error",
            "output": "\n".join(logs),
            "log_file": log_file
        }
