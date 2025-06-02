import streamlit as st
import sqlite3
from datetime import datetime
import re
import pandas as pd
from PIL import Image
import io

# Configuração inicial do Streamlit
st.set_page_config(page_title="Controle de Acesso Carbon", layout="wide", page_icon="🚗")

class VehicleAccessSystem:
    def __init__(self):
        self.conn = sqlite3.connect('carbon_access.db')
        self.create_database()

    def create_database(self):
        cursor = self.conn.cursor()
        
        # Tabela de colaboradores
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS colaboradores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                cargo TEXT NOT NULL,
                tag_id TEXT UNIQUE,
                foto BLOB,
                ativo BOOLEAN DEFAULT 1
            )
        ''')
        
        # Tabela de veículos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS veiculos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                placa TEXT UNIQUE NOT NULL,
                modelo TEXT,
                marca TEXT,
                cor TEXT,
                colaborador_id INTEGER,
                tipo_veiculo TEXT CHECK(tipo_veiculo IN ('Diretor', 'Gerente', 'Funcionario', 'Visitante')),
                FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id)
            )
        ''')
        
        # Tabela de histórico de acessos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS acessos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                veiculo_id INTEGER,
                data_hora TEXT NOT NULL,
                acesso_permitido BOOLEAN,
                observacoes TEXT,
                FOREIGN KEY (veiculo_id) REFERENCES veiculos(id)
            )
        ''')
        
        self.conn.commit()

    def validate_plate(self, plate):
        # Remove espaços e hífens, converte para maiúsculas
        plate = plate.replace(" ", "").replace("-", "").upper()
        # Padrão Mercosul: AAA0A00 (3 letras, 1 número, 1 letra ou número, 2 números)
        # Padrão antigo: AAA0000 (3 letras, 4 números)
        mercosul_pattern = r'^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$'
        old_pattern = r'^[A-Z]{3}[0-9]{4}$'
        return bool(re.match(mercosul_pattern, plate) or re.match(old_pattern, plate))

    def get_vehicle_info(self, plate):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT v.placa, v.modelo, v.marca, v.cor, v.tipo_veiculo,
                   c.nome, c.cargo, c.tag_id, c.foto
            FROM veiculos v
            JOIN colaboradores c ON v.colaborador_id = c.id
            WHERE v.placa = ?
        ''', (plate,))
        return cursor.fetchone()

    def get_employees_by_name(self, name):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, nome, cargo, tag_id, foto
            FROM colaboradores
            WHERE nome LIKE ? AND ativo = 1
        ''', (f'%{name}%',))
        return cursor.fetchall()

    def get_vehicles_by_employee(self, employee_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT placa, modelo, marca, cor, tipo_veiculo
            FROM veiculos
            WHERE colaborador_id = ?
        ''', (employee_id,))
        return cursor.fetchall()

    def register_access(self, plate, allowed, notes=""):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM veiculos WHERE placa = ?", (plate,))
        vehicle_id = cursor.fetchone()
        
        if vehicle_id:
            cursor.execute('''
                INSERT INTO acessos (veiculo_id, data_hora, acesso_permitido, observacoes)
                VALUES (?, ?, ?, ?)
            ''', (vehicle_id[0], datetime.now().strftime("%Y-%m-%d %H:%M:%S"), allowed, notes))
            self.conn.commit()
            return True
        return False

    def add_employee(self, name, position, tag_id, photo):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO colaboradores (nome, cargo, tag_id, foto)
                VALUES (?, ?, ?, ?)
            ''', (name, position, tag_id, photo))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            st.error("Tag ID já cadastrada")
            return None

    def update_employee_photo(self, employee_id, photo):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE colaboradores
                SET foto = ?
                WHERE id = ?
            ''', (photo, employee_id))
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            st.error(f"Erro ao atualizar foto: {str(e)}")
            return False

    def add_vehicle(self, plate, model, brand, color, employee_id, vehicle_type):
        if not self.validate_plate(plate):
            return False, "Placa inválida (use padrão Mercosul AAA0A00 ou antigo AAA0000)"
        
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO veiculos (placa, modelo, marca, cor, colaborador_id, tipo_veiculo)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (plate.upper(), model, brand, color, employee_id, vehicle_type))
            self.conn.commit()
            return True, "Veículo cadastrado com sucesso"
        except sqlite3.IntegrityError:
            return False, "Placa já cadastrada"

# Interface Streamlit
system = VehicleAccessSystem()

st.title("🚗 Sistema de Controle de Acesso - Carbon")

# Menu lateral
menu_option = st.sidebar.selectbox("Menu", ["Controle de Acesso", "Cadastros", "Relatórios"])

