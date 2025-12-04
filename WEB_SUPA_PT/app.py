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
    """
    Vista para buscar, seleccionar y modificar siniestros.
    - Busca y muestra tabla compacta.
    - Al seleccionar un siniestro, muestra dos tabs:
        1) Modificar datos (afecta todas las filas del siniestro)
        2) Agregar estatus / seguimiento (añade nueva fila)
    """

    st.title("🔧 Modificar Siniestro")

    # -------------- CARGAR DATOS desde Google Sheets --------------
    try:
        records = sheet_form.get_all_records()
        df = pd.DataFrame(records)
    except Exception as e:
        st.error(f"Error leyendo la hoja: {e}")
        return

    if df.empty:
        st.warning("No hay siniestros registrados aún.")
        return

    # Asegurar columnas clave existan
    required_cols = [
        "# DE SINIESTRO","CORRELATIVO","FECHA SINIESTRO","LUGAR SINIESTRO","MEDIO ASIGNACIÓN",
        "MARCA","SUBMARCA","VERSIÓN","AÑO/MODELO","NO. SERIE","MOTOR","PATENTE",
        "FECHA ESTATUS BITÁCORA","ESTATUS",
        "NOMBRE ASEGURADO","RUT ASEGURADO","TIPO DE PERSONA ASEGURADO","TEL. ASEGURADO","CORREO ASEGURADO","DIRECCIÓN ASEGURADO",
        "NOMBRE PROPIETARIO","RUT PROPIETARIO","TIPO DE PERSONA PROPIETARIO","TEL. PROPIETARIO","CORREO PROPIETARIO","DIRECCIÓN PROPIETARIO",
        "LIQUIDADOR","CORREO LIQUIDADOR","DRIVE"
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"Faltan columnas en la hoja: {missing}")
        return

    # Normalizar a strings para buscar sin problemas
    df["# DE SINIESTRO"] = df["# DE SINIESTRO"].astype(str)
    df["PATENTE"] = df["PATENTE"].astype(str)
    df["NOMBRE ASEGURADO"] = df["NOMBRE ASEGURADO"].astype(str)
    df["NOMBRE PROPIETARIO"] = df["NOMBRE PROPIETARIO"].astype(str)

    # -------------- BUSCADOR Y TABLA COMPACTA --------------
    st.subheader("🔍 Buscar siniestro")
    buscar = st.text_input("Escribe número de siniestro, asegurado, patente o propietario", key="buscar_mod")

    # Filtrado reactivo
    if buscar:
        filt = df[
            df["# DE SINIESTRO"].str.contains(buscar, case=False, na=False) |
            df["NOMBRE ASEGURADO"].str.contains(buscar, case=False, na=False) |
            df["PATENTE"].str.contains(buscar, case=False, na=False) |
            df["NOMBRE PROPIETARIO"].str.contains(buscar, case=False, na=False)
        ]
    else:
        filt = df.copy()

    # Construir tabla compacta con la info relevante y botón seleccionar
    st.markdown("**Resultados** (selecciona una fila para editar)")

    # Columnas a mostrar
    display_cols = ["# DE SINIESTRO", "FECHA SINIESTRO", "NOMBRE ASEGURADO", "MARCA", "AÑO/MODELO", "ESTATUS"]

    # Mostrar encabezados
    header_cols = st.columns(len(display_cols) + 1)
    for i, c in enumerate(display_cols):
        header_cols[i].markdown(f"**{c}**")
    header_cols[-1].markdown("**Acción**")

    selected_siniestro = None
    # Recorrer filas filtradas (limitamos a primeras 200 para evitar UI pesada)
    for idx, row in filt.reset_index(drop=True).head(200).iterrows():
        cols = st.columns(len(display_cols) + 1)
        for i, c in enumerate(display_cols):
            cols[i].write(row.get(c, ""))
        # botón seleccionar con key única (usar índice del dataframe original)
        original_index = df.index[df["# DE SINIESTRO"] == row["# DE SINIESTRO"]][0]
        if cols[-1].button("Seleccionar", key=f"sel_{int(original_index)}"):
            selected_siniestro = row["# DE SINIESTRO"]
            # guardar en session para persistencia si se desea
            st.session_state["selected_siniestro"] = selected_siniestro
            st.experimental_rerun()

    # Si user ya seleccionó antes y no refrescó
    if "selected_siniestro" in st.session_state and not selected_siniestro:
        selected_siniestro = st.session_state["selected_siniestro"]

    if not selected_siniestro:
        st.info("Selecciona un siniestro de la lista para editar o usa el buscador.")
        return

    # -------------- CARGAR FILAS DEL SINIESTRO SELECCIONADO --------------
    sin_df = df[df["# DE SINIESTRO"] == str(selected_siniestro)].reset_index(drop=True)
    if sin_df.empty:
        st.error("No se encontró información del siniestro seleccionado.")
        return

    base = sin_df.iloc[0].copy()  # referencia para rellenar campos

    st.success(f"Siniestro seleccionado: {selected_siniestro} — filas: {len(sin_df)}")
    st.markdown("---")

    # -------------- TABS: modificar datos / agregar estatus --------------
    tab_datos, tab_estatus = st.tabs(["✏️ Modificar datos", "📌 Agregar estatus (seguimiento)"])

    # ---------------- TAB: MODIFICAR DATOS ----------------
    with tab_datos:
        st.header("Modificar datos del siniestro (se aplicará a todas las filas)")

        with st.form(f"form_modif_{selected_siniestro}", clear_on_submit=False):
            # DATOS DEL SINIESTRO
            st.subheader("Datos del siniestro")
            Correlativo = st.text_input("Correlativo", value=base["CORRELATIVO"], key=f"c_corr_{selected_siniestro}")
            # convertir FECHA SINIESTRO a date si viene en otro formato
            try:
                fecha_prefill = pd.to_datetime(base["FECHA SINIESTRO"], errors="coerce")
                fecha_prefill = fecha_prefill.date() if not pd.isna(fecha_prefill) else None
            except Exception:
                fecha_prefill = None
            Fecha_siniestro = st.date_input("Fecha siniestro", value=fecha_prefill, key=f"c_fecha_{selected_siniestro}")
            Lugar_siniestro = st.text_input("Lugar siniestro", value=base["LUGAR SINIESTRO"], key=f"c_lugar_{selected_siniestro}")
            Medio_asign = st.selectbox("Medio de asignación", ["Call center", "PP", "Otro"],
                                       index=(["Call center","PP","Otro"].index(base["MEDIO ASIGNACIÓN"])
                                              if base["MEDIO ASIGNACIÓN"] in ["Call center","PP","Otro"] else 0),
                                       key=f"c_medio_{selected_siniestro}")

            # ASEGURADO
            st.subheader("Datos del asegurado")
            A_Nombre = st.text_input("Nombre asegurado", value=base["NOMBRE ASEGURADO"], key=f"c_aseg_nom_{selected_siniestro}")
            A_Rut = st.text_input("Rut asegurado", value=base["RUT ASEGURADO"], key=f"c_aseg_rut_{selected_siniestro}")
            A_Tipo = st.selectbox("Tipo de persona (asegurado)", ["Natural", "Jurídica"],
                                  index=(["Natural","Jurídica"].index(base["TIPO DE PERSONA ASEGURADO"])
                                         if base["TIPO DE PERSONA ASEGURADO"] in ["Natural","Jurídica"] else 0),
                                  key=f"c_aseg_tipo_{selected_siniestro}")
            A_Tel = st.text_input("Teléfono asegurado", value=base["TEL. ASEGURADO"], key=f"c_aseg_tel_{selected_siniestro}")
            A_Correo = st.text_input("Correo asegurado", value=base["CORREO ASEGURADO"], key=f"c_aseg_mail_{selected_siniestro}")
            A_Dir = st.text_input("Dirección asegurado", value=base["DIRECCIÓN ASEGURADO"], key=f"c_aseg_dir_{selected_siniestro}")

            # PROPIETARIO
            st.subheader("Datos del propietario")
            P_Nombre = st.text_input("Nombre propietario", value=base["NOMBRE PROPIETARIO"], key=f"c_prop_nom_{selected_siniestro}")
            P_Rut = st.text_input("Rut propietario", value=base["RUT PROPIETARIO"], key=f"c_prop_rut_{selected_siniestro}")
            P_Tipo = st.selectbox("Tipo de persona (propietario)", ["Natural", "Jurídica"],
                                  index=(["Natural","Jurídica"].index(base["TIPO DE PERSONA PROPIETARIO"])
                                         if base["TIPO DE PERSONA PROPIETARIO"] in ["Natural","Jurídica"] else 0),
                                  key=f"c_prop_tipo_{selected_siniestro}")
            P_Tel = st.text_input("Teléfono propietario", value=base["TEL. PROPIETARIO"], key=f"c_prop_tel_{selected_siniestro}")
            P_Correo = st.text_input("Correo propietario", value=base["CORREO PROPIETARIO"], key=f"c_prop_mail_{selected_siniestro}")
            P_Dir = st.text_input("Dirección propietario", value=base["DIRECCIÓN PROPIETARIO"], key=f"c_prop_dir_{selected_siniestro}")

            # VEHÍCULO
            st.subheader("Datos del vehículo")
            Marca = st.text_input("Marca", value=base["MARCA"], key=f"c_veh_marca_{selected_siniestro}")
            Submarca = st.text_input("Submarca", value=base["SUBMARCA"], key=f"c_veh_submarca_{selected_siniestro}")
            Version = st.text_input("Versión", value=base["VERSIÓN"], key=f"c_veh_version_{selected_siniestro}")
            Anio = st.text_input("Año/Modelo", value=base["AÑO/MODELO"], key=f"c_veh_anio_{selected_siniestro}")
            Serie = st.text_input("Número de serie", value=base["NO. SERIE"], key=f"c_veh_serie_{selected_siniestro}")
            Motor = st.text_input("Motor", value=base["MOTOR"], key=f"c_veh_motor_{selected_siniestro}")
            Patente = st.text_input("Patente", value=base["PATENTE"], key=f"c_veh_patente_{selected_siniestro}")

            submit_changes = st.form_submit_button("💾 Guardar cambios en todas las filas")

        # AL SUBMIT: actualizar TODAS las filas del siniestro
        if submit_changes:
            # validaciones básicas
            errores = []
            if not selected_siniestro:
                st.error("No hay siniestro seleccionado.")
                return
            if not Correlativo:
                errores.append("Correlativo obligatorio.")
            if A_Correo and not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", A_Correo):
                errores.append("Correo asegurado inválido.")
            if P_Correo and not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", P_Correo):
                errores.append("Correo propietario inválido.")

            if errores:
                st.error("Corrige:\n- " + "\n- ".join(errores))
            else:
                # Construir fila con el ORDEN EXACTO de tu hoja (29 columnas)
                # 1..29 según tu esquema
                updated_row = [
                    str(selected_siniestro),          # 1 # DE SINIESTRO
                    Correlativo,                      # 2 CORRELATIVO
                    Fecha_siniestro.strftime("%Y-%m-%d") if Fecha_siniestro else "",  # 3 FECHA SINIESTRO
                    Lugar_siniestro,                  # 4 LUGAR SINIESTRO
                    Medio_asign,                      # 5 MEDIO ASIGNACIÓN
                    Marca,                             # 6 MARCA
                    Submarca,                          # 7 SUBMARCA
                    Version,                           # 8 VERSIÓN
                    Anio,                              # 9 AÑO/MODELO
                    Serie,                             # 10 NO. SERIE
                    Motor,                             # 11 MOTOR
                    Patente,                           # 12 PATENTE
                    "",                                # 13 FECHA ESTATUS BITÁCORA (no tocar)
                    "",                                # 14 ESTATUS (no tocar)
                    A_Nombre,                          # 15 NOMBRE ASEGURADO
                    A_Rut,                             # 16 RUT ASEGURADO
                    A_Tipo,                            # 17 TIPO DE PERSONA ASEGURADO
                    A_Tel,                             # 18 TEL. ASEGURADO
                    A_Correo,                          # 19 CORREO ASEGURADO
                    A_Dir,                             # 20 DIRECCIÓN ASEGURADO
                    P_Nombre,                          # 21 NOMBRE PROPIETARIO
                    P_Rut,                             # 22 RUT PROPIETARIO
                    P_Tipo,                            # 23 TIPO DE PERSONA PROPIETARIO
                    P_Tel,                             # 24 TEL. PROPIETARIO
                    P_Correo,                          # 25 CORREO PROPIETARIO
                    P_Dir,                             # 26 DIRECCIÓN PROPIETARIO
                    st.session_state.get("LIQUIDADOR", ""), # 27 LIQUIDADOR (se mantiene o actualiza según tu lógica)
                    st.session_state.get("USUARIO", ""),    # 28 CORREO LIQUIDADOR (usuario)
                    base.get("DRIVE", "")               # 29 DRIVE (mantener)
                ]

                # Actualizar cada fila que corresponde al siniestro
                indices = sin_df.index.tolist()  # índices relativos al df original? sin_df was reset, need original positions
                # we must find original row numbers in sheet_form
                orig_indices = df.index[df["# DE SINIESTRO"] == str(selected_siniestro)].tolist()
                try:
                    for orig in orig_indices:
                        row_number = orig + 2  # +2 por header
                        # Actualiza columnas A:AC (29 columnas -> A..AC)
                        sheet_form.update(f"A{row_number}:AC{row_number}", [updated_row])
                    st.success("Cambios aplicados en todas las filas del siniestro.")
                except Exception as e:
                    st.error(f"Error al actualizar en Google Sheets: {e}")

    # ---------------- TAB: AGREGAR ESTATUS / SEGUIMIENTO ----------------
    with tab_estatus:
        st.header("Agregar estatus / seguimiento")

        with st.form(f"form_estatus_{selected_siniestro}"):
            nuevo_estatus = st.selectbox("Nuevo estatus", [
                "ASIGNADO", "EN PROCESO", "FINALIZADO", "PENDIENTE", "CANCELADO"
            ], key=f"estatus_sel_{selected_siniestro}")
            comentario = st.text_area("Comentario (opcional)", key=f"estatus_com_{selected_siniestro}")
            submit_status = st.form_submit_button("➕ Agregar estatus")

        if submit_status:
            # construir nueva fila copiando base y cambiando campos requeridos
            timestamp = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d %H:%M:%S")
            nueva = [
                str(selected_siniestro),   # 1
                base.get("CORRELATIVO", ""),   # 2
                base.get("FECHA SINIESTRO", ""),# 3
                base.get("LUGAR SINIESTRO", ""),# 4
                base.get("MEDIO ASIGNACIÓN", ""),#5
                base.get("MARCA", ""),         #6
                base.get("SUBMARCA", ""),      #7
                base.get("VERSIÓN", ""),       #8
                base.get("AÑO/MODELO", ""),    #9
                base.get("NO. SERIE", ""),     #10
                base.get("MOTOR", ""),         #11
                base.get("PATENTE", ""),       #12
                timestamp,                     #13 FECHA ESTATUS BITÁCORA (nuevo)
                nuevo_estatus,                 #14 ESTATUS (nuevo)
                base.get("NOMBRE ASEGURADO", ""),#15
                base.get("RUT ASEGURADO", ""),   #16
                base.get("TIPO DE PERSONA ASEGURADO", ""), #17
                base.get("TEL. ASEGURADO", ""),  #18
                base.get("CORREO ASEGURADO", ""),#19
                base.get("DIRECCIÓN ASEGURADO", ""),#20
                base.get("NOMBRE PROPIETARIO", ""),#21
                base.get("RUT PROPIETARIO", ""),   #22
                base.get("TIPO DE PERSONA PROPIETARIO", ""),#23
                base.get("TEL. PROPIETARIO", ""),  #24
                base.get("CORREO PROPIETARIO", ""),#25
                base.get("DIRECCIÓN PROPIETARIO", ""),#26
                st.session_state.get("LIQUIDADOR", ""),   #27 LIQUIDADOR (usuario actual)
                st.session_state.get("USUARIO", ""),      #28 CORREO LIQUIDADOR
                base.get("DRIVE", "")                     #29 DRIVE
            ]
            try:
                sheet_form.append_row(nueva)
                st.success("Estatus agregado: fila nueva creada en la bitácora.")
            except Exception as e:
                st.error(f"Error al agregar estatus: {e}")

    # End function

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
