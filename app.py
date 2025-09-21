import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from datetime import date
import json
import re
from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode, GridUpdateMode

st.title("Assistente Grão Lar")

# --- Configurar API Gemini ---
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# --- Conectar ao Google Sheets ---
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
gc = gspread.authorize(creds)
sh = gc.open_by_key(st.secrets["SPREADSHEET_ID"])

worksheet_produtos = sh.worksheet("Produtos")
df_produtos = pd.DataFrame(worksheet_produtos.get_all_records())
tipos_de_cafe = df_produtos["TIPO"].dropna().tolist()

worksheet_entradas = sh.worksheet("ENTRADAS")
expected_headers = ["Data", "Tipo_de_Cafe", "Qtde", "Valor", "Comprador", "Vendedor", "Pago"]

# --- Função para carregar planilha ---
def carregar_planilha():
    valores = worksheet_entradas.get_all_records(expected_headers=expected_headers)
    df = pd.DataFrame(valores)
    return df

df_entradas = carregar_planilha()

# --- 1. Visualização da planilha (somente leitura) ---
st.subheader("📊 Planilha Grão Lar")
gb = GridOptionsBuilder.from_dataframe(df_entradas)
gb.configure_default_column(editable=False)  # desabilitar edição
gb.configure_selection('single', use_checkbox=False)
grid_options = gb.build()

AgGrid(
    df_entradas,
    gridOptions=grid_options,
    data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
    update_mode=GridUpdateMode.NO_UPDATE,
    fit_columns_on_grid_load=True
)

# --- 2. Adicionar nova linha manualmente ---
st.subheader("➕ Adicionar nova venda manualmente")
with st.form("nova_venda"):
    col1, col2 = st.columns(2)
    with col1:
        data_nova = st.date_input("Data", value=date.today())
        tipo_cafe_novo = st.selectbox("Tipo de Café", tipos_de_cafe)
        quantidade_novo = st.number_input("Quantidade", min_value=1, value=1)
        valor_novo = st.number_input("Valor", min_value=0.0, value=0.0, step=0.1)
    with col2:
        comprador_novo = st.text_input("Comprador")
        vendedor_novo = st.text_input("Vendedor")
        pago_novo = st.selectbox("Pago", ["Sim", "Não"])
    
    enviar_novo = st.form_submit_button("Adicionar linha")

if enviar_novo:
    try:
        nova_linha = [
            data_nova.strftime("%d-%m-%y"),
            tipo_cafe_novo,
            quantidade_novo,
            valor_novo,
            comprador_novo,
            vendedor_novo,
            pago_novo
        ]
        worksheet_entradas.append_row(nova_linha, value_input_option="USER_ENTERED")
        st.success("✅ Nova linha adicionada com sucesso!")
        df_entradas = carregar_planilha()
    except Exception as e:
        st.error(f"❌ Erro ao adicionar nova linha: {e}")

# --- 3. Registrar vendas via IA (Gemini) ---
st.subheader("🤖 Registrar vendas via IA")
comando_do_usuario = st.text_area("Digite a(s) venda(s):", height=150)
enviar_ia = st.button("Registrar venda(s) via IA")

if enviar_ia and comando_do_usuario:
    data_hoje = date.today().strftime("%d-%m-%y")

    prompt_template = """
    Você é um assistente que registra vendas de café. 
    Transforme as seguintes vendas em uma lista JSON de objetos, cada objeto contendo:
    "data", "tipo_de_cafe", "quantidade", "valor", "comprador", "vendedor", "pago".
    
    O objeto "pago" deverá conter somente a resposta "sim" ou "não".
    
    Se a data não for informada, utilize a data de hoje.
    Produtos válidos: {lista_de_produtos_validos}
    
    Vendas:
    {comando_do_usuario}
    """

    prompt_final = prompt_template.format(
        lista_de_produtos_validos=tipos_de_cafe,
        comando_do_usuario=comando_do_usuario
    )

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt_final)
        resposta_bruta = response.text

        match = re.search(r"\[.*\]", resposta_bruta, re.DOTALL)
        if match:
            resposta_json = match.group()
            try:
                lista_vendas = json.loads(resposta_json)

                st.write("📋 Resumo das vendas:")
                for i, venda in enumerate(lista_vendas, start=1):
                    st.write(f"**Venda {i}:** {venda['data']} | {venda['tipo_de_cafe']} | {venda['quantidade']} un | {venda['valor']} | {venda['comprador']} | {venda['vendedor']} | {venda['pago']}")

                # Inserir em batch na planilha
                df_entradas_atual = carregar_planilha()
                linhas_existentes = len(df_entradas_atual)
                batch_data = []
                for i, venda in enumerate(lista_vendas):
                    nova_linha = [
                        venda.get("data", data_hoje),
                        venda.get("tipo_de_cafe"),
                        venda.get("quantidade"),
                        venda.get("valor"),
                        venda.get("comprador"),
                        venda.get("vendedor"),
                        venda.get("pago")
                    ]
                    batch_data.append({
                        "range": f"A{linhas_existentes+i+2}:G{linhas_existentes+i+2}",
                        "values": [nova_linha]
                    })
                if batch_data:
                    worksheet_entradas.batch_update(batch_data)

                st.success(f"✅ {len(lista_vendas)} venda(s) registradas com sucesso na planilha!")
                df_entradas = carregar_planilha()

            except json.JSONDecodeError as e:
                st.error(f"❌ Erro ao decodificar JSON: {e}")
        else:
            st.error("❌ Não foi possível extrair JSON válido da resposta da IA.")
    except Exception as e:
        st.error(f"❌ Erro ao registrar venda(s): {e}")
