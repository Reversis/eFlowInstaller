import os
import subprocess
from datetime import datetime

LOG_DIR = "logs"


def guardar_log(logs):
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    fecha = datetime.now().strftime('%Y-%m-%d')
    log_file_path = os.path.join(LOG_DIR, f"middleware_{fecha}.log")
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


def run_middleware_installation(form_data):
    try:
        ruta_middleware = form_data.get("target_path")  # C:\Sidesys\Middleware
        puerto_app = form_data.get("puerto_app", "10500")
        puerto_nodo = form_data.get("puerto_nodo", "10501")
        sql_server = form_data.get("sql_server")
        db_user = form_data.get("user")
        db_pass = form_data.get("password")

        logs = []

        # 1. Modificar archivos config
        service_config = os.path.join(ruta_middleware, "STE", "bin", "ServiceModelConfig", "Services.config")
        client_config = os.path.join(ruta_middleware, "STE", "bin", "ServiceModelConfig", "Client.config")

        reemplazar_en_archivo(service_config, {"10500": puerto_app})
        reemplazar_en_archivo(client_config, {"10501": puerto_nodo})
        logs.append(f"[{datetime.now()}] ✔ Puertos actualizados en archivos .config")

        # 2. Modificar archivos UDL
        udl_files = ["SOF.udl", "STE.udl", "STE_HD.udl"]
        for udl in udl_files:
            path = os.path.join(ruta_middleware, "STE", "ConfigFiles", udl)
            reemplazar_en_archivo(path, {
                "Provider=SQLOLEDB.1;": "",  # Se elimina esa parte
                "Data Source=(local)": f"Data Source={sql_server}",
                "User Id=usuario": f"User Id={db_user}",
                "Password=clave": f"Password={db_pass}"
            })
            logs.append(f"[{datetime.now()}] ✔ UDL modificado: {udl}")

        # 3. Instalar STEService
        service_exe = os.path.join(ruta_middleware, "STE", "bin", "Sidesys.Services.ApplicationService.exe")
        installutil = r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\installutil.exe"

        command = f'"{installutil}" -i "{service_exe}"'
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        logs.append(f"[{datetime.now()}] ▶ Registro de servicio STEService:\n{result.stdout or result.stderr}")
        if result.returncode != 0:
            raise Exception("❌ Error registrando el servicio STEService")

        # 4. Configurar inicio automático
        subprocess.run('sc config STEService start= auto', shell=True)
        logs.append(f"[{datetime.now()}] ✔ Servicio configurado como automático")

        # 5. Iniciar servicio
        subprocess.run('sc start STEService', shell=True)
        logs.append(f"[{datetime.now()}] ▶ Servicio STEService iniciado")

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
