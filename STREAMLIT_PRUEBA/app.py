import streamlit as st
import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import gspread
from datetime import datetime
import re

# ================================
#   FUNCIONES PARA GOOGLE DRIVE
# ================================
def obtener_o_crear_carpeta(nombre_carpeta, parent_id, drive_service):

    query = (
        f"name = '{nombre_carpeta}' "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and '{parent_id}' in parents"
    )

    resultado = drive_service.files().list(
        q=query, fields="files(id, name)"
    ).execute()

    folders = resultado.get("files", [])

    if folders:
        return folders[0]["id"]

    metadata = {
        "name": nombre_carpeta,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }

    nueva = drive_service.files().create(
        body=metadata, fields="id"
    ).execute()

    return nueva["id"]


def subir_archivo_drive(nombre_archivo, contenido, mime_type, folder_id, drive_service):

    file_metadata = {
        "name": nombre_archivo,
        "parents": [folder_id]
    }

    media = MediaIoBaseUpload(io.BytesIO(contenido), mimetype=mime_type)

    archivo = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()

    return archivo["id"]


# ================================
#     CONFIGURAR CREDENCIALES
# ================================
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# 🔥 AHORA LAS CREDENCIALES SE LEEN DE STREAMLIT SECRETS
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scope
)

client = gspread.authorize(creds)
drive_service = build("drive", "v3", credentials=creds)


# ================================
#     ABRIR SPREADSHEETS
# ================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/1N968vVRp3VfX8r1sRdUA8bdeMxx6Ldjj_a4_coah_BY/edit?gid=0#gid=0"
sheet_form = client.open_by_url(SHEET_URL).sheet1

SHEET_LOGIN = "https://docs.google.com/spreadsheets/d/14ByPe5nivtsO1k-lTeJLOY1SPAtqsA9sEQnjArIk4Ik/edit?gid=0#gid=0"
sheet_users = client.open_by_url(SHEET_LOGIN).worksheet("Login")


# ================================
#      CARGAR USUARIOS
# ================================
def cargar_usuarios(sheet):
    datos = sheet.get_all_records()
    return pd.DataFrame(datos)

df_usuarios = cargar_usuarios(sheet_users)


# ================================
#       FORMULARIO LOGIN
# ================================
def login(df):

    st.title("Inicio de Sesión")

    usuario = st.text_input("USUARIO:")
    password = st.text_input("CONTRASEÑA:", type="password")

    if st.button("Ingresar"):
        fila = df[
            (df["USUARIO"] == usuario) &
            (df["PASSWORD"] == password)
        ]

        if len(fila) == 1:
            st.session_state["auth"] = True
            st.session_state["USUARIO"] = usuario
            st.session_state["ROL"] = fila.iloc[0]["ROL"]

            st.success("Acceso concedido")
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos")


# ================================
#       VISTA: FORMULARIO
# ================================
def vista_capturista():

    st.title("Registro nuevo siniestro")

    with st.form("Formulario Alta"):

        Siniestro = st.text_input("NO. DE SINIESTRO")
        Estatus = st.selectbox(
            "ESTATUS",
            [
                "ALTA FOLIO",
                "CONTACTO PENDIENTE DE CARGA",
                "PENDIENTE DE CONTACTO",
                "PENDIENTE VALIDACIÓN DIGITAL",
                "REPROCESO EN VALIDACIÓN DIGITAL",
                "PAGADO"
            ]
        )
        Correo = st.text_input("CORREO ELECTRÓNICO")
        Usuario = st.text_input("USUARIO (interno)")
        Comentario = st.text_area("Comentario")

        archivos = st.file_uploader(
            "Subir documentos",
            type=["pdf", "jpg", "jpeg", "png", "xlsx", "xls", "docx"],
            accept_multiple_files=True
        )

        enviado = st.form_submit_button("Guardar")

    # ================================
    #        VALIDACIONES
    # ================================
    errores = []

    if not Siniestro:
        errores.append("El número de siniestro es obligatorio.")
    if not Usuario:
        errores.append("El usuario es obligatorio.")

    email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if Correo and not re.match(email_regex, Correo):
        errores.append("El correo no tiene un formato válido.")

    # ================================
    #          GUARDAR DATOS
    # ================================
    if enviado:

        if errores:
            st.error("Revisa:\n\n- " + "\n- ".join(errores))

        else:
            # --- 1. Crear carpeta del siniestro ---
            root_folder_id = "1eYIU7fW_x2D4HU8GrsYzdDS5Bigf3T_2"
            nombre_carpeta = f"SINIESTRO_{Siniestro}"

            carpeta_id = obtener_o_crear_carpeta(
                nombre_carpeta, root_folder_id, drive_service
            )

            carpeta_link = f"https://drive.google.com/drive/folders/{carpeta_id}"

            # --- 2. Subir archivos ---
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
                    links_archivos.append(
                        f"https://drive.google.com/file/d/{archivo_id}/view"
                    )

            links_texto = ", ".join(links_archivos)

            # --- 3. Guardar en Google Sheet ---
            sheet_form.append_row([
                Siniestro,
                Estatus,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                Usuario,
                Comentario,
                Correo,
                carpeta_link,
                links_texto
            ])

            st.success("Datos guardados correctamente")


    # ================================
    #    MOSTRAR DATOS EXISTENTES
    # ================================
    st.subheader("Datos actuales en la hoja")

    datos = sheet_form.get_all_records()
    df = pd.DataFrame(datos)

    st.dataframe(df)


# ================================
#       VISTA: ADMIN
# ================================
def vista_admin():
    st.title("Panel Administrador")

    datos = sheet_form.get_all_records()
    df = pd.DataFrame(datos)

    st.dataframe(df)
    st.write("Total de registros:", len(df))


# ================================
#       CONTROL DE SESIÓN
# ================================
if "auth" not in st.session_state:
    st.session_state["auth"] = False

if not st.session_state["auth"]:
    login(df_usuarios)
    st.stop()


# ================================
#         INTERFAZ PRINCIPAL
# ================================
st.sidebar.write(f"USUARIO: **{st.session_state['USUARIO']}**")
st.sidebar.write(f"ROL: **{st.session_state['ROL']}**")

if st.sidebar.button("Cerrar sesión ❌"):
    st.session_state.clear()
    st.rerun()

if st.session_state["ROL"] == "ADMINISTRADOR":
    vista_admin()
else:
    vista_capturista()
