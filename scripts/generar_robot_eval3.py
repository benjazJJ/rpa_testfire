"""Genera rocketbot/RPA_TestFire_Eval3.json a partir del robot v5 (mismo formato de comandos).

Uso: py scripts/generar_robot_eval3.py rocketbot/RPA_TestFire_Login_v5.json rocketbot/RPA_TestFire_Eval3.json
"""
import copy
import json
import sys
import uuid

entrada, salida = sys.argv[1], sys.argv[2]
v5 = json.load(open(entrada, encoding="utf-8"))
p5 = v5["project"]


def recorrer(cmds):
    for c in cmds:
        yield c
        yield from recorrer(c.get("children", []))
        yield from recorrer(c.get("else", []))


# Plantillas: un comando real del v5 por cada tipo que se usa.
plantillas = {}
for c in recorrer(p5["commands"]):
    clave = (c["group"], c["father"], c.get("option", ""))
    if c["father"] == "evaluateIf" and "run_when" not in c:
        continue  # el If de nivel superior tiene otro juego de campos; usamos el interno
    plantillas.setdefault(clave, c)


def nuevo(group, father, option, command, **extra):
    base = copy.deepcopy(plantillas[(group, father, option)])
    base.update(command=command, id=str(uuid.uuid4()), time="0", execute=2, mode_live=False,
                message="", screenshot="", img="", children=[], **{"else": []})
    base.update(extra)
    return base


def log(texto, nivel="info"):
    return nuevo("system", "log_message", nivel, texto)


def set_var(var, valor):
    return nuevo("system", "setVar", "", valor, var=var)


def si(condicion, hijos, sino=(), descripcion=""):
    c = nuevo("logic", "evaluateIf", "", condicion, description=descripcion)
    c["children"], c["else"] = list(hijos), list(sino)
    return c


def ejecutar_bat(nombre, variable):
    c = copy.deepcopy(plantillas[("system", "startapp", "")])
    c.update(command=json.dumps({"path": "{ruta_repo}\\scripts\\" + nombre, "tipo": "0"}),
             id=str(uuid.uuid4()), time="0", execute=2, mode_live=False, getvar=variable, disabled=False)
    return c


def subproceso(titulo, bat, variable, extra_ok=(), descripcion=""):
    """If {continuar}: ejecuta el .bat y revisa RESULTADO=OK; si falla, corta la cadena."""
    revisar = si(
        f"'RESULTADO=OK' in r'''{{{variable}}}'''",
        [log(f"{titulo}: OK | {{{variable}}}"), *extra_ok],
        [log(f"{titulo}: FALLÓ, se detiene la cadena | {{{variable}}}", "error"), set_var("continuar", "False")],
    )
    return si("{continuar}", [log(f"Inicio {titulo}"), ejecutar_bat(bat, variable), revisar],
              descripcion=descripcion)


def pendiente(texto):
    return log("AGREGAR AQUÍ (Rocketbot > Email > SMTP - IMAP): " + texto, "error")


# ---- Subproceso 1 + extracción: se reutiliza el v5 cambiando rutas fijas por variables ----
c5 = copy.deepcopy(p5["commands"])
abrir, esperar, login = c5[0], c5[1], c5[2]
abrir["command"] = json.dumps({"tipo": "0", "url": "https://demo.testfire.net/", "profile": "{ruta_perfil_ff}"})
login["description"] = "Subproceso 1 · Login + extracción"
tabla = login["children"][9]
for c in recorrer([tabla]):
    if c["father"] == "savexlsx":
        c["command"] = json.dumps({"path": "{ruta_salida}\\consolidado.xlsx"})
    if c["father"] == "readxlsx":
        c["command"] = json.dumps({"file_path": "{ruta_salida}\\consolidado.xlsx", "identificator": "validacion"})
validacion = tabla["children"][13]
# La conciliación sale de aquí y pasa a ser su propio subproceso en la cadena.
validacion["children"] = [validacion["children"][0], set_var("extraccion_ok", "True")]

