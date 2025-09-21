import streamlit as st
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from datetime import date
import json
import os

# --- CONFIGURAÇÃO DA PÁGINA E TÍTULO ---
st.set_page_config(page_title="Assistente de Vendas Grão Lar", page_icon="☕")
st.title("🤖 Chatbot de Vendas Grão Lar")
st.caption("Olá! Sou seu assistente de IA. Diga-me qual venda você quer registrar na sua planilha.")

# --- 1. CONFIGURAÇÃO E CONEXÃO COM AS APIS (COM CACHE) ---

load_dotenv()

@st.cache_resource
def configure_apis():
    # Configura Gemini
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        st.error("A chave da API do Gemini (GEMINI_API_KEY) não foi encontrada no arquivo .env")
        st.stop()
    genai.configure(api_key=gemini_api_key)

    # Conecta ao Google Sheets usando o caminho absoluto (método mais robusto)
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        service_account_path = os.path.join(script_dir, "service_account.json")
        creds = Credentials.from_service_account_file(
            service_account_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        gc = gspread.authorize(creds)
        spreadsheet_id = "1HUvt5pRS_dC6n-3zGqPm4pyzlygHxKESYG0ljzhUfU"
        sh = gc.open_by_key(spreadsheet_id)
        return sh
    except FileNotFoundError:
        st.error("Erro Crítico: O arquivo 'service_account.json' não foi encontrado na pasta do projeto.")
        st.stop()
    except Exception as e:
        st.error(f"Erro ao conectar com o Google Sheets: {e}")
        st.stop()

sh = configure_apis()

@st.cache_data(ttl=600) # Recarrega a lista de produtos a cada 10 minutos
def get_product_list(_sh):
    try:
        worksheet_produtos = _sh.worksheet("Produtos")
        return [p['TIPO'] for p in worksheet_produtos.get_all_records() if p.get('TIPO')]
    except Exception as e:
        st.error(f"Não foi possível buscar a lista de produtos: {e}")
        return []

tipos_de_cafe = get_product_list(sh)

# --- 2. LÓGICA DO CHATBOT ---

# Inicializa o histórico de mensagens no estado da sessão
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Como posso ajudar a registrar uma venda hoje?"}]

# Exibe as mensagens do histórico
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Função para processar o comando do usuário
def processar_comando(comando_usuario):
    try:
        data_hoje = date.today().strftime("%Y-%m-%d")
        prompt_template = """
        ### CONTEXTO ###
        Você é um assistente de IA especialista em processar pedidos para a loja de cafés "Grão Lar"... (Seu prompt completo vai aqui)
        ### DADOS DE ENTRADA ###
        - Data Atual: "{data_atual}"
        - Lista de Produtos Válidos: {lista_de_produtos_validos}
        - Mensagem do Usuário: "{comando_do_usuario}"
        ### ESTRUTURA DE SAÍDA (OBRIGATÓRIO) ###
        {{
          "data": "YYYY-MM-DD", "tipo_de_cafe": "string", "quantidade": "integer",
          "valor": "float", "comprador": "string | null", "vendedor": "string | null", "pago": "string"
        }}
        """
        prompt_final = prompt_template.format(
            data_atual=data_hoje,
            lista_de_produtos_validos=tipos_de_cafe,
            comando_do_usuario=comando_usuario
        )
        
        # Chama o Gemini
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt_final)
        resposta_json = response.text.strip().replace("```json", "").replace("```", "")
        dados_da_ia = json.loads(resposta_json)
        
        # Atualiza a planilha
        nova_linha = [
            dados_da_ia.get("data"), dados_da_ia.get("tipo_de_cafe"),
            dados_da_ia.get("quantidade"), dados_da_ia.get("valor"),
            dados_da_ia.get("comprador"), dados_da_ia.get("vendedor"),
            dados_da_ia.get("pago")
        ]
        worksheet_entradas = sh.worksheet("ENTRADAS")
        all_values = worksheet_entradas.get_all_values()
        next_row_index = len(all_values) + 1
        start_cell = f"A{next_row_index}"
        worksheet_entradas.update(start_cell, [nova_linha], value_input_option='USER_ENTERED')
        
        # Retorna uma mensagem de sucesso para o chat
        return (f"✅ Venda registrada com sucesso na linha {next_row_index} da planilha!\n"
                f"- **Produto:** {dados_da_ia.get('tipo_de_cafe')}\n"
                f"- **Comprador:** {dados_da_ia.get('comprador')}\n"
                f"- **Valor:** R$ {dados_da_ia.get('valor')}")
    except Exception as e:
        return f"❌ Ocorreu um erro: {e}. Por favor, tente novamente."

# --- 3. CAMPO DE INPUT DO CHAT ---

if prompt := st.chat_input("Digite o comando da venda aqui..."):
    # Adiciona a mensagem do usuário ao histórico e exibe
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Mostra uma mensagem de "pensando" e processa o comando
    with st.chat_message("assistant"):
        with st.spinner("Analisando e atualizando a planilha..."):
            response_content = processar_comando(prompt)
            st.markdown(response_content)
            # Adiciona a resposta do assistente ao histórico
            st.session_state.messages.append({"role": "assistant", "content": response_content})

# Adiciona a lista de produtos na barra lateral como referência
st.sidebar.header("Produtos Disponíveis")
st.sidebar.dataframe(tipos_de_cafe, hide_index=True)