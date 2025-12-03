import streamlit as st
import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import gspread
from datetime import datetime
import re
from zoneinfo import ZoneInfo

# =======================================================
#             CONFIGURAR CREDENCIALES
# =======================================================
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# 🔥 CREDENCIALES DESDE STREAMLIT SECRETS
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scope
)

client = gspread.authorize(creds)
drive_service = build("drive", "v3", credentials=creds)

# =======================================================
#     FUNCIONES PARA GOOGLE DRIVE DENTRO DE SHARED DRIVE
# =======================================================

SHARED_DRIVE_ID = "0AMe71RDJTYcGUk9PVA"   # ← tu unidad compartida

def obtener_o_crear_carpeta(nombre_carpeta, drive_service):
    """Busca o crea carpeta en la unidad compartida."""

    query = (
        f"name = '{nombre_carpeta}' "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and '{SHARED_DRIVE_ID}' in parents "
        f"and trashed = false"
    )

    resultado = drive_service.files().list(
        q=query,
        spaces='drive',
        corpora='drive',
        driveId=SHARED_DRIVE_ID,
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        fields="files(id, name)"
    ).execute()

    folders = resultado.get("files", [])

    if folders:
        return folders[0]["id"]

    metadata = {
        "name": nombre_carpeta,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [SHARED_DRIVE_ID]
    }

    nueva = drive_service.files().create(
        body=metadata,
        fields="id",
        supportsAllDrives=True
    ).execute()

    return nueva["id"]


def subir_archivo_drive(nombre_archivo, contenido, mime_type, folder_id, drive_service):
    """Sube un archivo dentro de una carpeta en Shared Drive."""

    file_metadata = {
        "name": nombre_archivo,
        "parents": [folder_id]
    }

    media = MediaIoBaseUpload(io.BytesIO(contenido), mimetype=mime_type)

    archivo = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
        supportsAllDrives=True
    ).execute()

    return archivo["id"]

# =======================================================
#               ABRIR SPREADSHEETS
# =======================================================

SHEET_FORM_URL = "https://docs.google.com/spreadsheets/d/1N968vVRp3VfX8r1sRdUA8bdeMxx6Ldjj_a4_coah_BY/edit?gid=0#gid=0"
sheet_form = client.open_by_url(SHEET_FORM_URL).sheet1

SHEET_LOGIN_URL = "https://docs.google.com/spreadsheets/d/14ByPe5nivtsO1k-lTeJLOY1SPAtqsA9sEQnjArIk4Ik/edit?gid=0#gid=0"
sheet_users = client.open_by_url(SHEET_LOGIN_URL).worksheet("Login")


# =======================================================
#                 CARGAR USUARIOS
# =======================================================
def cargar_usuarios(sheet):
    datos = sheet.get_all_records()
    return pd.DataFrame(datos)

df_usuarios = cargar_usuarios(sheet_users)


# =======================================================
#                       LOGIN
# =======================================================
def login(df):

    st.title("Inicio de Sesión")

    user = st.text_input("USUARIO:")
    password = st.text_input("CONTRASEÑA:", type="password")

    if st.button("Ingresar"):
        registros = sheet_users.get_all_records()

        for fila in registros:
            if fila["USUARIO"] == user and fila["PASSWORD"] == password:
                st.session_state["auth"] = True
                st.session_state["USUARIO"] = fila["USUARIO"]
                st.session_state["LIQUIDADOR"] = fila["LIQUIDADOR"]
                st.session_state["ROL"] = fila["ROL"]
                st.success("Acceso exitoso.")
                st.rerun()

        st.error("Credenciales incorrectas")