comandos = [
    log("=== RPA TestFire · Evaluación 3 · inicio === PC con repo en {ruta_repo} y salida en {ruta_salida}"),
    set_var("extraccion_ok", "False"),
    abrir, esperar, login,
    set_var("continuar", "{extraccion_ok}"),
    subproceso("Subproceso 2b · Conciliación contra el maestro SQLite", "conciliar_rocketbot.bat",
               "res_conciliacion", descripcion="Subproceso 2b · Conciliación"),
    subproceso("Subproceso 2c · API dólar mindicador.cl -> reporte final", "referencia_externa.bat",
               "res_api", descripcion="Subproceso 2c · API pública"),
    subproceso("Subproceso 3 · Abrir el reporte en Excel (escritorio)", "abrir_excel.bat",
               "res_excel", descripcion="Subproceso 3 · Excel"),
    subproceso("Subproceso 4a · Dispatcher: encolar correos", "dispatcher.bat",
               "res_dispatcher", descripcion="Subproceso 4a · Dispatcher"),
    subproceso("Subproceso 4b · Performer: enviar la cola por SMTP", "performer.bat",
               "res_performer", descripcion="Subproceso 4b · Performer"),
    subproceso(
        "Subproceso 4c · Correo al supervisor", "resumen_supervisor.bat", "res_resumen",
        extra_ok=[
            set_var("mensaje_supervisor", "r'''{res_resumen}'''.split('RESULTADO=')[0].strip()"),
            pendiente("comando Configurar servidor con los datos de la diapositiva "
                      "(mail.mantistcy.cl, SMTP 465 SSL, IMAP 993 SSL). Luego borrar este mensaje."),
            pendiente("comando Enviar email SMTP | Para: {correo_supervisor} | "
                      "Asunto: [RPA TestFire] Resumen de ejecución | Mensaje: {mensaje_supervisor} | "
                      "Archivo adjunto: {ruta_salida}\\reporte_final_ultimo.xlsx. Luego borrar este mensaje."),
        ],
        descripcion="Subproceso 4c · Correo supervisor"),
    si("{continuar}", [
        pendiente("comando Listar email nuevos IMAP (para mostrar las respuestas en la demo). "
                  "Luego borrar este mensaje."),
    ], descripcion="Subproceso 4d · Recepción (Rocketbot)"),
    subproceso("Subproceso 4d · Clasificar respuestas por IMAP", "clasificar.bat",
               "res_clasificar", descripcion="Subproceso 4d · Clasificación"),
    si("{continuar}",
       [log("=== RPA TestFire · Evaluación 3 · fin OK === Revisar la Auditoría RPA y logs\\rpa_AAAAMMDD.log")],
       [log("=== RPA TestFire · Evaluación 3 · fin CON ERRORES === Revisar el paso marcado arriba y "
            "{ruta_salida}\\*_errores.log", "error")],
       descripcion="Subproceso 5 · Cierre"),
]


def numerar(cmds, prefijo=""):
    for i, c in enumerate(cmds):
        c["index"] = i
        c["line"] = f"{prefijo}{i + 1}"
        numerar(c.get("children", []), c["line"] + ".")
        numerar(c.get("else", []), c["line"] + ".")


numerar(comandos)

# ---- Variables ----
quitar = {"http_get", "http_post", "http_put", "http_patch", "http_delete", "resumen_sql"}
variables = [v for v in p5["vars"] if v["name"] not in quitar]
plantilla_var = p5["vars"][3]
nuevas = {
    "ruta_repo": "C:\\Workspace\\rpa_testfire\\rpa_testfire",
    "ruta_salida": "C:\\Users\\bpalm\\Rocketbot_Salida",
    "ruta_perfil_ff": "C:/Users/bpalm/Rocketbot_FF_Profile",
    "correo_supervisor": "be.palmap@duocuc.cl",
    "continuar": "False", "extraccion_ok": "False",
    "res_conciliacion": "", "res_api": "", "res_excel": "", "res_dispatcher": "",
    "res_performer": "", "res_resumen": "", "mensaje_supervisor": "", "res_clasificar": "",
}
for nombre, dato in nuevas.items():
    v = copy.deepcopy(plantilla_var)
    v.update(name=nombre, data=dato, id=str(uuid.uuid4()))
    variables.append(v)
for i, v in enumerate(variables):
    v["index"] = i

proyecto = copy.deepcopy(p5)
proyecto["profile"]["name"] = "RPA_TestFire_Eval3"
proyecto["profile"]["description"] = ("Evaluación 3 ATY1102: login TestFire, extracción, conciliación, API dólar, "
                                      "Excel, dispatcher/performer de correos, supervisor y clasificación IMAP")
proyecto["commands"] = comandos
proyecto["vars"] = variables
for idioma in proyecto["expose"]["title"]:
    proyecto["expose"]["title"][idioma] = "RPA_TestFire_Eval3 expose"

json.dump({**v5, "project": proyecto}, open(salida, "w", encoding="utf-8"), ensure_ascii=False)
print("comandos de nivel superior:", len(comandos), "| total:", sum(1 for _ in recorrer(comandos)),
      "| variables:", len(variables))
