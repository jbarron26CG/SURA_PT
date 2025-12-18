import streamlit as st
import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
import io
import gspread
#import datetime
from datetime import datetime
import re
from zoneinfo import ZoneInfo
import yagmail
import time

def safe_google_call(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)

    except (gspread.exceptions.APIError, HttpError) as e:

        # Detectar error por saturación / limite de uso
        if "quota" in str(e).lower() or "rate limit" in str(e).lower():
            st.warning("⚠️ Saturación temporal del servicio. Por favor intenta nuevamente en unos segundos.")
        else:
            st.error("⚠️ Ocurrió un error inesperado al comunicarse con Google Sheets.")

        # Puedes registrar el error si quieres:
        # st.write(str(e))

        return None

def cargar_dataframe_rate_limit(sheet_form, cooldown=15):
    """
    Carga el DataFrame solo si han pasado X segundos desde la última actualización.
    cooldown: segundos mínimos entre llamadas reales a Google Sheets.
    """
    now = time.time()

    # Si NO existe historial → cargar por primera vez
    if "last_load_time" not in st.session_state:
        st.session_state["last_load_time"] = 0

    # Verificar rate limit
    if now - st.session_state["last_load_time"] < cooldown:
        # Usar caché existente
        return st.session_state.get("df_form", pd.DataFrame())

    # Si ya pasó el cooldown → cargar de Sheets
    data = sheet_form.get_all_values()
    if not data:
        df = pd.DataFrame()
    else:
        df = pd.DataFrame(data[1:], columns=data[0])

    # Guardar en caché
    st.session_state["df_form"] = df
    st.session_state["last_load_time"] = now

    return df



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
#                 CARGAR DATOS
# =======================================================

#@st.cache_data(ttl=20)
def obtener_dataframe(sheet_form):
    data = sheet_form.get_all_records()
    df = pd.DataFrame(data)
    return df

# =======================================================
#               ABRIR SPREADSHEETS
# =======================================================

SHEET_FORM_URL = "https://docs.google.com/spreadsheets/d/1N968vVRp3VfX8r1sRdUA8bdeMxx6Ldjj_a4_coah_BY/edit?gid=0#gid=0"
sheet_form = client.open_by_url(SHEET_FORM_URL).sheet1

SHEET_LOGIN_URL = "https://docs.google.com/spreadsheets/d/14ByPe5nivtsO1k-lTeJLOY1SPAtqsA9sEQnjArIk4Ik/edit?gid=0#gid=0"
sheet_users = client.open_by_url(SHEET_LOGIN_URL).worksheet("Login")

if "df_form" not in st.session_state:
    st.session_state["df_form"] = obtener_dataframe(sheet_form)

if "form_dirty" not in st.session_state:
    st.session_state["form_dirty"] = False

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

    if st.button("Ingresar",use_container_width=True):
        registros = sheet_users.get_all_records()
        #registros = df_usuarios
        for fila in registros:
            if fila["USUARIO"] == user and fila["PASSWORD"] == password:
                st.session_state["auth"] = True
                st.session_state["USUARIO"] = fila["USUARIO"]
                st.session_state["LIQUIDADOR"] = fila["LIQUIDADOR"]
                st.session_state["ROL"] = fila["ROL"]
                st.success("Acceso exitoso.")
                st.rerun()

        st.error("Credenciales incorrectas")


def guardar_dataframe(sheet, df):
    sheet.clear()
    sheet.update([df.columns.tolist()] + df.values.tolist())

def agregar_fila(sheet, fila_dict):
    # Convertimos el diccionario a lista en el orden correcto de columnas
    columnas = sheet.row_values(1)
    if not columnas:
        columnas = list(fila_dict.keys())
    fila = [fila_dict.get(col, "") for col in columnas]

    sheet.append_row(fila)


from datetime import datetime