# =======================================================
#               VISTA LIQUIDADOR
# =======================================================
def vista_liquidador():

    st.title("Panel Liquidador")

    opcion = st.sidebar.radio(
        "Seleccione una sección:",
        ["Registrar siniestro", "Modificar siniestro"]
    )

    # =====================================================================================
    #                                REGISTRAR SINIESTRO
    # =====================================================================================
    if opcion == "Registrar siniestro":

        st.header("Registro de nuevo siniestro")

        with st.form("form_siniestro"):

            tabs = st.tabs([
                "📁 Datos del siniestro",
                "👤 Datos del asegurado",
                "🏠 Datos del propietario",
                "🚗 Datos del vehículo"
            ])

            # ---------------------- DATOS SINIESTRO -------------------------
            with tabs[0]:
                st.subheader("Datos del siniestro")

                Siniestro = st.text_input("Número de siniestro", key="siniestro_num")
                Correlativo = st.text_input("Correlativo", key="siniestro_correl")
                FechaSiniestro = st.date_input("Fecha del siniestro", key="siniestro_fecha")
                Lugar = st.text_input("Lugar del siniestro", key="siniestro_lugar")
                Medio = st.selectbox(
                    "Medio de asignación",
                    ["Call center", "PP", "Otro"],
                    key="siniestro_medio"
                )

            # ---------------------- DATOS ASEGURADO -------------------------
            with tabs[1]:
                st.subheader("Datos del asegurado")

                Asegurado_Nombre = st.text_input("Nombre del asegurado", key="aseg_nombre")
                Asegurado_Rut = st.text_input("RUT del asegurado", key="aseg_rut")
                Asegurado_Tipo = st.selectbox(
                    "Tipo de persona (asegurado)",
                    ["Natural", "Jurídica"],
                    key="aseg_tipo"
                )
                Asegurado_Telefono = st.text_input("Teléfono", key="aseg_tel")
                Asegurado_Correo = st.text_input("Correo electrónico", key="aseg_correo")
                Asegurado_Direccion = st.text_input("Dirección", key="aseg_direccion")

            # ---------------------- DATOS PROPIETARIO -------------------------
            with tabs[2]:
                st.subheader("Datos del propietario")

                Propietario_Nombre = st.text_input("Nombre", key="prop_nombre")
                Propietario_Rut = st.text_input("RUT", key="prop_rut")
                Propietario_Tipo = st.selectbox(
                    "Tipo de persona (propietario)",
                    ["Natural", "Jurídica"],
                    key="prop_tipo"
                )
                Propietario_Telefono = st.text_input("Teléfono", key="prop_tel")
                Propietario_Correo = st.text_input("Correo electrónico", key="prop_correo")
                Propietario_Direccion = st.text_input("Dirección", key="prop_direccion")

            # ---------------------- DATOS VEHÍCULO -------------------------
            with tabs[3]:
                st.subheader("Datos del vehículo")

                Marca = st.text_input("Marca", key="veh_marca")
                Submarca = st.text_input("Submarca", key="veh_submarca")
                Version = st.text_input("Versión", key="veh_version")
                AñoModelo = st.number_input("Año/Modelo", min_value=1900, max_value=2050, key="veh_anio")
                Serie = st.text_input("Número de serie", key="veh_serie")
                Motor = st.text_input("Motor", key="veh_motor")
                Patente = st.text_input("Patente", key="veh_patente")

                archivos = st.file_uploader(
                    "Subir documentos",
                    type=["pdf", "jpg", "jpeg", "png", "xlsx", "xls", "docx"],
                    accept_multiple_files=True,
                    key="veh_archivos"
                )

            # >>>>>>>> AQUÍ VA EL SUBMIT BUTTON <<<<<<<<
                enviado = st.form_submit_button("Guardar")

        # ======================= VALIDACIONES =============================
            if enviado:
                errores = []

                if not Siniestro:
                    errores.append("El número de siniestro es obligatorio.")

                email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
                if Asegurado_Correo and not re.match(email_regex, Asegurado_Correo):
                    errores.append("El correo del asegurado no es válido.")

                if errores:
                    st.error("Revisa lo siguiente:\n- " + "\n- ".join(errores))
                    return

                # Usuario login desde session_state
                Usuario_Login = st.session_state["USUARIO"]
                Liquidador_Nombre = st.session_state["LIQUIDADOR"]
                FechaMovimiento = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Crear carpeta en drive
                carpeta_id = obtener_o_crear_carpeta(f"SINIESTRO_{Siniestro}", drive_service)
                carpeta_link = f"https://drive.google.com/drive/folders/{carpeta_id}"

                # Subir archivos
                links_archivos = []
                if archivos:
                    for archivo in archivos:
                        archivo_id = subir_archivo_drive(
                            archivo.name,
                            archivo.read(),
                            archivo.type,
                            carpeta_id,
                            drive_service
                        )
                        links_archivos.append(f"https://drive.google.com/file/d/{archivo_id}/view")

                # Guardar en Sheets
                sheet_form.append_row([
                    Siniestro,
                    Correlativo,
                    FechaSiniestro.strftime("%Y-%m-%d"),
                    Lugar,
                    Medio,
                    Marca,
                    Submarca,
                    Version,
                    AñoModelo,
                    Serie,
                    Motor,
                    Patente,
                    datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d %H:%M:%S"),
                    "ALTA SINIESTRO",
                    Asegurado_Nombre,
                    Asegurado_Rut,
                    Asegurado_Tipo,
                    Asegurado_Telefono,
                    Asegurado_Correo,
                    Asegurado_Direccion,
                    Propietario_Nombre,
                    Propietario_Rut,
                    Propietario_Tipo,
                    Propietario_Telefono,
                    Propietario_Correo,
                    Propietario_Direccion,
                    Liquidador_Nombre,
                    Usuario_Login,
                    carpeta_link,
                    ", ".join(links_archivos)
                ])

                st.success("✔ Siniestro registrado correctamente.")

# =======================================================
#                VISTA ADMINISTRADOR
# =======================================================
def vista_admin():
    st.title("Panel Administrador")

    datos = sheet_form.get_all_records()
    df = pd.DataFrame(datos)

    st.dataframe(df)
    st.write("Total de registros:", len(df))


# =======================================================
#                 CONTROL DE SESIÓN
# =======================================================
if "auth" not in st.session_state:
    st.session_state["auth"] = False

if not st.session_state["auth"]:
    login(df_usuarios)
    st.stop()

# =======================================================
#                 INTERFAZ PRINCIPAL
# =======================================================
st.sidebar.write(f"USUARIO: **{st.session_state['USUARIO']}**")
st.sidebar.write(f"ROL: **{st.session_state['ROL']}**")

if st.sidebar.button("Cerrar sesión ❌"):
    st.session_state.clear()
    st.rerun()

if st.session_state["ROL"] == "ADMINISTRADOR":
    vista_admin()
else:
    vista_liquidador()
