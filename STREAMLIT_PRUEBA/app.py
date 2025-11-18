import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURAR CREDENCIALES ---
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(
    "Crenciales_CuentaServicio.json",  # ← renómbralo a tu archivo
    scopes=scope
)

client = gspread.authorize(creds)

# --- ABRIR LA HOJA DE GOOGLE ---
sheet = client.open("bd_prueba_streamlit").sheet1

st.title("Prueba de registro (Streamlit + Google Sheets)")

with st.form("formulario"):
    folio = st.text_input("Folio")
    estatus = st.selectbox("Estatus", ["Nuevo", "En proceso", "Finalizado"])
    comentario = st.text_area("Comentario opcional")
    
    enviar = st.form_submit_button("Guardar")

if enviar:
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        folio,
        estatus,
        comentario
    ]
    sheet.append_row(row)
    st.success("Registro guardado con éxito 🎉")

# --- MOSTRAR HISTORIAL ---
st.subheader("Historial")
data = sheet.get_all_records()
df = pd.DataFrame(data)
st.dataframe(df)