def reset_form_registro():
    """Reinicia los valores del formulario de registro de siniestro en st.session_state."""
    
    # Define los valores por defecto exactos que usas en el bloque de inicialización
    default_values = {
        "siniestro_num": "",
        "siniestro_correl": "",
        "siniestro_fecha": datetime.today().date(),
        "siniestro_lugar": "",
        "siniestro_medio": "Call center",
        "aseg_nombre": "",
        "aseg_rut": "",
        "aseg_tipo": "",
        "aseg_tel": "",
        "aseg_correo": "",
        "aseg_direccion": "",
        "prop_nombre": "",
        "prop_rut": "",
        "prop_tipo": "",
        "prop_tel": "",
        "prop_correo": "",
        "prop_direccion": "",
        "veh_marca": "",
        "veh_submarca": "",
        "veh_version": "",
        "veh_anio": 1900,
        "veh_serie": "",
        "veh_motor": "",
        "veh_patente": "" 
    }
    
    # Itera sobre los valores por defecto y actualiza st.session_state
    # Solo actualiza si la clave está actualmente en st.session_state (para seguridad)
    for key, default_value in default_values.items():
        if key in st.session_state:
            st.session_state[key] = default_value
    if "veh_archivos" in st.session_state:
        del st.session_state["veh_archivos"]

def limpiar_y_recargar():
    reset_form_registro()
    #st.rerun()

def panel_seguimiento_2(df_sel, df, siniestro_id):

    st.subheader("📌 Agregar Estatus (Seguimiento)")
    if "estatus" not in st.session_state:
        st.session_state["estatus"] = "Seleccionar estatus"

    if "comentario" not in st.session_state:
        st.session_state["comentario"] = ""
    
    if "upload_counter" not in st.session_state:
        st.session_state["upload_counter"] = 0

    #nuevo_estatus = st.text_input("Nuevo estatus del siniestro")
    nuevo_estatus = st.selectbox("ESTATUS",["Seleccionar estatus","ASIGNADO","CLIENTE CONTACTADO","CARGA DOCUMENTAL RECIBIDA",
                                            "DESVIADO A FRAUDES","DOCUMENTACIÓN COMPLETA","EN ESPERA DE PRIMAS, PÓLIZA Y/O SALDO INSOLUTO",
                                            "PROPUESTA ECONÓMICA ENVIADA","PROPUESTA ECONÓMICA ACEPTADA","DERIVADO A CERO KM",
                                            "DERIVADO A REPOSICIÓN","EN ESPERA DE PRIMERA FIRMA","EN ESPERA DE SEGUNDA FIRMA (ROBO)",
                                            "EN ESPERA DE LEGALIZACIÓN","DOCUMENTACIÓN LEGALIZADA","SOLICITUD DE PAGO GENERADA","PAGO LIBERADO"],
                                            key="estatus")
    comentario = st.text_area("COMENTARIOS", height=120,key="comentario")

    st.write("Subir archivos para agregar al expediente del siniestro:")

    uploaded_files = st.file_uploader(
        "Selecciona los archivos",
        type=None,
        accept_multiple_files=True,
        key=f"veh_archivos_{st.session_state['upload_counter']}"
    )

    links_archivos = []

    if st.button("Agregar estatus",icon="💾",use_container_width=True):

        if nuevo_estatus == "Seleccionar estatus":
            st.warning("Debes ingresar un estatus.")
            return

        ref = df_sel.iloc[-1].copy()
        
        ahora = datetime.now(ZoneInfo("America/Mexico_City"))
        ref["FECHA ESTATUS BITÁCORA"] = ahora.strftime("%Y-%m-%d %H:%M:%S")

        ref["ESTATUS"] = nuevo_estatus
        ref["COMENTARIO"] = comentario
        #["LIQUIDADOR"] = st.session_state["LIQUIDADOR"]
        ref["CORREO LIQUIDADOR"] = st.session_state["USUARIO"]

        #df = df.append(ref, ignore_index=True)
        fila_dict = ref.to_dict()

        # Agregar solo una fila a Google Sheets
        agregar_fila(sheet_form, fila_dict)
        #df = pd.concat([df, pd.DataFrame([ref])], ignore_index=True)
        #guardar_dataframe(sheet_form, df)

        if uploaded_files:
        # Obtener o crear carpeta del siniestro
            nombre_carpeta = f"SINIESTRO_{siniestro_id}"
            carpeta_id = obtener_o_crear_carpeta(nombre_carpeta, drive_service)

            for archivo in uploaded_files:
                # Subir al drive con tu misma función existente
                archivo_id = subir_archivo_drive(
                    archivo.name,
                    archivo.read(),
                    archivo.type,
                    carpeta_id,
                    drive_service
                )

                link = f"https://drive.google.com/file/d/{archivo_id}/view"
                links_archivos.append(link)

        st.session_state["estatus"] = "Seleccionar estatus"
        st.session_state["comentario"] = ""
        st.session_state["upload_counter"] += 1
        
        st.session_state["last_load_time"] = 0
        st.success("Estatus agregado correctamente.")
        st.rerun()
