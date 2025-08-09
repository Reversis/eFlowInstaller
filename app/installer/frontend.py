import os
import subprocess
from datetime import datetime

LOG_DIR = "logs"


def guardar_log(logs):
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    fecha = datetime.now().strftime('%Y-%m-%d')
    log_file_path = os.path.join(LOG_DIR, f"frontend_{fecha}.log")
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


def run_frontend_installation(form_data):
    try:
        ruta_instalacion = form_data.get("target_path")  # Ej: C:\Sidesys\FrontEnd
        middleware_ip = form_data.get("middleware_ip")
        nodo_ip = form_data.get("nodo_ip")
        puerto_app = form_data.get("puerto_app", "10500")
        puerto_nodo = form_data.get("puerto_nodo", "10501")
        site_name = form_data.get("site_name", "STE")
        app_pool = f"{site_name}_Pool"

        logs = []

        # 1. Configurar Client.config
        config_path = os.path.join(ruta_instalacion, "STE", "ConfigFiles", "Client.config")
        reemplazar_en_archivo(config_path, {
            "127.0.0.1": middleware_ip,
            "localhost": nodo_ip,
            "10500": puerto_app,
            "10501": puerto_nodo
        })
        logs.append(f"[{datetime.now()}] ✔ Client.config actualizado.")

        # 2. Crear Application Pool
        subprocess.run(f'appcmd add apppool /name:{app_pool}', shell=True)
        subprocess.run(f'appcmd set apppool /apppool.name:{app_pool} /managedRuntimeVersion:v4.0 /managedPipelineMode:Integrated', shell=True)
        logs.append(f"[{datetime.now()}] ✔ AppPool '{app_pool}' creado.")

        # 3. Crear sitio web en IIS
        site_path = os.path.join(ruta_instalacion, "STE")
        subprocess.run(f'appcmd add site /name:{site_name} /bindings:https/*:443: /physicalPath:"{site_path}"', shell=True)
        subprocess.run(f'appcmd set app "{site_name}/" /applicationPool:{app_pool}', shell=True)
        logs.append(f"[{datetime.now()}] ✔ Sitio IIS '{site_name}' creado y apuntando a {site_path}.")

        # 4. Establecer documento predeterminado
        subprocess.run(f'appcmd set config "{site_name}" /section:defaultDocument /+files.[value=\'default.aspx\']', shell=True)
        logs.append(f"[{datetime.now()}] ✔ Documento predeterminado configurado: default.aspx")

        # 5. Activar compresión estática
        subprocess.run(f'appcmd set config "{site_name}" /section:urlCompression /doStaticCompression:true /commit:apphost', shell=True)
        logs.append(f"[{datetime.now()}] ✔ Compresión estática activada.")

        # 6. Headers de seguridad (ejemplo X-Frame-Options)
        subprocess.run(f'appcmd set config "{site_name}" /section:httpProtocol /+customHeaders.[name=\'X-Frame-Options\',value=\'sameorigin\']', shell=True)
        subprocess.run(f'appcmd set config "{site_name}" /section:httpProtocol /+customHeaders.[name=\'X-Content-Type-Options\',value=\'nosniff\']', shell=True)
        logs.append(f"[{datetime.now()}] ✔ Headers de seguridad añadidos.")

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
