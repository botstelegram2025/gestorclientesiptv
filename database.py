"""
Gerenciador do banco de dados SQLite
"""

import sqlite3
import logging
from datetime import datetime
import pytz
from typing import List, Dict, Optional, Tuple
from config import DB_PATH

# Configurar timezone brasileiro
TIMEZONE_BR = pytz.timezone('America/Sao_Paulo')

def agora_br():
    """Retorna datetime atual no fuso horário de Brasília"""
    return datetime.now(TIMEZONE_BR)

logger = logging.getLogger(__name__)

def criar_tabela():
    """Cria as tabelas necessárias no banco de dados"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        # Tabela de clientes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                telefone TEXT UNIQUE NOT NULL,
                pacote TEXT NOT NULL,
                plano REAL NOT NULL,
                vencimento TEXT NOT NULL,
                servidor TEXT NOT NULL,
                chat_id INTEGER,
                data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,
                ativo BOOLEAN DEFAULT 1
            )
        ''')
        
        # Tabela de renovações
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS renovacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telefone TEXT NOT NULL,
                data_renovacao TEXT NOT NULL,
                novo_vencimento TEXT NOT NULL,
                pacote_anterior TEXT,
                pacote_novo TEXT,
                plano_anterior REAL,
                plano_novo REAL,
                observacoes TEXT
            )
        ''')
        
        # Tabela de configurações do admin
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS configuracoes (
                id INTEGER PRIMARY KEY,
                pix_key TEXT,
                empresa_nome TEXT,
                contato_suporte TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabela de log de mensagens enviadas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mensagens_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telefone TEXT NOT NULL,
                nome_cliente TEXT,
                tipo_mensagem TEXT NOT NULL,
                conteudo_mensagem TEXT,
                data_envio TEXT NOT NULL,
                status TEXT NOT NULL,
                erro_detalhes TEXT
            )
        ''')
        
        # Tabela de templates personalizáveis
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT UNIQUE NOT NULL,
                titulo TEXT NOT NULL,
                conteudo TEXT NOT NULL,
                tipo TEXT NOT NULL,
                ativo BOOLEAN DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        logger.info("Tabelas criadas com sucesso")
        
    except Exception as e:
        logger.error(f"Erro ao criar tabelas: {e}")
        conn.rollback()
    finally:
        conn.close()

class DatabaseManager:
    """Classe para gerenciar operações do banco de dados"""
    
    def __init__(self):
        self.db_path = DB_PATH
    
    def get_connection(self):
        """Retorna uma conexão com o banco de dados"""
        return sqlite3.connect(self.db_path, check_same_thread=False)
    
    def executar_query(self, query: str, params: tuple = ()) -> List[Dict]:
        """Executa uma query e retorna os resultados"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(query, params)
            columns = [description[0] for description in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return results
        except Exception as e:
            logger.error(f"Erro ao executar query: {e}")
            return []
        finally:
            conn.close()
    
    def executar_comando(self, query: str, params: tuple = ()) -> bool:
        """Executa um comando (INSERT, UPDATE, DELETE)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(query, params)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Erro ao executar comando: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    # Métodos para clientes
    def adicionar_cliente(self, nome: str, telefone: str, pacote: str, 
                         plano: float, vencimento: str, servidor: str, 
                         chat_id: Optional[int] = None) -> bool:
        """Adiciona um novo cliente"""
        query = '''
            INSERT INTO clientes (nome, telefone, pacote, plano, vencimento, servidor, chat_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        '''
        return self.executar_comando(query, (nome, telefone, pacote, plano, vencimento, servidor, chat_id))
    
    def listar_clientes(self, ativo_apenas: bool = True) -> List[Dict]:
        """Lista todos os clientes"""
        query = "SELECT * FROM clientes"
        if ativo_apenas:
            query += " WHERE ativo = 1"
        query += " ORDER BY nome"
        return self.executar_query(query)
    
    def buscar_cliente_por_telefone(self, telefone: str) -> Optional[Dict]:
        """Busca um cliente pelo telefone"""
        query = "SELECT * FROM clientes WHERE telefone = ?"
        results = self.executar_query(query, (telefone,))
        return results[0] if results else None
    
    def atualizar_cliente(self, cliente_id: int, campo: str, valor) -> bool:
        """Atualiza um campo específico de um cliente pelo ID"""
        # Mapear nomes de campos do bot para nomes do banco
        mapeamento_campos = {
            'nome': 'nome',
            'telefone': 'telefone', 
            'pacote': 'pacote',
            'valor': 'plano',  # valor -> plano no banco
            'servidor': 'servidor',
            'vencimento': 'vencimento'
        }
        
        if campo not in mapeamento_campos:
            return False
            
        campo_db = mapeamento_campos[campo]
        query = f"UPDATE clientes SET {campo_db} = ? WHERE id = ?"
        return self.executar_comando(query, (valor, cliente_id))
    
    def atualizar_cliente_completo(self, cliente_id: int, nome: str, telefone: str, 
                         pacote: str, plano: float, servidor: str, vencimento: str) -> bool:
        """Atualiza todos os dados de um cliente pelo ID"""
        query = '''
            UPDATE clientes 
            SET nome = ?, telefone = ?, pacote = ?, plano = ?, servidor = ?, vencimento = ?
            WHERE id = ?
        '''
        return self.executar_comando(query, (nome, telefone, pacote, plano, servidor, vencimento, cliente_id))
    
    def atualizar_campo_cliente(self, telefone: str, campo: str, valor) -> bool:
        """Atualiza um campo específico do cliente"""
        query = f"UPDATE clientes SET {campo} = ? WHERE telefone = ?"
        return self.executar_comando(query, (valor, telefone))
    
    def excluir_cliente(self, cliente_id: int) -> bool:
        """Remove um cliente permanentemente pelo ID"""
        query = "DELETE FROM clientes WHERE id = ?"
        return self.executar_comando(query, (cliente_id,))
    
    def deletar_cliente(self, telefone: str) -> bool:
        """Remove um cliente (marca como inativo)"""
        query = "UPDATE clientes SET ativo = 0 WHERE telefone = ?"
        return self.executar_comando(query, (telefone,))
    
    def clientes_vencendo(self, dias: int) -> List[Dict]:
        """Busca clientes que vencem em X dias"""
        query = '''
            SELECT * FROM clientes 
            WHERE ativo = 1 
            AND date(vencimento) = date('now', '+{} days')
        '''.format(dias)
        return self.executar_query(query)
    
    def clientes_vencidos(self) -> List[Dict]:
        """Busca clientes com vencimento em atraso"""
        query = '''
            SELECT * FROM clientes 
            WHERE ativo = 1 
            AND date(vencimento) < date('now')
        '''
        return self.executar_query(query)
    
    # Métodos para renovações
    def registrar_renovacao(self, cliente_id: int, dias_adicionados: int, valor: float,
                           observacoes: str = "") -> bool:
        """Registra uma renovação por ID do cliente"""
        # Buscar dados atuais do cliente
        clientes = self.listar_clientes(False)  # Busca todos, incluindo inativos
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)
        if not cliente:
            return False
        
        query = '''
            INSERT INTO renovacoes 
            (telefone, data_renovacao, novo_vencimento, pacote_anterior, 
             pacote_novo, plano_anterior, plano_novo, observacoes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        '''
        
        # Calcular novo vencimento
        from datetime import datetime, timedelta
        data_renovacao = agora_br().replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
        vencimento_atual = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')
        if vencimento_atual < agora_br().replace(tzinfo=None):
            novo_vencimento = agora_br().replace(tzinfo=None) + timedelta(days=dias_adicionados)
        else:
            novo_vencimento = vencimento_atual + timedelta(days=dias_adicionados)
        
        return self.executar_comando(query, (
            cliente['telefone'], data_renovacao, novo_vencimento.strftime('%Y-%m-%d'),
            cliente['pacote'], cliente['pacote'],  # Mantém o mesmo pacote
            cliente['plano'], valor,
            f"Renovação por {dias_adicionados} dias. {observacoes}"
        ))
    
    def registrar_renovacao_telefone(self, telefone: str, novo_vencimento: str, 
                           pacote_novo: str, plano_novo: float,
                           observacoes: str = "") -> bool:
        """Registra uma renovação (método legado)"""
        # Buscar dados atuais do cliente
        cliente = self.buscar_cliente_por_telefone(telefone)
        if not cliente:
            return False
        
        query = '''
            INSERT INTO renovacoes 
            (telefone, data_renovacao, novo_vencimento, pacote_anterior, 
             pacote_novo, plano_anterior, plano_novo, observacoes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        '''
        
        data_renovacao = agora_br().replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
        
        return self.executar_comando(query, (
            telefone, data_renovacao, novo_vencimento,
            cliente['pacote'], pacote_novo,
            cliente['plano'], plano_novo,
            observacoes
        ))
    
    def historico_renovacoes(self, telefone: Optional[str] = None) -> List[Dict]:
        """Retorna o histórico de renovações"""
        if telefone:
            query = "SELECT * FROM renovacoes WHERE telefone = ? ORDER BY data_renovacao DESC"
            return self.executar_query(query, (telefone,))
        else:
            query = "SELECT * FROM renovacoes ORDER BY data_renovacao DESC"
            return self.executar_query(query)
    
    # Métodos para configurações
    def get_configuracoes(self) -> Optional[Dict]:
        """Busca as configurações do admin"""
        query = "SELECT * FROM configuracoes WHERE id = 1"
        results = self.executar_query(query)
        return results[0] if results else None
    
    def salvar_configuracoes(self, pix_key: str, empresa_nome: str, contato_suporte: str) -> bool:
        """Salva as configurações do admin"""
        query = '''
            INSERT OR REPLACE INTO configuracoes 
            (id, pix_key, empresa_nome, contato_suporte, updated_at) 
            VALUES (1, ?, ?, ?, ?)
        '''
        timestamp = agora_br().replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
        return self.executar_comando(query, (pix_key, empresa_nome, contato_suporte, timestamp))
    
    # Métodos para log de mensagens
    def log_mensagem(self, telefone: str, nome_cliente: str, tipo_mensagem: str,
                    conteudo: str, status: str, erro_detalhes: str = "") -> bool:
        """Registra o envio de uma mensagem"""
        query = '''
            INSERT INTO mensagens_log 
            (telefone, nome_cliente, tipo_mensagem, conteudo_mensagem, 
             data_envio, status, erro_detalhes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        '''
        
        data_envio = agora_br().replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
        
        return self.executar_comando(query, (
            telefone, nome_cliente, tipo_mensagem, conteudo,
            data_envio, status, erro_detalhes
        ))
    
    def estatisticas_mensagens(self) -> Dict:
        """Retorna estatísticas de mensagens enviadas"""
        stats = {}
        
        # Total de mensagens
        query = "SELECT COUNT(*) as total FROM mensagens_log"
        result = self.executar_query(query)
        stats['total'] = result[0]['total'] if result else 0
        
        # Mensagens por status
        query = "SELECT status, COUNT(*) as count FROM mensagens_log GROUP BY status"
        results = self.executar_query(query)
        stats['por_status'] = {row['status']: row['count'] for row in results}
        
        # Mensagens por tipo
        query = "SELECT tipo_mensagem, COUNT(*) as count FROM mensagens_log GROUP BY tipo_mensagem"
        results = self.executar_query(query)
        stats['por_tipo'] = {row['tipo_mensagem']: row['count'] for row in results}
        
        return stats
    
    # Métodos para templates
    def salvar_template(self, nome: str, titulo: str, conteudo: str, tipo: str) -> bool:
        """Salva um template personalizado"""
        query = '''
            INSERT OR REPLACE INTO templates (nome, titulo, conteudo, tipo)
            VALUES (?, ?, ?, ?)
        '''
        return self.executar_comando(query, (nome, titulo, conteudo, tipo))
    
    def buscar_template(self, nome: str) -> Optional[Dict]:
        """Busca um template pelo nome"""
        query = "SELECT * FROM templates WHERE nome = ? AND ativo = 1"
        results = self.executar_query(query, (nome,))
        return results[0] if results else None
    
    def listar_templates(self) -> List[Dict]:
        """Lista todos os templates ativos"""
        query = "SELECT * FROM templates WHERE ativo = 1 ORDER BY nome"
        return self.executar_query(query)