def panel_seguimiento(df_sel, df, siniestro_id):

    st.subheader("📌 Agregar Estatus (Seguimiento)")

    with st.form("form_seguimiento", clear_on_submit=True):

        nuevo_estatus = st.selectbox(
            "ESTATUS",
            [
                "Seleccionar estatus",
                "ASIGNADO","CLIENTE CONTACTADO","CARGA DOCUMENTAL RECIBIDA",
                "DESVIADO A FRAUDES","DOCUMENTACIÓN COMPLETA",
                "EN ESPERA DE PRIMAS, PÓLIZA Y/O SALDO INSOLUTO",
                "PROPUESTA ECONÓMICA ENVIADA","PROPUESTA ECONÓMICA ACEPTADA",
                "DERIVADO A CERO KM","DERIVADO A REPOSICIÓN",
                "EN ESPERA DE PRIMERA FIRMA",
                "EN ESPERA DE SEGUNDA FIRMA (ROBO)",
                "EN ESPERA DE LEGALIZACIÓN","DOCUMENTACIÓN LEGALIZADA",
                "SOLICITUD DE PAGO GENERADA","PAGO LIBERADO"
            ]
        )

        comentario = st.text_area("COMENTARIOS", height=120)

        uploaded_files = st.file_uploader(
            "Selecciona los archivos",
            accept_multiple_files=True
        )

        enviado = st.form_submit_button("Agregar estatus",icon="💾",use_container_width=True)

    if enviado:

        if nuevo_estatus == "Seleccionar estatus":
            st.warning("Debes seleccionar un estatus.")
            return

        ref = df_sel.iloc[-1].copy()
        ahora = datetime.now(ZoneInfo("America/Mexico_City"))

        ref["FECHA ESTATUS BITÁCORA"] = ahora.strftime("%Y-%m-%d %H:%M:%S")
        ref["ESTATUS"] = nuevo_estatus
        ref["COMENTARIO"] = comentario
        ref["CORREO LIQUIDADOR"] = st.session_state["USUARIO"]

        agregar_fila(sheet_form, ref.to_dict())

        if uploaded_files:
            nombre_carpeta = f"SINIESTRO_{siniestro_id}"
            carpeta_id = obtener_o_crear_carpeta(nombre_carpeta, drive_service)

            for archivo in uploaded_files:
                subir_archivo_drive(
                    archivo.name,
                    archivo.read(),
                    archivo.type,
                    carpeta_id,
                    drive_service
                )

        st.session_state["last_load_time"] = 0
        st.toast("Guardando cambios...", icon="⏳",duration=5)
        st.toast("Estatus agregado correctamente", icon="✅")
        time.sleep(5)
        st.rerun()


