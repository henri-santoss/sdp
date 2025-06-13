
# Execute com: streamlit run app.py
import streamlit as st
import sqlite3
from datetime import datetime
import re
import pandas as pd
from PIL import Image
import io
import uuid
import cv2
import pytesseract
import numpy as np

# Configuração inicial do Streamlit
st.set_page_config(page_title="Controle de Acesso Carbon", layout="wide", page_icon="🚗")

# Configuração do Tesseract (descomente e ajuste o caminho se necessário)
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class VehicleAccessSystem:
    def __init__(self):
        self.conn = sqlite3.connect('carbon_access.db', check_same_thread=False)
        self.create_database()

    def create_database(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS colaboradores (
                id TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                cargo TEXT NOT NULL,
                tag_id TEXT UNIQUE,
                foto BLOB,
                ativo BOOLEAN DEFAULT 1
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS veiculos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                placa TEXT UNIQUE NOT NULL,
                modelo TEXT NOT NULL,
                marca TEXT,
                cor TEXT,
                colaborador_id TEXT,
                tipo_veiculo TEXT CHECK(tipo_veiculo IN ('Vendedor', 'Diretor', 'Gerente', 'Funcionario', 'Visitante')),
                FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS acessos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                veiculo_id INTEGER,
                data_hora TEXT NOT NULL,
                acesso_permitido BOOLEAN NOT NULL,
                observacoes TEXT,
                FOREIGN KEY (veiculo_id) REFERENCES veiculos(id)
            )
        ''')
        self.conn.commit()

    def validate_plate(self, placa):
        placa = placa.replace(" ", "").replace("-", "").upper()
        mercosul_pattern = r'^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$'
        old_pattern = r'^[A-Z]{3}[0-9]{4}$'
        return bool(re.match(mercosul_pattern, placa) or re.match(old_pattern, placa))

    def get_vehicle_info(self, placa):
        cursor = self.conn.cursor()
        placa = placa.replace(" ", "").replace("-", "").upper()
        cursor.execute('''
            SELECT v.placa, v.modelo, v.marca, v.cor, v.tipo_veiculo,
                   c.nome, c.cargo, c.tag_id, c.foto
            FROM veiculos v
            JOIN colaboradores c ON v.colaborador_id = c.id
            WHERE v.placa = ?
        ''', (placa,))
        return cursor.fetchone()

    def get_employees_by_name(self, nome):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, nome, cargo, tag_id, foto
            FROM colaboradores
            WHERE nome LIKE ? AND ativo = 1
        ''', (f'%{nome}%',))
        return cursor.fetchall()

    def get_vehicles_by_employee(self, colaborador_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT placa, modelo, marca, cor, tipo_veiculo
            FROM veiculos
            WHERE colaborador_id = ?
        ''', (colaborador_id,))
        return cursor.fetchall()

    def get_employee_by_id(self, colaborador_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, nome, cargo, tag_id, foto
            FROM colaboradores
            WHERE id = ? AND ativo = 1
        ''', (colaborador_id,))
        return cursor.fetchone()

    def get_vehicle_by_plate(self, placa):
        cursor = self.conn.cursor()
        placa = placa.replace(" ", "").replace("-", "").upper()
        cursor.execute('''
            SELECT id, placa, modelo, marca, cor, tipo_veiculo, colaborador_id
            FROM veiculos
            WHERE placa = ?
        ''', (placa,))
        return cursor.fetchone()

    def register_access(self, placa, permitido, observacoes=""):
        try:
            cursor = self.conn.cursor()
            placa = placa.replace(" ", "").replace("-", "").upper()
            cursor.execute("SELECT id FROM veiculos WHERE placa = ?", (placa,))
            veiculo_id = cursor.fetchone()
            if veiculo_id:
                data_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute('''
                    INSERT INTO acessos (veiculo_id, data_hora, acesso_permitido, observacoes)
                    VALUES (?, ?, ?, ?)
                ''', (veiculo_id[0], data_hora, permitido, observacoes))
                self.conn.commit()
                return True, f"Acesso registrado com sucesso para placa {placa}"
            else:
                return False, f"Veículo com placa {placa} não encontrado"
        except sqlite3.Error as e:
            return False, f"Erro ao registrar acesso: {e}"

    def add_employee(self, nome, cargo, tag_id, foto=None):
        try:
            cursor = self.conn.cursor()
            colaborador_id = str(uuid.uuid4())
            cursor.execute('''
                INSERT INTO colaboradores (id, nome, cargo, tag_id, foto)
                VALUES (?, ?, ?, ?, ?)
            ''', (colaborador_id, nome, cargo, tag_id, foto))
            self.conn.commit()
            return colaborador_id
        except sqlite3.IntegrityError:
            st.error("Tag ID já cadastrada")
            return None

    def update_employee(self, colaborador_id, nome, cargo, tag_id, foto=None):
        try:
            cursor = self.conn.cursor()
            if foto:
                cursor.execute('''
                    UPDATE colaboradores
                    SET nome = ?, cargo = ?, tag_id = ?, foto = ?
                    WHERE id = ?
                ''', (nome, cargo, tag_id, foto, colaborador_id))
            else:
                cursor.execute('''
                    UPDATE colaboradores
                    SET nome = ?, cargo = ?, tag_id = ?
                    WHERE id = ?
                ''', (nome, cargo, tag_id, colaborador_id))
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.IntegrityError:
            st.error("Tag ID já cadastrada")
            return False
        except sqlite3.Error as e:
            st.error(f"Erro ao atualizar colaborador: {e}")
            return False

    def update_employee_photo(self, colaborador_id, foto):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE colaboradores
                SET foto = ?
                WHERE id = ?
            ''', (foto, colaborador_id))
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            st.error(f"Erro ao atualizar foto: {e}")
            return False

    def add_vehicle(self, placa, modelo, marca, cor, colaborador_id, tipo_veiculo):
        if not self.validate_plate(placa):
            return False, "Placa inválida (use padrão Mercosul AAA0A00 ou antigo AAA0000)"
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO veiculos (placa, modelo, marca, cor, colaborador_id, tipo_veiculo)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (placa.upper(), modelo, marca, cor, colaborador_id, tipo_veiculo))
            self.conn.commit()
            return True, "Veículo cadastrado com sucesso"
        except sqlite3.IntegrityError:
            return False, "Placa já cadastrada"

    def update_vehicle(self, veiculo_id, placa, modelo, marca, cor, colaborador_id, tipo_veiculo):
        if not self.validate_plate(placa):
            return False, "Placa inválida (use padrão Mercosul AAA0A00 ou antigo AAA0000)"
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE veiculos
                SET placa = ?, modelo = ?, marca = ?, cor = ?, colaborador_id = ?, tipo_veiculo = ?
                WHERE id = ?
            ''', (placa.upper(), modelo, marca, cor, colaborador_id, tipo_veiculo, veiculo_id))
            self.conn.commit()
            return cursor.rowcount > 0, "Veículo atualizado com sucesso"
        except sqlite3.IntegrityError:
            return False, "Placa já cadastrada"
        except sqlite3.Error as e:
            return False, f"Erro ao atualizar veículo: {e}"

