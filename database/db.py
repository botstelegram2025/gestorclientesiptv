# database/db.py

import aiosqlite

DB_PATH = "clientes.db"

async def criar_tabelas():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT,
                telefone TEXT UNIQUE,
                pacote TEXT,
                plano REAL,
                vencimento TEXT,
                chat_id INTEGER
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS renovacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telefone TEXT,
                data_renovacao TEXT,
                novo_vencimento TEXT,
                pacote TEXT,
                plano REAL
            )
        ''')
        await db.commit()

async def get_db():
    return await aiosqlite.connect(DB_PATH)