def panel_modificar_datos(df_sel, df, siniestro_id):

    st.subheader("✏️ Modificar Datos")

    # Usamos la primera fila como referencia
    ref = df_sel.iloc[0]

    # Campos a editar
    with st.expander("DATOS DEL SINIESTRO", expanded=False):
    #num_siniestro = st.text_input("Número de siniestro", ref["# DE SINIESTRO"])
        num_siniestro = siniestro_id
        correlativo = st.text_input("Correlativo", ref["CORRELATIVO"])
        fecha_siniestro = st.date_input("Fecha del siniestro", pd.to_datetime(ref["FECHA SINIESTRO"]))
        lugar = st.text_input("Lugar del siniestro", ref["LUGAR SINIESTRO"])
        medio = st.selectbox("Medio de asignación", ["Call center", "PP", "ALMA"], index=["Call center","PP","ALMA"].index(ref["MEDIO ASIGNACIÓN"]))

    # Datos asegurado
    with st.expander("DATOS DEL ASEGURADO", expanded=False):
        asegurado_nombre = st.text_input("Nombre asegurado", ref["NOMBRE ASEGURADO"])
        asegurado_rut = st.text_input("RUT asegurado", ref["RUT ASEGURADO"])
        #asegurado_tipo = st.text_input("Tipo persona asegurado", ref["TIPO DE PERSONA ASEGURADO"])
        asegurado_tipo = st.selectbox("Tipo persona asegurado", ["","Jurídica", "Natural"], index=["","Jurídica", "Natural"].index(ref["TIPO DE PERSONA ASEGURADO"]))
        asegurado_tel = st.text_input("Teléfono asegurado", ref["TEL. ASEGURADO"])
        asegurado_correo = st.text_input("Correo asegurado", ref["CORREO ASEGURADO"])
        asegurado_dir = st.text_input("Dirección asegurado", ref["DIRECCIÓN ASEGURADO"])
        #medio = st.selectbox("Medio de asignación", ["Call center", "PP", "Otro"], index=["Call center","PP","Otro"].index(ref["MEDIO ASIGNACIÓN"]))

    # Datos propietario
    with st.expander("DATOS DEL PROPIETARIO", expanded=False):
        propietario_nombre = st.text_input("Nombre propietario", ref["NOMBRE PROPIETARIO"])
        propietario_rut = st.text_input("RUT propietario", ref["RUT PROPIETARIO"])
        #propietario_tipo = st.text_input("Tipo persona propietario", ref["TIPO DE PERSONA PROPIETARIO"])
        propietario_tipo = st.selectbox("Tipo persona propietario", ["","Jurídica", "Natural"], index=["","Jurídica", "Natural"].index(ref["TIPO DE PERSONA PROPIETARIO"]))
        propietario_tel = st.text_input("Tel. propietario", ref["TEL. PROPIETARIO"])
        propietario_correo = st.text_input("Correo propietario", ref["CORREO PROPIETARIO"])
        propietario_dir = st.text_input("Dirección propietario", ref["DIRECCIÓN PROPIETARIO"])

    # Datos vehículo
    with st.expander("DATOS DEL VEHÍCULO", expanded=False):
        marca = st.text_input("Marca", ref["MARCA"])
        submarca = st.text_input("Submarca", ref["SUBMARCA"])
        version = st.text_input("Versión", ref["VERSIÓN"])
        anio = st.text_input("Año/Modelo", ref["AÑO/MODELO"])
        serie = st.text_input("Número de serie", ref["NO. SERIE"])
        motor = st.text_input("Motor", ref["MOTOR"])
        patente = st.text_input("Patente", ref["PATENTE"])

    if st.button("💾 Guardar cambios"):
        mask = df["# DE SINIESTRO"] == siniestro_id

        df.loc[mask, "# DE SINIESTRO"] = num_siniestro
        df.loc[mask, "CORRELATIVO"] = correlativo
        df.loc[mask, "FECHA SINIESTRO"] = fecha_siniestro.strftime("%Y-%m-%d")
        df.loc[mask, "LUGAR SINIESTRO"] = lugar
        df.loc[mask, "MEDIO ASIGNACIÓN"] = medio

        df.loc[mask, "NOMBRE ASEGURADO"] = asegurado_nombre
        df.loc[mask, "RUT ASEGURADO"] = asegurado_rut
        df.loc[mask, "TIPO DE PERSONA ASEGURADO"] = asegurado_tipo
        df.loc[mask, "TEL. ASEGURADO"] = asegurado_tel
        df.loc[mask, "CORREO ASEGURADO"] = asegurado_correo
        df.loc[mask, "DIRECCIÓN ASEGURADO"] = asegurado_dir

        df.loc[mask, "NOMBRE PROPIETARIO"] = propietario_nombre
        df.loc[mask, "RUT PROPIETARIO"] = propietario_rut
        df.loc[mask, "TIPO DE PERSONA PROPIETARIO"] = propietario_tipo
        df.loc[mask, "TEL. PROPIETARIO"] = propietario_tel
        df.loc[mask, "CORREO PROPIETARIO"] = propietario_correo
        df.loc[mask, "DIRECCIÓN PROPIETARIO"] = propietario_dir

        df.loc[mask, "MARCA"] = marca
        df.loc[mask, "SUBMARCA"] = submarca
        df.loc[mask, "VERSIÓN"] = version
        df.loc[mask, "AÑO/MODELO"] = anio
        df.loc[mask, "NO. SERIE"] = serie
        df.loc[mask, "MOTOR"] = motor
        df.loc[mask, "PATENTE"] = patente

        guardar_dataframe(sheet_form, df)
        st.session_state["last_load_time"] = 0
        st.success("Datos actualizados correctamente.")
        st.rerun()
