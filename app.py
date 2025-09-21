import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from datetime import date
import json

# --- Configurações da página ---
st.set_page_config(page_title="Assistente Grão Lar", layout="wide")
st.title("🟢 Assistente de Vendas Grão Lar")

# --- 1️⃣ Configurar APIs via st.secrets ---
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SPREADSHEET_ID = st.secrets["SPREADSHEET_ID"]
SERVICE_ACCOUNT_JSON = st.secrets["SERVICE_ACCOUNT_JSON"]

genai.configure(api_key=GEMINI_API_KEY)

# --- 2️⃣ Conectar ao Google Sheets ---
try:
    creds = Credentials.from_service_account_info(
        json.loads(SERVICE_ACCOUNT_JSON),
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    worksheet_entradas = sh.worksheet("ENTRADAS")
    worksheet_produtos = sh.worksheet("Produtos")
    st.success("✅ Conexão com Google Sheets estabelecida!")
except Exception as e:
    st.error(f"❌ Erro ao conectar com Google Sheets: {e}")
    st.stop()

# --- 3️⃣ Ler lista de produtos ---
lista_de_produtos = worksheet_produtos.get_all_records()
tipos_de_cafe = [p['TIPO'] for p in lista_de_produtos if p['TIPO']]

# --- 4️⃣ Input do usuário ---
st.subheader("Registrar venda")
comando_do_usuario = st.text_area("Digite a mensagem da venda", "")

if st.button("📤 Processar e registrar venda") and comando_do_usuario.strip():
    data_hoje = date.today().strftime("%Y-%m-%d")

    # --- Montar prompt para Gemini ---
    prompt = f"""
### CONTEXTO ###
Você é um assistente de IA especialista em processar pedidos para a loja de cafés "Grão Lar". Sua função é interpretar mensagens de texto sobre vendas e estruturar essas informações em JSON para serem inseridas na planilha Google Sheets.

### TAREFA ###
Analise a MENSAGEM DO USUÁRIO e extraia: data, tipo de café, quantidade, valor, comprador, vendedor, pago. Responda **apenas com JSON**.

### REGRAS ###
1. data: se não mencionada, use {data_hoje}.
2. tipo_de_cafe: use a lista {tipos_de_cafe}.
3. quantidade: se não mencionada, assuma 1.
4. valor: extraia apenas o valor total.
5. comprador: se não mencionado, null.
6. vendedor: se não mencionado ou "eu que vendi", use "cat".
7. pago: se houver menção de pagamento, "sim", senão "não".

### MENSAGEM ###
"{comando_do_usuario}"

### JSON DE SAÍDA ###
{{
  "data": "YYYY-MM-DD",
  "tipo_de_cafe": "string",
  "quantidade": "integer",
  "valor": "float",
  "comprador": "string | null",
  "vendedor": "string | null",
  "pago": "string"
}}
"""

    # --- 5️⃣ Chamar Gemini AI ---
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        resposta_json = response.text.strip().replace("```json", "").replace("```", "")
        dados_da_ia = json.loads(resposta_json)
    except Exception as e:
        st.error(f"❌ Erro ao chamar Gemini AI: {e}")
        st.stop()

    # --- 6️⃣ Inserir venda na planilha ---
    nova_linha = [
        dados_da_ia.get("data"),
        dados_da_ia.get("tipo_de_cafe"),
        dados_da_ia.get("quantidade"),
        dados_da_ia.get("valor"),
        dados_da_ia.get("comprador"),
        dados_da_ia.get("vendedor"),
        dados_da_ia.get("pago")
    ]

    try:
        all_values = worksheet_entradas.get_all_values()
        next_row_index = len(all_values) + 1
        worksheet_entradas.update(f"A{next_row_index}:G{next_row_index}", [nova_linha],_]()_
