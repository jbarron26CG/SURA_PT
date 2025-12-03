import streamlit as st
import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import gspread
from datetime import datetime
import re

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
#               VISTA CAPTURISTA
# =======================================================
def vista_liquidador():

    st.title("Panel Liquidador")

    # Selector de sección
    opcion = st.sidebar.radio(
        "Seleccione una sección:",
        ["Registrar siniestro", "Modificar siniestro"]
    )

    # =====================================================
    #                REGISTRAR SINIESTRO
    # =====================================================
    if opcion == "Registrar siniestro":
        # ===== CSS PARA PESTAÑAS PROFESIONALES =====
        st.markdown("""
        <style>
        .tabs-container {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }

        .tab-button {
            padding: 10px 15px;
            border-radius: 8px;
            background-color: #f0f2f6;
            border: 1px solid #d6d6d6;
            cursor: pointer;
            font-weight: 600;
            transition: 0.2s;
        }

        .tab-button:hover {
            background-color: #e2e6ea;
        }

        .tab-active {
            background-color: #4A90E2 !important;
            color: white !important;
            border-color: #4A90E2 !important;
        }
        </style>
        """, unsafe_allow_html=True)

        # ===== CONTROL DE PESTAÑAS =====
        if "tab_actual" not in st.session_state:
            st.session_state.tab_actual = "siniestro"

        def cambiar_tab(nombre):
            st.session_state.tab_actual = nombre

        st.markdown('<div class="tabs-container">', unsafe_allow_html=True)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button("Datos del siniestro",
                        key="tab_siniestro",
                        help="Registrar datos del siniestro"):
                cambiar_tab("siniestro")

        with col2:
            if st.button("Datos del asegurado",
                        key="tab_asegurado"):
                cambiar_tab("asegurado")

        with col3:
            if st.button("Datos del propietario",
                        key="tab_propietario"):
                cambiar_tab("propietario")

        with col4:
            if st.button("Datos del vehículo",
                        key="tab_vehiculo"):
                cambiar_tab("vehiculo")

        st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.tab_actual == "siniestro":
            st.markdown("### 🟥 Datos del siniestro")

            col1, col2 = st.columns(2)

            with col1:
                numero_siniestro = st.text_input("Número de siniestro")
                correlativo = st.text_input("Correlativo")
                fecha_siniestro = st.date_input("Fecha del siniestro")

            with col2:
                lugar_siniestro = st.text_input("Lugar del siniestro")
                medio_asignacion = st.selectbox(
                    "Medio de asignación",
                    ["Call center", "PP", "Otro"]
                )

        if st.session_state.tab_actual == "asegurado":
            st.markdown("### 🟦 Datos del asegurado")

            col1, col2 = st.columns(2)

            with col1:
                nombre_ase = st.text_input("Nombre")
                rut_ase = st.text_input("RUT")
                tipo_persona_ase = st.selectbox("Tipo de persona", ["Física", "Moral"])

            with col2:
                telefono_ase = st.text_input("Teléfono")
                correo_ase = st.text_input("Correo electrónico")
                direccion_ase = st.text_input("Dirección")
        if st.session_state.tab_actual == "propietario":
            st.markdown("### 🟩 Datos del propietario")

            col1, col2 = st.columns(2)

            with col1:
                nombre_prop = st.text_input("Nombre")
                rut_prop = st.text_input("RUT")
                tipo_persona_prop = st.selectbox("Tipo de persona", ["Física", "Moral"])

            with col2:
                telefono_prop = st.text_input("Teléfono")
                correo_prop = st.text_input("Correo electrónico")
                direccion_prop = st.text_input("Dirección")
        
        if st.session_state.tab_actual == "vehiculo":
            st.markdown("### 🟨 Datos del vehículo")

            col1, col2, col3 = st.columns(3)

            with col1:
                marca = st.text_input("Marca")
                submarca = st.text_input("Submarca")
                version = st.text_input("Versión")

            with col2:
                anio_modelo = st.number_input("Año / Modelo", 1980, 2030, 2023)
                numero_serie = st.text_input("Número de serie")
                motor = st.text_input("Motor")

            with col3:
                patente = st.text_input("Patente")
        
        if st.button("Guardar registro ✅"):
            # VALIDACIÓN SIMPLE
            if not numero_siniestro:
                st.error("Debes ingresar el número de siniestro.")
                st.stop()

            # Construir registro para Google Sheets
            registro = [
                numero_siniestro,
                correlativo,
                str(fecha_siniestro),
                lugar_siniestro,
                medio_asignacion,

                nombre_ase,
                rut_ase,
                tipo_persona_ase,
                telefono_ase,
                correo_ase,
                direccion_ase,

                nombre_prop,
                rut_prop,
                tipo_persona_prop,
                telefono_prop,
                correo_prop,
                direccion_prop,

                marca,
                submarca,
                version,
                anio_modelo,
                numero_serie,
                motor,
                patente,

                st.session_state["USUARIO"],   # ← Guardado automático desde login
                st.session_state["NOMBRE"],    # ← Si lo agregaste en login
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ]

            # Guardar en Google Sheets
            sheet_form.append_row(registro)

            st.success("Registro guardado correctamente 🎉")




    # =====================================================
    #                MODIFICAR SINIESTRO
    # =====================================================
    elif opcion == "Modificar siniestro":

        st.header("Modificar información de un siniestro")

        datos = sheet_form.get_all_records()
        df = pd.DataFrame(datos)

        siniestros = df["Siniestro"].unique()

        seleccion = st.selectbox("Seleccione el siniestro:", siniestros)

        registro = df[df["Siniestro"] == seleccion].iloc[0]

        st.write("Datos actuales:")
        st.write(registro)

        nuevo_estatus = st.selectbox(
            "Nuevo estatus:",
            [
                "ALTA FOLIO",
                "CONTACTO PENDIENTE DE CARGA",
                "PENDIENTE DE CONTACTO",
                "PENDIENTE VALIDACIÓN DIGITAL",
                "REPROCESO EN VALIDACIÓN DIGITAL",
                "PAGADO"
            ],
            index=[
                "ALTA FOLIO",
                "CONTACTO PENDIENTE DE CARGA",
                "PENDIENTE DE CONTACTO",
                "PENDIENTE VALIDACIÓN DIGITAL",
                "REPROCESO EN VALIDACIÓN DIGITAL",
                "PAGADO"
            ].index(registro["Estatus"])
        )

        if st.button("Actualizar"):

            fila = df.index[df["Siniestro"] == seleccion][0] + 2  # +2 por encabezado y 1-index

            sheet_form.update_cell(fila, 2, nuevo_estatus)

            st.success("Estatus actualizado correctamente")


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
