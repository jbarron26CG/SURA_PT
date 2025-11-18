import streamlit as st
import pandas as pd
from google.oauth2.service_account import Credentials
import gspread

# --- CONFIGURAR CREDENCIALES ---
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)

# --- ABRIR SPREADSHEET ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1N968vVRp3VfX8r1sRdUA8bdeMxx6Ldjj_a4_coah_BY/edit?gid=0#gid=0"
sheet = client.open_by_url(SHEET_URL).sheet1  # primera hoja

st.title("Prueba de Google Sheets + Streamlit")

# --- FORMULARIO ---
with st.form("formulario_prueba"):
    nombre = st.text_input("Nombre")
    estatus = st.selectbox("Estatus", ["Nuevo", "En proceso", "Finalizado"])
    enviado = st.form_submit_button("Guardar")

# --- GUARDAR EN GOOGLE SHEETS ---
if enviado:
    sheet.append_row([nombre, estatus])
    st.success("Datos guardados correctamente en Google Sheets.")

# --- MOSTRAR DATOS ---
st.subheader("Datos actuales en la hoja")
datos = sheet.get_all_records()
df = pd.DataFrame(datos)
st.dataframe(df)
