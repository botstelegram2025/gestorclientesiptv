import sqlite3
from datetime import datetime, timedelta

DB_NAME = "clientes.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT NOT NULL UNIQUE,
            plano INTEGER NOT NULL,
            duracao INTEGER NOT NULL,
            vencimento TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def adicionar_cliente(nome, telefone, plano, duracao):
    vencimento = (datetime.now() + timedelta(days=30 * duracao)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        INSERT OR REPLACE INTO clientes (nome, telefone, plano, duracao, vencimento)
        VALUES (?, ?, ?, ?, ?)
    ''', (nome, telefone, plano, duracao, vencimento))
    conn.commit()
    conn.close()
    return vencimento

def listar_clientes():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT nome, telefone, plano, duracao, vencimento FROM clientes")
    rows = cur.fetchall()
    conn.close()
    return rows

def clientes_proximos_vencimento(dias=3):
    hoje = datetime.now()
    limite = hoje + timedelta(days=dias)
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT nome, telefone, vencimento FROM clientes")
    rows = cur.fetchall()
    conn.close()
    alertas = []
    for nome, telefone, vencimento in rows:
        venc = datetime.strptime(vencimento, "%Y-%m-%d")
        if hoje <= venc <= limite:
            alertas.append((nome, telefone, vencimento))
    return alertas
