import cv2
import sqlite3
from datetime import datetime
import re
import easyocr
import pandas as pd

class PlacaReaderApp:
    def __init__(self):
        # Configurações iniciais
        self.conn = sqlite3.connect('placas_liberadas.db')
        self.criar_banco_dados()
        self.reader = easyocr.Reader(['en'], gpu=False)  # Inicializa EasyOCR

    def criar_banco_dados(self):
        # Criando tabela de placas liberadas
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS placas_liberadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                placa TEXT UNIQUE,
                proprietario TEXT,
                data_cadastro TEXT,
                observacoes TEXT
            )
        ''')
        # Criando tabela de histórico de acessos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS historico_acessos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                placa TEXT,
                data_hora TEXT,
                liberado BOOLEAN,
                mensagem TEXT
            )
        ''')
        self.conn.commit()

    def validar_placa(self, placa):
        # Valida formato Mercosul: AAA0A00
        padrao_mercosul = r'^[A-Z]{3}[0-9][A-Z][0-9]{2}$'
        return bool(re.match(padrao_mercosul, placa))

    def ler_placa(self, imagem_path):
        # Pré-processamento da imagem
        img = cv2.imread(imagem_path)
        if img is None:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

        # Reconhecimento com EasyOCR
        resultados = self.reader.readtext(thresh)
        for (bbox, texto, prob) in resultados:
            placa = ''.join(e for e in texto if e.isalnum()).upper()
            if self.validar_placa(placa):
                return placa
        return None

    def verificar_placa(self, placa):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM placas_liberadas WHERE placa=?", (placa,))
        return cursor.fetchone() is not None

    def adicionar_placa_liberada(self, placa, proprietario, observacoes=''):
        if not self.validar_placa(placa):
            return False, "Placa fora do padrão Mercosul"
        try:
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO placas_liberadas (placa, proprietario, data_cadastro, observacoes) VALUES (?, ?, ?, ?)",
                          (placa, proprietario, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), observacoes))
            self.conn.commit()
            return True, "Placa cadastrada com sucesso"
        except sqlite3.IntegrityError:
            return False, "Placa já cadastrada"

    def registrar_acesso(self, resultado):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO historico_acessos (placa, data_hora, liberado, mensagem) VALUES (?, ?, ?, ?)",
                      (resultado.get('placa', ''), datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                       resultado.get('liberado', False), resultado.get('mensagem', '')))
        self.conn.commit()

    def processar_entrada_veiculo(self, imagem_path):
        placa = self.ler_placa(imagem_path)
        if placa:
            liberado = self.verificar_placa(placa)
            resultado = {
                'placa': placa,
                'liberado': liberado,
                'mensagem': 'Acesso LIBERADO' if liberado else 'Acesso NEGADO'
            }
        else:
            resultado = {'erro': 'Placa não reconhecida'}
        self.registrar_acesso(resultado)
        return resultado

    def processar_camera_tempo_real(self):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return {'erro': 'Não foi possível acessar a câmera'}

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Salva frame temporário para processamento
            cv2.imwrite('temp_frame.jpg', frame)
            resultado = self.processar_entrada_veiculo('temp_frame.jpg')

            # Exibe o resultado no frame
            texto = resultado.get('mensagem', resultado.get('erro', ''))
            cor = (0, 255, 0) if resultado.get('liberado', False) else (0, 0, 255)
            cv2.putText(frame, texto, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, cor, 2)
            cv2.imshow('Controle de Acesso', frame)

            # Sai com a tecla 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()
        return resultado

    def gerar_relatorio_csv(self, arquivo_saida='relatorio_acessos.csv'):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM historico_acessos")
        dados = cursor.fetchall()
        colunas = ['ID', 'Placa', 'Data/Hora', 'Liberado', 'Mensagem']
        df = pd.DataFrame(dados, columns=colunas)
        df.to_csv(arquivo_saida, index=False)
        return f"Relatório salvo em {arquivo_saida}"

if __name__ == "__main__":
    app = PlacaReaderApp()
    # Adiciona placas de exemplo
    app.adicionar_placa_liberada("ABC1D23", "João Silva", "Apartamento 101")
    app.adicionar_placa_liberada("XYZ9K87", "Maria Souza", "Apartamento 205")
    # Testa com uma imagem
    resultado = app.processar_entrada_veiculo("foto_placa.jpg")
    print(resultado)