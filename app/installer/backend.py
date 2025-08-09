import os
import subprocess
from datetime import datetime


LOG_DIR = "logs"


def guardar_log(logs):
    """
    Guarda los logs en un archivo .log con fecha actual.
    """
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    fecha = datetime.now().strftime('%Y-%m-%d')
    log_file_path = os.path.join(LOG_DIR, f"backend_{fecha}.log")

    with open(log_file_path, "a", encoding="utf-8") as f:
        for linea in logs:
            f.write(f"{linea}\n")

    return log_file_path


def ejecutar_sql_script(sql_server, user, password, script_path, database='master'):
    command = f'sqlcmd -S {sql_server} -U {user} -P {password} -d {database} -i "{script_path}"'
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def reemplazar_en_archivo(ruta, reemplazos):
    with open(ruta, 'r', encoding='utf-8') as file:
        contenido = file.read()

    for original, nuevo in reemplazos.items():
        contenido = contenido.replace(original, nuevo)

    with open(ruta, 'w', encoding='utf-8') as file:
        file.write(contenido)


def run_backend_installation(form_data):
    try:
        sql_server = form_data.get('sql_server')
        db_name = form_data.get('db_name')
        user = form_data.get('user')
        password = form_data.get('password')
        target_path = form_data.get('target_path')

        logs = []
        scripts_dir = os.path.abspath(target_path)

        # Reemplazo en script 001
        script_001 = os.path.join(scripts_dir, "001_Data_Base.sql")
        reemplazar_en_archivo(script_001, {
            "[Target]": f"C:\\Program Files\\Microsoft SQL Server\\MSSQL15.SQLEXPRESS\\MSSQL\\DATA\\{db_name}"
        })
        logs.append(f"[{datetime.now()}] ✔ Reemplazado [Target] en 001_Data_Base.sql")

        # Ejecutar script 001
        code, out, err = ejecutar_sql_script(sql_server, user, password, script_001)
        logs.append(f"[{datetime.now()}] ▶ Script 001 output:\n{out or err}")
        if code != 0:
            raise Exception(f"❌ Error ejecutando 001_Data_Base.sql:\n{err}")

        # Ejecutar script 002
        script_002 = os.path.join(scripts_dir, "002_Data_Base_Users.sql")
        code, out, err = ejecutar_sql_script(sql_server, user, password, script_002, database=db_name)
        logs.append(f"[{datetime.now()}] ▶ Script 002 output:\n{out or err}")
        if code != 0:
            raise Exception(f"❌ Error ejecutando 002_Data_Base_Users.sql:\n{err}")

        # Ejecutar .bat si existe
        bat_path = os.path.join(scripts_dir, "ejecutar_restantes.bat")
        if os.path.exists(bat_path):
            reemplazar_en_archivo(bat_path, {"SERVIDORBBDD": sql_server})
            result = subprocess.run(f'"{bat_path}"', shell=True, capture_output=True, text=True)
            logs.append(f"[{datetime.now()}] ▶ Script .BAT output:\n{result.stdout or result.stderr}")
            if result.returncode != 0:
                raise Exception("❌ Error ejecutando el archivo .bat")
        else:
            logs.append(f"[{datetime.now()}] ⚠ Archivo .bat no encontrado.")

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