# Pré-processamento de imagem para OCR (com detecção de contornos)
def preprocess_image_for_ocr(imagem):
    # Redimensionar para melhorar a resolução
    scale_percent = 150  # Aumentar em 50%
    width = int(imagem.shape[1] * scale_percent / 100)
    height = int(imagem.shape[0] * scale_percent / 100)
    imagem = cv2.resize(imagem, (width, height), interpolation=cv2.INTER_CUBIC)
    
    # Converter para escala de cinza
    gray = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
    # Equalização de histograma
    gray = cv2.equalizeHist(gray)
    # Detectar bordas com Canny
    edges = cv2.Canny(gray, 100, 200)
    # Encontrar contornos
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        # Selecionar o maior contorno (provavelmente a placa)
        largest_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)
        # Verificar se o contorno é grande o suficiente (evitar ruídos)
        if w > 50 and h > 20:
            cropped = gray[y:y+h, x:x+w]
            # Limiar adaptativo na região recortada
            thresh = cv2.adaptiveThreshold(cropped, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            return thresh, cropped
    # Fallback: usar a imagem inteira se não encontrar contornos
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    return thresh, gray

# Extração de texto da placa (com depuração)
def extract_plate_text(imagem):
    try:
        # Obter imagem pré-processada e imagem recortada para depuração
        processed_image, debug_image = preprocess_image_for_ocr(imagem)
        # Exibir imagem pré-processada para depuração
        st.image(processed_image, caption="Imagem Pré-processada para OCR", use_column_width=True)
        st.image(debug_image, caption="Imagem Recortada (se aplicável)", use_column_width=True)
        # Configurações do Tesseract
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-'
        text = pytesseract.image_to_string(processed_image, config=custom_config)
        st.write(f"Texto bruto extraído: '{text}'")  # Depuração
        text = re.sub(r'[^A-Z0-9]', '', text.upper()).strip()
        # Validação de placa
        if re.match(r'^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$', text) or re.match(r'^[A-Z]{3}[0-9]{4}$', text):
            return text
        return None
    except Exception as e:
        st.error(f"Erro ao processar imagem: {e}")
        return None

# Interface Streamlit
system = VehicleAccessSystem()

st.title("🚗 Sistema de Controle de Acesso - Carbon")

# Estilização CSS
st.markdown("""
    <style>
    div.stButton > button[kind="primary"] {
        background-color: #28a745 !important;
        color: white !important;
        border: none !important;
        padding: 12px 24px !important;
        font-size: 16px !important;
        min-width: 120px !important;
        margin: 5px !important;
        border-radius: 8px !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #218838 !important;
    }
    div.stButton > button[kind="secondary"] {
        background-color: #dc3545 !important;
        color: white !important;
        border: none !important;
        padding: 12px 24px !important;
        font-size: 16px !important;
        min-width: 120px !important;
        margin: 5px !important;
        border-radius: 8px !important;
    }
    div.stButton > button[kind="secondary"]:hover {
        background-color: #c82333 !important;
    }
    .or-label {
        font-size: 16px;
        color: #666;
        text-align: left;
        margin: 10px 0;
    }
    @media (max-width: 600px) {
        div.stButton > button {
            width: 100% !important;
            margin-bottom: 10px !important;
        }
        .stColumn {
            flex-direction: column !important;
            width: 100% !important;
        }
        .stTextInput > div > input {
            font-size: 16px !important;
            padding: 10px !important;
        }
        .stTextArea > div > textarea {
            font-size: 16px !important;
            padding: 10px !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

# Menu lateral
menu_option = st.sidebar.selectbox("Menu", ["Controle de Acesso", "Cadastros", "Relatórios"])

if menu_option == "Controle de Acesso":
    st.header("Registro de Acesso")

    if 'form_key' not in st.session_state:
        st.session_state.form_key = str(uuid.uuid4())
    if 'vehicle_info' not in st.session_state:
        st.session_state.vehicle_info = None
    if 'employees' not in st.session_state:
        st.session_state.employees = []
    if 'captured_plate' not in st.session_state:
        st.session_state.captured_plate = ""

    with st.form(key=st.session_state.form_key):
        plate_input = st.text_input("Digite a placa do veículo (ex.: ABC1D23 ou ABC1234):", value=st.session_state.captured_plate, key="plate_input").upper()
        st.markdown('<div class="or-label">OU</div>', unsafe_allow_html=True)
        name_input = st.text_input("Digite o nome do colaborador (ex.: Marcelo):", key="name_input")
        notes = st.text_area("Observações (opcional):", key="notes_access")
        col1, col2 = st.columns([1, 1])
        with col1:
            search_submitted = st.form_submit_button("Consultar")
        with col2:
            capture_button = st.form_submit_button("📷 Capturar Placa")

    if capture_button:
        st.session_state.vehicle_info = None
        st.session_state.employees = []
        st.info("Tire a foto com boa iluminação, placa centralizada e sem reflexos. Enquadre a placa para ocupar a maior parte da imagem.")
        camera_image = st.camera_input("Capturar Placa")
        if camera_image is not None:
            img = Image.open(camera_image)
            img_array = np.array(img)
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            st.image(img_bgr, channels="BGR", caption="Imagem Capturada", use_column_width=True)
            plate_text = extract_plate_text(img_bgr)
            if plate_text:
                st.session_state.captured_plate = plate_text
                st.success(f"Placa detectada: {plate_text}")
                st.session_state.form_key = str(uuid.uuid4())
            else:
                st.warning("Nenhuma placa válida detectada. Tente novamente ou digite manualmente.")

    if search_submitted:
        st.session_state.vehicle_info = None
        st.session_state.employees = []
        if not plate_input and not name_input:
            st.warning("Digite uma placa ou um nome para buscar.")
        else:
            if plate_input:
                if system.validate_plate(plate_input):
                    vehicle_info = system.get_vehicle_info(plate_input)
                    if vehicle_info:
                        st.session_state.vehicle_info = vehicle_info
                    else:
                        st.error(f"⚠️ Veículo com placa {plate_input} não cadastrado")
                else:
                    st.warning("Formato de placa inválido. Use o padrão Mercosul (ex.: ABC1D23) ou antigo (ex.: ABC1234)")
            if name_input:
                employees = system.get_employees_by_name(name_input)
                if employees:
                    st.session_state.employees = employees
                else:
                    st.warning("Nenhum colaborador encontrado com este nome.")

    if st.session_state.vehicle_info:
        plate, model, brand, color, v_type, name, position, tag_id, photo = st.session_state.vehicle_info
        st.success(f"🚘 Veículo encontrado: {plate}")
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            st.subheader("Informações do Veículo")
            st.write(f"**Placa:** {plate}")
            st.write(f"**Modelo/Marca:** {model} / {brand}")
            st.write(f"**Cor:** {color}")
            st.write(f"**Tipo:** {v_type}")
        with col_v2:
            st.subheader("Informações do Colaborador")
            st.write(f"**Nome:** {name}")
            st.write(f"**Cargo:** {position}")
            st.write(f"**Tag ID:** {tag_id}")
            if photo:
                st.image(Image.open(io.BytesIO(photo)), caption="Foto do Colaborador", width=150)

        col_btn1, col_btn2, _ = st.columns([1, 1, 3])
        with col_btn1:
            if st.button("✔ Liberar Acesso", key=f"approve_plate_{plate}", type="primary"):
                success, message = system.register_access(plate, True, notes)
                if success:
                    st.success(message)
                    st.session_state.vehicle_info = None
                    st.session_state.employees = []
                    st.session_state.captured_plate = ""
                    st.session_state.form_key = str(uuid.uuid4())
                else:
                    st.error(message)
        with col_btn2:
            if st.button("✘ Reprovar Acesso", key=f"deny_plate_{plate}", type="secondary"):
                success, message = system.register_access(plate, False, notes)
                if success:
                    st.success(message)
                    st.session_state.vehicle_info = None
                    st.session_state.employees = []
                    st.session_state.captured_plate = ""
                    st.session_state.form_key = str(uuid.uuid4())
                else:
                    st.error(message)

        with st.expander("Ver últimos acessos"):
            cursor = system.conn.cursor()
            cursor.execute('''
                SELECT data_hora, acesso_permitido, observacoes
                FROM acessos a
                JOIN veiculos v ON a.veiculo_id = v.id
                WHERE v.placa = ?
                ORDER BY a.data_hora DESC LIMIT 5
            ''', (plate,))
            accesses = cursor.fetchall()
            if accesses:
                df = pd.DataFrame(
                    accesses,
                    columns=["Data/Hora", "Status", "Observações"],
                    index=range(1, len(accesses) + 1)
                )
                df["Status"] = df["Status"].apply(lambda x: "LIBERADO" if x else "NEGADO")
                st.dataframe(df)
            else:
                st.info("Nenhum acesso registrado para este veículo.")

    if st.session_state.employees:
        st.subheader("Colaboradores Encontrados")
        for emp in st.session_state.employees:
            emp_id, emp_name, emp_position, emp_tag, emp_photo = emp
            st.write("---")
            col_e1, col_e2 = st.columns([3, 1])
            with col_e1:
                st.write(f"**Nome:** {emp_name}")
                st.write(f"**Cargo:** {emp_position}")
                st.write(f"**Tag ID:** {emp_tag}")
            with col_e2:
                if emp_photo:
                    st.image(Image.open(io.BytesIO(emp_photo)), caption="Foto do Colaborador", width=100)

            vehicles = system.get_vehicles_by_employee(emp_id)
            if vehicles:
                st.write("**Veículos Associados:**")
                df_vehicles = pd.DataFrame(
                    vehicles,
                    columns=["Placa", "Modelo", "Marca", "Cor", "Tipo"],
                    index=range(1, len(vehicles) + 1)
                )
                selected_vehicle = st.selectbox(
                    "Selecione um veículo para registrar acesso",
                    options=df_vehicles["Placa"],
                    key=f"vehicle_select_{emp_id}"
                )

                vehicle_info = system.get_vehicle_info(selected_vehicle)
                if vehicle_info:
                    plate, model, brand, color, v_type, name, position, tag_id, photo = vehicle_info
                    st.success(f"🚘 Veículo selecionado: {plate}")
                    col_v1, col_v2 = st.columns(2)
                    with col_v1:
                        st.subheader("Informações do Veículo")
                        st.write(f"**Placa:** {plate}")
                        st.write(f"**Modelo/Marca:** {model} / {brand}")
                        st.write(f"**Cor:** {color}")
                        st.write(f"**Tipo:** {v_type}")
                    with col_v2:
                        st.subheader("Informações do Colaborador")
                        st.write(f"**Nome:** {name}")
                        st.write(f"**Cargo:** {position}")
                        st.write(f"**Tag ID:** {tag_id}")
                        if photo:
                            st.image(Image.open(io.BytesIO(photo)), caption="Foto do Colaborador", width=150)

                col_btn1, col_btn2, _ = st.columns([1, 1, 3])
                with col_btn1:
                    if st.button("✔ Liberar Acesso", key=f"approve_vehicle_{emp_id}", type="primary"):
                        success, message = system.register_access(selected_vehicle, True, notes)
                        if success:
                            st.success(message)
                            st.session_state.vehicle_info = None
                            st.session_state.employees = []
                            st.session_state.captured_plate = ""
                            st.session_state.form_key = str(uuid.uuid4())
                        else:
                            st.error(message)
                with col_btn2:
                    if st.button("✘ Reprovar Acesso", key=f"deny_vehicle_{emp_id}", type="secondary"):
                        success, message = system.register_access(selected_vehicle, False, notes)
                        if success:
                            st.success(message)
                            st.session_state.vehicle_info = None
                            st.session_state.employees = []
                            st.session_state.captured_plate = ""
                            st.session_state.form_key = str(uuid.uuid4())
                        else:
                            st.error(message)

                with st.expander("Ver últimos acessos"):
                    cursor = system.conn.cursor()
                    cursor.execute('''
                        SELECT data_hora, acesso_permitido, observacoes
                        FROM acessos a
                        JOIN veiculos v ON a.veiculo_id = v.id
                        WHERE v.placa = ?
                        ORDER BY a.data_hora DESC LIMIT 5
                    ''', (selected_vehicle,))
                    accesses = cursor.fetchall()
                    if accesses:
                        df = pd.DataFrame(
                            accesses,
                            columns=["Data/Hora", "Status", "Observações"],
                            index=range(1, len(accesses) + 1)
                        )
                        df["Status"] = df["Status"].apply(lambda x: "LIBERADO" if x else "NEGADO")
                        st.dataframe(df)
                    else:
                        st.info("Nenhum acesso registrado para este veículo.")
            else:
                st.info("Nenhum veículo associado a este colaborador.")

elif menu_option == "Cadastros":
    st.header("Cadastros")
    tab1, tab2, tab3 = st.tabs(["Cadastrar/Editar Colaborador", "Cadastrar/Editar Veículo", "Atualizar Foto do Colaborador"])

    with tab1:
        st.subheader("Pesquisar e Editar Colaborador")
        name_search = st.text_input("Digite o nome do colaborador para buscar (ex.: Marcelo):", key="employee_search")
        if st.button("Buscar Colaborador", key="search_employee"):
            if name_search:
                employees = system.get_employees_by_name(name_search)
                if employees:
                    employee_options = {f"{emp[1]} (ID:{emp[0]})": emp[0] for emp in employees}
                    selected_employee = st.selectbox("Selecione o colaborador", options=list(employee_options.keys()), key="select_employee")
                    employee_id = employee_options[selected_employee]
                    employee_data = system.get_employee_by_id(employee_id)
                    if employee_data:
                        st.session_state['selected_employee_data'] = employee_data
                    else:
                        st.error("Colaborador não encontrado.")
                else:
                    st.warning("Nenhum colaborador encontrado com este nome.")
            else:
                st.warning("Digite um nome para buscar.")

        if 'selected_employee_data' in st.session_state and st.session_state['selected_employee_data']:
            emp_id, emp_name, emp_position, emp_tag, emp_photo = st.session_state['selected_employee_data']
            with st.form("edit_employee_form"):
                st.subheader("Editar Colaborador")
                new_name = st.text_input("Nome Completo", value=emp_name, key=f"edit_name_{emp_id}")
                new_position = st.selectbox("Cargo", ["Diretor", "Gerente", "Coordenador", "Analista", "Assistente", "Outro"], index=["Diretor", "Gerente", "Coordenador", "Analista", "Assistente", "Outro"].index(emp_position) if emp_position in ["Diretor", "Gerente", "Coordenador", "Analista", "Assistente", "Outro"] else 5, key=f"edit_position_{emp_id}")
                new_tag = st.text_input("Número da Tag", value=emp_tag, key=f"edit_tag_{emp_id}")
                new_photo = st.file_uploader("Nova Foto do Colaborador", type=["jpg", "png", "jpeg"], key=f"edit_photo_{emp_id}")
                if emp_photo:
                    st.image(Image.open(io.BytesIO(emp_photo)), caption="Foto Atual", width=150)
                submitted = st.form_submit_button("Atualizar Colaborador")
                if submitted:
                    if new_name and new_position and new_tag:
                        photo_bytes = new_photo.read() if new_photo else emp_photo
                        success = system.update_employee(emp_id, new_name, new_position, new_tag, photo_bytes)
                        if success:
                            st.success("Colaborador atualizado com sucesso!")
                            st.session_state['selected_employee_data'] = None
                        else:
                            st.error("Falha ao atualizar colaborador.")
                    else:
                        st.error("Preencha todos os campos obrigatórios")

        st.subheader("Novo Colaborador")
        with st.form("employee_form"):
            emp_name = st.text_input("Nome Completo", key="new_employee_name")
            emp_position = st.selectbox("Cargo", ["Diretor", "Gerente", "Coordenador", "Analista", "Assistente", "Outro"], key="new_employee_position")
            emp_tag = st.text_input("Número da Tag", key="new_employee_tag")
            emp_photo = st.file_uploader("Foto do Colaborador", type=["jpg", "png", "jpeg"], key="new_employee_photo")
            submitted = st.form_submit_button("Cadastrar")
            if submitted:
                if emp_name and emp_position and emp_tag:
                    photo_bytes = None
                    if emp_photo:
                        photo_bytes = emp_photo.read()
                    employee_id = system.add_employee(emp_name, emp_position, emp_tag, photo_bytes)
                    if employee_id:
                        st.success("Colaborador cadastrado com sucesso!")
                else:
                    st.error("Preencha todos os campos obrigatórios")

    with tab2:
        st.subheader("Pesquisar e Editar Veículo")
        plate_search = st.text_input("Digite a placa do veículo (ex.: ABC1D23 ou ABC1234):", key="vehicle_search").upper()
        if st.button("Buscar Veículo", key="search_vehicle"):
            if plate_search:
                if system.validate_plate(plate_search):
                    vehicle_data = system.get_vehicle_by_plate(plate_search)
                    if vehicle_data:
                        st.session_state['selected_vehicle_data'] = vehicle_data
                    else:
                        st.error(f"⚠️ Veículo com placa {plate_search} não cadastrado")
                else:
                    st.warning("Formato de placa inválido. Use o padrão Mercosul (ex.: ABC1D23) ou antigo (ex.: ABC1234)")
            else:
                st.warning("Digite uma placa para buscar.")

        if 'selected_vehicle_data' in st.session_state and st.session_state['selected_vehicle_data']:
            vehicle_id, plate, model, brand, color, v_type, owner_id = st.session_state['selected_vehicle_data']
            cursor = system.conn.cursor()
            cursor.execute("SELECT id, nome FROM colaboradores")
            employees = cursor.fetchall()
            employee_options = {f"{e[1]} (ID:{e[0]})": e[0] for e in employees}
            with st.form("edit_vehicle_form"):
                st.subheader("Editar Veículo")
                new_plate = st.text_input("Placa (Mercosul ou antigo)", value=plate, key="edit_vehicle_plate")
                new_model = st.text_input("Modelo", value=model, key="edit_vehicle_model")
                new_brand = st.text_input("Marca", value=brand, key="edit_vehicle_brand")
                new_color = st.text_input("Cor", value=color, key="edit_vehicle_color")
                new_vehicle_type = st.selectbox("Tipo de Veículo", ["Diretor", "Gerente", "Funcionario", "Visitante"], index=["Diretor", "Gerente", "Funcionario", "Visitante"].index(v_type) if v_type in ["Diretor", "Gerente", "Funcionario", "Visitante"] else 0, key="edit_vehicle_type")
                new_owner = st.selectbox("Proprietário", options=list(employee_options.keys()), index=list(employee_options.values()).index(owner_id) if owner_id in employee_options.values() else 0, key="edit_vehicle_owner")
                submitted = st.form_submit_button("Atualizar Veículo")
                if submitted:
                    if new_plate and new_model and new_brand and new_color:
                        owner_id = employee_options[new_owner]
                        success, message = system.update_vehicle(vehicle_id, new_plate, new_model, new_brand, new_color, owner_id, new_vehicle_type)
                        if success:
                            st.success(message)
                            st.session_state['selected_vehicle_data'] = None
                        else:
                            st.error(message)
                    else:
                        st.error("Preencha todos os campos obrigatórios")

        st.subheader("Novo Veículo")
        cursor = system.conn.cursor()
        cursor.execute("SELECT id, nome FROM colaboradores")
        employees = cursor.fetchall()
        employee_options = {f"{e[1]} (ID:{e[0]})": e[0] for e in employees}
        with st.form("vehicle_form"):
            vehicle_plate = st.text_input("Placa (Mercosul ou antigo)", key="new_vehicle_plate").upper()
            vehicle_model = st.text_input("Modelo", key="new_vehicle_model")
            vehicle_brand = st.text_input("Marca", key="new_vehicle_brand")
            vehicle_color = st.text_input("Cor", key="new_vehicle_color")
            vehicle_type = st.selectbox("Tipo de Veículo", ["Diretor", "Gerente", "Funcionario", "Visitante"], key="new_vehicle_type")
            vehicle_owner = st.selectbox("Proprietário", options=list(employee_options.keys()), key="new_vehicle_owner")
            submitted = st.form_submit_button("Cadastrar")
            if submitted:
                if vehicle_plate and vehicle_model and vehicle_brand and vehicle_color:
                    owner_id = employee_options[vehicle_owner]
                    success, message = system.add_vehicle(
                        vehicle_plate, vehicle_model, vehicle_brand,
                        vehicle_color, owner_id, vehicle_type
                    )
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                else:
                    st.error("Preencha todos os campos obrigatórios")

    with tab3:
        st.subheader("Atualizar Foto do Colaborador")
        name_input = st.text_input("Digite o nome do colaborador (ex.: Henri):")
        if st.button("Buscar Colaborador"):
            if name_input:
                employees = system.get_employees_by_name(name_input)
                if employees:
                    st.subheader("Colaboradores Encontrados")
                    employee_options = {f"{emp[1]} (ID:{emp[0]})": emp[0] for emp in employees}
                    selected_employee = st.selectbox("Selecione o colaborador", options=list(employee_options.keys()))
                    selected_photo = st.file_uploader("Nova foto do colaborador", type=["jpg", "png", "jpeg"], key="update_photo")
                    cursor = system.conn.cursor()
                    cursor.execute("SELECT foto FROM colaboradores WHERE id = ?", (employee_options[selected_employee],))
                    current_photo = cursor.fetchone()
                    if current_photo and current_photo[0]:
                        st.image(Image.open(io.BytesIO(current_photo[0])), caption="Foto Atual", width=150)
                    if st.button("Atualizar Foto"):
                        if selected_photo:
                            photo_bytes = selected_photo.read()
                            if system.update_employee_photo(employee_options[selected_employee], photo_bytes):
                                st.success("Foto atualizada com sucesso!")
                            else:
                                st.error("Falha ao atualizar a foto.")
                        else:
                            st.warning("Por favor, faça upload de uma nova foto.")
                else:
                    st.warning("Nenhum colaborador encontrado com este nome.")
            else:
                st.warning("Digite um nome para buscar.")

elif menu_option == "Relatórios":
    st.header("Relatórios de Acesso")
    date_range = st.date_input("Selecione o período", [])
    if st.button("Gerar Relatório"):
        cursor = system.conn.cursor()
        query = '''
            SELECT a.data_hora, v.placa, v.modelo, v.marca, c.nome, c.cargo,
                   CASE WHEN a.acesso_permitido THEN 'LIBERADO' ELSE 'NEGADO' END as status
            FROM acessos a
            JOIN veiculos v ON a.veiculo_id = v.id
            LEFT JOIN colaboradores c ON v.colaborador_id = c.id
            ORDER BY a.data_hora DESC
        '''
        cursor.execute(query)
        data = cursor.fetchall()
        if data:
            df = pd.DataFrame(data, columns=["Data/Hora", "Placa", "Modelo", "Marca", "Proprietário", "Cargo", "Status"])
            st.dataframe(df)
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "Baixar como CSV",
                data=csv,
                file_name="relatorio_acessos.csv",
                mime="text/csv"
            )
        else:
            st.info("Nenhum registro de acesso encontrado")