def vista_modificar_siniestro():

    st.subheader("🔍 Buscar siniestro para actualizar")

    # ============================
    #  1. Recargar DF 
    # ============================
    #df = obtener_dataframe(sheet_form)
    df = cargar_dataframe_rate_limit(sheet_form, cooldown=15)
    # ============================
    #  2. Buscar siniestro
    # ============================
    busqueda = st.text_input("ESCRIBE NÚMERO DE SINIESTRO")

    if not busqueda:
        st.info("Ingresa un número para buscar un siniestro.")
        return

    # Coincidencias en cualquier columna
    mask = df.apply(lambda r: r.astype(str).str.contains(busqueda, case=False, na=False).any(), axis=1)
    resultados = df[mask]

    if resultados.empty:
        st.warning("❌ No se encontraron coincidencias.")
        return

    siniestros_unicos = resultados["# DE SINIESTRO"].unique()

    # ============================
    #  3. Selección del siniestro
    # ============================
    seleccionado = st.selectbox(
        "Selecciona un siniestro:",
        siniestros_unicos,
        key="sel_siniestro"
    )

    if not seleccionado:
        return

    st.session_state["siniestro_actual"] = seleccionado

    # Crear df_sel siempre actualizado
    df_sel = df[df["# DE SINIESTRO"] == seleccionado]

    st.success(f"Siniestro seleccionado: {seleccionado}")

    # ============================
    #  4. Tabs
    # ============================
    tab1, tab2 = st.tabs(["✏️ Modificar Datos del Siniestro", "📌 Agregar Estatus (Seguimiento)"])

    with tab1:
        panel_modificar_datos(df_sel, df, seleccionado)

    with tab2:
        panel_seguimiento(df_sel, df, seleccionado)

    # ============================
    #  5. Regresar a inicio
    # ============================
    if st.button("Volver al inicio", icon="⬅️", use_container_width=True):
        st.session_state.vista = None
        st.rerun()