if menu_option == "Controle de Acesso":
    st.header("Registro de Acesso")
    
    tab1, tab2 = st.tabs(["Busca por Placa", "Busca por Nome"])
    
    with tab1:
        plate_input = st.text_input("Digite a placa do veículo (ex.: ABC1D23 ou ABC1234):").upper()
        notes_plate = st.text_area("Observações (opcional):", key="notes_plate")
        
        if st.button("Consultar Placa"):
            if plate_input and system.validate_plate(plate_input):
                vehicle_info = system.get_vehicle_info(plate_input)
                if vehicle_info:
                    plate, model, brand, color, v_type, name, position, tag_id, photo = vehicle_info
                    
                    st.success("🚘 Veículo encontrado - Acesso LIBERADO")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader("Informações do Veículo")
                        st.write(f"**Placa:** {plate}")
                        st.write(f"**Modelo/Marca:** {model} / {brand}")
                        st.write(f"**Cor:** {color}")
                        st.write(f"**Tipo:** {v_type}")
                    
                    with col2:
                        st.subheader("Informações do Colaborador")
                        st.write(f"**Nome:** {name}")
                        st.write(f"**Cargo:** {position}")
                        st.write(f"**Tag ID:** {tag_id}")
                        
                        if photo:
                            st.image(Image.open(io.BytesIO(photo)), caption="Foto do Colaborador", width=150)
                    
                    system.register_access(plate, True, notes_plate)
                    
                    # Exibir últimos acessos
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
                        st.subheader("Últimos Acessos")
                        df = pd.DataFrame(
                            accesses,
                            columns=["Data/Hora", "Status", "Observações"],
                            index=range(1, len(accesses) + 1)
                        )
                        df["Status"] = df["Status"].apply(lambda x: "LIBERADO" if x else "NEGADO")
                        st.dataframe(df)
                else:
                    st.error("⚠️ Veículo não cadastrado - Acesso NEGADO")
                    system.register_access(plate_input, False, notes_plate)
            else:
                st.warning("Formato de placa inválido. Use o padrão Mercosul (ex.: ABC1D23) ou antigo (ex.: ABC1234)")
    
    with tab2:
        name_input = st.text_input("Digite o nome do colaborador (ex.: Marcelo):")
        notes_name = st.text_area("Observações (opcional):", key="notes_name")
        
        if st.button("Buscar Colaborador"):
            if name_input:
                employees = system.get_employees_by_name(name_input)
                if employees:
                    st.subheader("Colaboradores Encontrados")
                    for emp in employees:
                        emp_id, emp_name, emp_position, emp_tag, emp_photo = emp
                        st.write("---")
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            st.write(f"**Nome:** {emp_name}")
                            st.write(f"**Cargo:** {emp_position}")
                            st.write(f"**Tag ID:** {emp_tag}")
                        
                        with col2:
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
                            if st.button("Registrar Acesso", key=f"register_access_{emp_id}"):
                                system.register_access(selected_vehicle, True, notes_name)
                                st.success(f"Acesso LIBERADO para veículo {selected_vehicle}")
                        else:
                            st.info("Nenhum veículo associado a este colaborador.")
                else:
                    st.warning("Nenhum colaborador encontrado com este nome.")
            else:
                st.warning("Digite um nome para buscar.")

elif menu_option == "Cadastros":
    st.header("Cadastros")
    
    tab1, tab2, tab3 = st.tabs(["Cadastrar Colaborador", "Cadastrar Veículo", "Atualizar Foto do Colaborador"])
    
    with tab1:
        with st.form("employee_form"):
            st.subheader("Novo Colaborador")
            emp_name = st.text_input("Nome Completo")
            emp_position = st.selectbox("Cargo", ["Sócio","Diretor", "Gerente", "Coordenador", "Analista", "Assistente", "Outro"])
            emp_tag = st.text_input("Número da Tag")
            emp_photo = st.file_uploader("Foto do Colaborador", type=["jpg", "png", "jpeg"])
            
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
        cursor = system.conn.cursor()
        cursor.execute("SELECT id, nome FROM colaboradores")
        employees = cursor.fetchall()
        employee_options = {f"{e[1]} (ID:{e[0]})": e[0] for e in employees}
        
        with st.form("vehicle_form"):
            st.subheader("Novo Veículo")
            vehicle_plate = st.text_input("Placa (Mercosul ou antigo)").upper()
            vehicle_model = st.text_input("Modelo")
            vehicle_brand = st.text_input("Marca")
            vehicle_color = st.text_input("Cor")
            vehicle_type = st.selectbox("Tipo de Veículo", ["Diretor", "Gerente", "Funcionario", "Visitante"])
            vehicle_owner = st.selectbox("Proprietário", options=list(employee_options.keys()))
            
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
                    
                    # Exibir foto atual
                    selected_emp_id = employee_options[selected_employee]
                    cursor = system.conn.cursor()
                    cursor.execute("SELECT foto FROM colaboradores WHERE id = ?", (selected_emp_id,))
                    current_photo = cursor.fetchone()[0]
                    if current_photo:
                        st.image(Image.open(io.BytesIO(current_photo)), caption="Foto Atual", width=150)
                    
                    if st.button("Atualizar Foto"):
                        if selected_photo:
                            photo_bytes = selected_photo.read()
                            if system.update_employee_photo(selected_emp_id, photo_bytes):
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
            