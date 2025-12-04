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

def vista_modificar_siniestro():

    st.title("🔧 Modificar Siniestro")

    # ================================
    # CARGAR BASE
    # ================================
    datos = sheet_form.get_all_records()
    df = pd.DataFrame(datos)

    if df.empty:
        st.warning("No hay siniestros registrados.")
        return

    # ================================
    # BUSCADOR
    # ================================
    st.subheader("🔍 Buscar siniestro")
    busqueda = st.text_input("Buscar por número de siniestro, asegurado, patente o propietario")

    df_filtrado = df[
        df.apply(lambda row:
                 busqueda.lower() in str(row["# DE SINIESTRO"]).lower() or
                 busqueda.lower() in str(row["NOMBRE ASEGURADO"]).lower() or
                 busqueda.lower() in str(row["PATENTE"]).lower() or
                 busqueda.lower() in str(row["NOMBRE PROPIETARIO"]).lower()
                 , axis=1)
        ] if busqueda else df

    lista_siniestros = sorted(df_filtrado["# DE SINIESTRO"].unique())

    selected = st.selectbox("Selecciona el siniestro", lista_siniestros)

    if not selected:
        return

    registro = df[df["# DE SINIESTRO"] == selected].iloc[0]

    st.write("---")

    # ================================
    # TABS
    # ================================
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📝 Datos del Siniestro",
        "👤 Datos del Asegurado",
        "🏠 Datos del Propietario",
        "🚗 Datos del Vehículo",
        "📌 Estatus"
    ])

    # -------- TAB 1 --------
    with tab1:
        correlativo = st.text_input("Correlativo", registro["CORRELATIVO"])
        fecha_siniestro = st.date_input("Fecha de siniestro")
        lugar_siniestro = st.text_input("Lugar del siniestro", registro["LUGAR SINIESTRO"])
        medio_asignacion = st.selectbox(
            "Medio de asignación",
            ["Call center", "PP", "Otro"],
            index=["Call center", "PP", "Otro"].index(registro["MEDIO ASIGNACIÓN"]) 
            if registro["MEDIO ASIGNACIÓN"] in ["Call center", "PP", "Otro"] else 0
        )

    # -------- TAB 2 --------
    with tab2:
        aseg_nombre = st.text_input("Nombre asegurado", registro["NOMBRE ASEGURADO"])
        aseg_rut = st.text_input("RUT asegurado", registro["RUT ASEGURADO"])
        aseg_persona = st.selectbox(
            "Tipo de persona",
            ["Natural", "Jurídica"],
            index=["Natural", "Jurídica"].index(registro["TIPO DE PERSONA ASEGURADO"])
            if registro["TIPO DE PERSONA ASEGURADO"] in ["Natural", "Jurídica"] else 0
        )
        aseg_tel = st.text_input("Teléfono", registro["TEL. ASEGURADO"])
        aseg_mail = st.text_input("Correo", registro["CORREO ASEGURADO"])
        aseg_dir = st.text_input("Dirección", registro["DIRECCIÓN ASEGURADO"])

    # -------- TAB 3 --------
    with tab3:
        prop_nombre = st.text_input("Nombre propietario", registro["NOMBRE PROPIETARIO"])
        prop_rut = st.text_input("RUT propietario", registro["RUT PROPIETARIO"])
        prop_tipo = st.selectbox(
            "Tipo de persona",
            ["Natural", "Jurídica"],
            index=["Natural", "Jurídica"].index(registro["TIPO DE PERSONA PROPIETARIO"])
            if registro["TIPO DE PERSONA PROPIETARIO"] in ["Natural", "Jurídica"] else 0
        )
        prop_tel = st.text_input("Teléfono", registro["TEL. PROPIETARIO"])
        prop_mail = st.text_input("Correo", registro["CORREO PROPIETARIO"])
        prop_dir = st.text_input("Dirección", registro["DIRECCIÓN PROPIETARIO"])

    # -------- TAB 4 --------
    with tab4:
        marca = st.text_input("Marca", registro["MARCA"])
        submarca = st.text_input("Submarca", registro["SUBMARCA"])
        version = st.text_input("Versión", registro["VERSIÓN"])
        anio = st.text_input("Año/Modelo", registro["AÑO/MODELO"])
        serie = st.text_input("Número de serie", registro["NO. SERIE"])
        motor = st.text_input("Motor", registro["MOTOR"])
        patente = st.text_input("Patente", registro["PATENTE"])

    # -------- TAB 5: ESTATUS --------
    with tab5:
        st.subheader("📌 Cambiar estatus del siniestro")

        nuevo_estatus = st.selectbox(
            "Nuevo estatus",
            ["ASIGNADO", "EN PROCESO", "FINALIZADO", "PENDIENTE", "CANCELADO"]
        )

        if st.button("Registrar estatus"):
            from datetime import datetime
            from zoneinfo import ZoneInfo

            timestamp = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d %H:%M:%S")

            sheet_form.append_row([
                selected,   # 1
                "", "", "", "",   # 2-5
                "", "", "", "", "", "", "",  # 6-12
                timestamp,        # 13
                nuevo_estatus,    # 14
                "", "", "", "", "", "",      # 15-20
                "", "", "", "", "", "",      # 21-26
                st.session_state["nombre_usuario"],   # 27
                st.session_state["correo_usuario"],   # 28
                ""  # 29
            ])

            st.success("Estatus registrado correctamente")

    st.write("---")

    # ================================
    # BOTÓN FINAL PARA GUARDAR CAMBIOS
    # ================================
    if st.button("💾 Guardar cambios en los datos"):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        todas_las_filas = df[df["# DE SINIESTRO"] == selected].index

        updated_row = [
            selected,                     # 1
            correlativo,                  # 2
            str(fecha_siniestro),         # 3
            lugar_siniestro,              # 4
            medio_asignacion,             # 5
            marca,                        # 6
            submarca,                     # 7
            version,                      # 8
            anio,                         # 9
            serie,                        # 10
            motor,                        # 11
            patente,                      # 12
            "",                           # 13
            "",                           # 14
            aseg_nombre,                  # 15
            aseg_rut,                     # 16
            aseg_persona,                 # 17
            aseg_tel,                     # 18
            aseg_mail,                    # 19
            aseg_dir,                     # 20
            prop_nombre,                  # 21
            prop_rut,                     # 22
            prop_tipo,                    # 23
            prop_tel,                     # 24
            prop_mail,                    # 25
            prop_dir,                     # 26
            st.session_state["nombre_usuario"],   # 27
            st.session_state["correo_usuario"],   # 28
            ""                             # 29
        ]

        for fila in todas_las_filas:
            sheet_form.update(f"A{fila+2}:AC{fila+2}", [updated_row])

        st.success("Cambios guardados correctamente en todas las filas del siniestro.")


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
    if opcion == "Modificar siniestro":
        vista_modificar_siniestro()
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