def registro_siniestro():
    st.header("Registro de nuevo siniestro")

    with st.form("form_siniestro",clear_on_submit=True):

        tabs = st.tabs([
            "📁 Datos del siniestro",
            "👤 Datos del asegurado",
            "👤 Datos del propietario",
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
                ["Call center", "PP", "ALMA"],
                key="siniestro_medio"
            )

        # ---------------------- DATOS ASEGURADO -------------------------
        with tabs[1]:
            st.subheader("Datos del asegurado")

            Asegurado_Nombre = st.text_input("Nombre", key="aseg_nombre")
            Asegurado_Rut = st.text_input("RUT", key="aseg_rut")
            Asegurado_Tipo = st.selectbox(
                "Tipo de persona",
                ["","Natural", "Jurídica"],
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
                "Tipo de persona",
                ["","Natural", "Jurídica"],
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
            enviado = st.form_submit_button("Guardar",use_container_width=True,width=150,icon="💾")

    col1, col2, col3 = st.columns(3)
    with col2: # Puedes usar esta columna para alineación si lo deseas
        limpiar = st.button("Limpiar Registro", on_click=limpiar_y_recargar,use_container_width=True,width=100,icon="🗑️")
    with col3:
        if st.button("Volver al inicio",icon="⬅️",use_container_width=True,width=100):
            st.session_state.vista = None
            st.rerun()
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
                carpeta_link
            ])
            st.success("✔ Siniestro registrado correctamente.")
            #reset_form_registro()
            #st.rerun()

def vista_buscar_siniestro():

    st.subheader("🔎 Buscar siniestro")

    siniestro = st.text_input("ESCRIBE NÚMERO DE SINIESTRO:")

    if st.button("Buscar", icon="🔎", use_container_width=True):
        
        if not siniestro:
            st.warning("Ingresa un número de siniestro.")
            return

        #df = obtener_dataframe(sheet_form)
        df = cargar_dataframe_rate_limit(sheet_form, cooldown=15)
        resultado = df[df["# DE SINIESTRO"].astype(str) == str(siniestro)]

        if resultado.empty:
            st.error("❌ Siniestro no encontrado.")
            return

        st.success("Resultado encontrado:")
        st.dataframe(resultado, use_container_width=True, hide_index=True)

        # ============================
        #   LINK A DRIVE
        # ============================
        if "DRIVE" in resultado.columns:
            drive_link = resultado.iloc[0]["DRIVE"]

            if isinstance(drive_link, str) and drive_link.startswith("http"):
                st.markdown(
                    f"<a href='{drive_link}' target='_blank' style='font-size:18px;'>📁 Abrir carpeta en Drive</a>",
                    unsafe_allow_html=True
                )
            else:
                st.info("Este siniestro no tiene un link de Drive registrado.")

        else:
            st.info("La columna 'DRIVE' no existe en el registro.")

    if st.button("Volver al inicio", icon="⬅️"):
        st.session_state.vista = None
        st.rerun()

def vista_descargas():
    st.subheader("📥 Descargas")

    # --- Cargar datos del sheet ---
    df = pd.DataFrame(sheet_form.get_all_records())

    st.write("Selecciona el tipo de bitácora a descargar.")

    opcion = st.selectbox(
        "Tipo de descarga",
        ["Selecciona una opción",
         "Bitácora de operación", 
         "Bitácora de último estatus"]
    )

    # --- BITÁCORA DE OPERACIÓN ---
    if opcion == "Bitácora de operación":
        #st.write("Descargar todos los registros de la hoja (bitácora completa).")

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="LOG")

        st.download_button(
            label="Descargar bitácora",
            icon="⬇️",
            use_container_width=True,
            data=buffer.getvalue(),
            file_name="Bitacora_Operación_SURA.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # --- BITÁCORA DE ÚLTIMO ESTATUS ---
    elif opcion == "Bitácora de último estatus":
        #st.write("Descargar solo el registro más reciente de cada siniestro.")

        # Convertir fecha si existe
        df["FECHA ESTATUS BITÁCORA"] = pd.to_datetime(
            df["FECHA ESTATUS BITÁCORA"], 
            errors="coerce"
        )

        # Ordenar para luego obtener el último registro por siniestro
        df_sorted = df.sort_values(
            by=["# DE SINIESTRO", "FECHA ESTATUS BITÁCORA"],
            ascending=[True, True]
        )

        # Obtener el último registro por siniestro
        df_ultimos = df_sorted.groupby("# DE SINIESTRO").tail(1)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_ultimos.to_excel(writer, index=False, sheet_name="LOG")

        st.download_button(
            label="Descargar bitácora",
            icon="⬇️",
            use_container_width=True,
            data=buffer.getvalue(),
            file_name="Bitacora_UltimoEstatus_SURA.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    if st.button("Volver al inicio",icon="⬅️",use_container_width=True,width=100):
        st.session_state.vista = None
        st.rerun()

def vista_registro_usuario():
    st.header("Registro de nuevo usuario")

    with st.form("form_usuario",clear_on_submit=True):
        usuario = st.text_input("NOMBRE COMPLETO:", key="nom_usuario")
        correo = st.text_input("CORREO:", key="correo")
        password = st.text_input("CONTRASEÑA", key="password",type="password")
        rol = st.selectbox("ROL",["Seleccionar rol","ADMINISTRADOR","LIQUIDADOR"],key="rol")

        enviado = st.form_submit_button("Guardar datos",use_container_width=True,width=150,icon="💾")

        if enviado:
            errores = []

            if not usuario:
                errores.append("Falta ingresar nombre del usuario")
            if not correo:
                errores.append("Falta ingresar correo del usuario")
            if not password:
                errores.append("Falta ingresar contraseña del usuario")
            if rol == "Seleccionar rol":
                errores.append("Seleccionar un rol para el usuario")

            email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
            if correo and not re.match(email_regex, correo):
                errores.append("El correo del usuario no es válido.")

            if errores:
                st.error("Revisa lo siguiente:\n- " + "\n- ".join(errores))
                return
            sheet_users.append_row([
                correo,
                password,
                rol,
                usuario
            ])
            st.success("Usuario registrado correctamente")
            CLAVE_APP = 'ckkazcijqkwikscd' #Contraseña de aplicación, utilizada para acceder al correo
            REMITENTE = 'jbarron@cibergestion.com' 
            DESTINATARIO = correo
            ASUNTO = 'SURA PT - CREACIÓN DE USUARIO'
            MENSAJE = f"""Estimado <strong>{usuario}</strong>,
            Tu usuario se ha creado correctamente. A continuación, se detallan tus datos de acceso:

            <strong>USUARIO: </strong>{correo}
            <strong>CONTRASEÑA: </strong>{password}
            <strong>ROL:</strong>{rol}

            Puedes acceder a la plataforma haciendo clic en el siguiente enlace: <a href="https://sura-pt-cibergestion.streamlit.app/">Ingresar aquí</a>
            
            Saludos.
            """
            yag = yagmail.SMTP(REMITENTE, CLAVE_APP)

            #Se envía el correo a los destinatarios con la estructura establecida en el item contents

            yag.send(
                to=DESTINATARIO, 
                subject=ASUNTO, 
                contents=[MENSAJE]
                )
        
    if st.button("Volver al inicio",icon="⬅️",use_container_width=True,width=100):
        st.session_state.vista = None
        st.rerun()
# =======================================================
#               VISTA LIQUIDADOR
# =======================================================
def vista_liquidador():

    Liquidador_Nombre = st.session_state["LIQUIDADOR"]
    st.title(f"¡HOLA, {Liquidador_Nombre}!")

    # Inicializar la variable si no existe
    if "vista" not in st.session_state:
        st.session_state.vista = None

    # ----------------------------------------------------
    #  MENÚ LATERAL
    # ----------------------------------------------------
    with st.sidebar.expander("GESTIÓN DE SINIESTRO", expanded=False):
        if st.button("REGISTRAR", use_container_width=True, icon="📄"):
            st.session_state.vista = "REGISTRAR"

        if st.button("ACTUALIZAR", use_container_width=True, icon="🔄️"):
            st.session_state.vista = "ACTUALIZAR"
    with st.sidebar:
        if st.button("BUSCAR / CONSULTAR", use_container_width=True, icon="🔎"):
            st.session_state.vista = "BUSCAR"
        #st.markdown("<div style='height:20vh'></div>", unsafe_allow_html=True)
        if st.button("Cerrar sesión", use_container_width=True,icon="❌"):
            st.session_state.clear()
            st.rerun()
    # =====================================================================================
    #                                REGISTRAR SINIESTRO
    # =====================================================================================
    if st.session_state.vista == "REGISTRAR":
        registro_siniestro()

    elif st.session_state.vista == "ACTUALIZAR":
        vista_modificar_siniestro()

    elif st.session_state.vista == "BUSCAR":
        vista_buscar_siniestro()

# =======================================================
#                VISTA ADMINISTRADOR
# =======================================================
def vista_admin():
    Liquidador_Nombre = st.session_state["LIQUIDADOR"]
    st.title(f"¡HOLA, {Liquidador_Nombre}!")

    # Inicializar la variable si no existe
    if "vista" not in st.session_state:
        st.session_state.vista = None

    # ----------------------------------------------------
    #  MENÚ LATERAL
    # ----------------------------------------------------
    with st.sidebar.expander("ADMINISTRACIÓN", expanded=False):
        if st.button("DESCARGAS", use_container_width=True, icon="📥"):
            st.session_state.vista = "DESCARGA"

        if st.button("USUARIOS", use_container_width=True, icon="👥"):
            st.session_state.vista = "USUARIOS"

    with st.sidebar.expander("GESTIÓN DE SINIESTRO", expanded=False):
        if st.button("REGISTRAR", use_container_width=True, icon="📄"):
            st.session_state.vista = "REGISTRAR"

        if st.button("ACTUALIZAR", use_container_width=True, icon="🔄️"):
            st.session_state.vista = "ACTUALIZAR"
    with st.sidebar:
        if st.button("BUSCAR / CONSULTAR", use_container_width=True, icon="🔎"):
            st.session_state.vista = "BUSCAR"
        #st.markdown("<div style='height:20vh'></div>", unsafe_allow_html=True)
        if st.button("Cerrar sesión", use_container_width=True,icon="❌"):
            st.session_state.clear()
            st.rerun()
    # =====================================================================================
    #                                REGISTRAR SINIESTRO
    # =====================================================================================
    if st.session_state.vista == "REGISTRAR":
        registro_siniestro()

    elif st.session_state.vista == "ACTUALIZAR":
        vista_modificar_siniestro()

    # =====================================================================================
    #                                BUSCAR / ACTUALIZAR
    # =====================================================================================

    elif st.session_state.vista == "BUSCAR":
        vista_buscar_siniestro()
    elif st.session_state.vista == "DESCARGA":
        vista_descargas()
    elif st.session_state.vista == "USUARIOS":
        vista_registro_usuario()
        
    #datos = sheet_form.get_all_records()
    #df = pd.DataFrame(datos)

    #st.dataframe(df)
    #st.write("Total de registros:", len(df))



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
#st.sidebar.write(f"USUARIO: **{st.session_state['USUARIO']}**")
#st.sidebar.write(f"ROL: **{st.session_state['ROL']}**")

#if st.sidebar.button("Cerrar sesión",icon="❌",use_container_width=True):
#    st.session_state.clear()
#    st.rerun()

with st.sidebar:
    st.markdown("""
        <div style="text-align:center; padding-top:10px;">
            <h1 style="margin-bottom:0; color: #00AEC7;">SURA PÉRDIDAS TOTALES</h1>
        </div>
    """, unsafe_allow_html=True)

    st.subheader("📋 MENÚ")

if st.session_state["ROL"] == "ADMINISTRADOR":
    vista_admin()
else:
    vista_liquidador()
