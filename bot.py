import os
import csv
import re
import sqlite3
import tempfile
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler,
    filters, ConversationHandler, CallbackQueryHandler, JobQueue
)

TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "clientes.db"

ADMIN_CHAT_ID = 123456789  # <<< SUBSTITUA PELO SEU CHAT_ID REAL

ADD_NAME, ADD_PHONE, ADD_PACOTE, ADD_PLANO, ESCOLHER_SERVIDOR = range(5)
ESCOLHER_MENSAGEM = 5

PACOTES = ["1 mês", "3 meses", "6 meses", "1 ano"]
PLANOS = [30, 35, 40, 45, 60, 65, 70, 90, 110, 135]
SERVIDORES = [
    ("📺 Fast Play", "Fast Play"),
    ("🎯 Genial TV", "Genial TV"),
    ("📡 EITV", "EITV"),
    ("👑 Gold Play", "Gold Play"),
    ("💎 Slim TV", "Slim TV"),
    ("📶 UniTV", "UniTV"),
    ("🎬 Live21", "Live21"),
    ("📲 Ztech Play", "Ztech Play"),
    ("🛰️ XServer Play", "XServer Play")
]

mensagens_padrao = {
    "promo": "📢 Olá {nome}, confira nossa promoção especial!",
    "lembrete": "⏰ Olá {nome}, só passando para lembrar do seu compromisso amanhã.",
    "vencimento_hoje": "⚠️ Olá {nome}, seu plano vence hoje!",
    "vencido": "❌ Olá {nome}, seu plano está vencido desde ontem."
}

def teclado_principal():
    teclado = [
        ["➕ Adicionar Cliente", "📋 Listar Clientes"],
        ["🔄 Renovar Plano", "📊 Relatório"],
        ["📤 Exportar Dados", "❌ Cancelar Operação"]
    ]
    return ReplyKeyboardMarkup(teclado, resize_keyboard=True)

def criar_tabela():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            telefone TEXT UNIQUE,
            pacote TEXT,
            plano REAL,
            servidor TEXT,
            vencimento TEXT,
            chat_id INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS renovacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telefone TEXT,
            data_renovacao TEXT,
            novo_vencimento TEXT,
            pacote TEXT,
            plano REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chave_pix TEXT
        )
    ''')
    conn.commit()
    conn.close()

def telefone_valido(telefone):
    return re.match(r'^\d{10,11}$', telefone)

def get_duracao_meses(pacote):
    mapa = {"1 mês": 1, "3 meses": 3, "6 meses": 6, "1 ano": 12}
    return mapa.get(pacote, 1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bem-vindo ao Bot de Gestão de Clientes!\n\n"
        "Escolha uma opção no menu abaixo ou digite um comando.",
        reply_markup=teclado_principal()
    )

async def cadastrar_pix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Acesso negado.")
        return
    if not context.args:
        await update.message.reply_text("ℹ️ Use: /pix SUACHAVEPIX")
        return

    chave = " ".join(context.args)

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM configuracoes")
    cursor.execute("INSERT INTO configuracoes (chave_pix) VALUES (?)", (chave,))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Chave Pix cadastrada: `{chave}`", parse_mode="Markdown")

async def enviar_lembretes_job(context: ContextTypes.DEFAULT_TYPE):
    bot = context.bot

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()

    hoje = datetime.now().date()
    datas = {
        "vencido": (hoje - timedelta(days=1)),
        "hoje": hoje,
        "1_dia": (hoje + timedelta(days=1)),
        "2_dias": (hoje + timedelta(days=2)),
    }

    cursor.execute("SELECT chave_pix FROM configuracoes ORDER BY id DESC LIMIT 1")
    chave_row = cursor.fetchone()
    chave_pix = chave_row[0] if chave_row else "Não cadastrada"

    mensagens = {
        "2_dias": "📅 Olá {nome}, seu plano de R$ {plano:.2f} vence em 2 dias, no dia {venc}. \n💳 Chave Pix: {pix}",
        "1_dia":  "⏳ Olá {nome}, falta 1 dia para o vencimento do seu plano (R$ {plano:.2f}) no dia {venc}. \n💳 Chave Pix: {pix}",
        "hoje":   "⚠️ Olá {nome}, seu plano vence hoje! Valor: R$ {plano:.2f}.\n💳 Chave Pix: {pix}",
        "vencido":"❌ Olá {nome}, seu plano venceu ontem ({venc}). Valor: R$ {plano:.2f}. \n💳 Chave Pix: {pix}",
    }

    for tipo, data_alvo in datas.items():
        cursor.execute("SELECT nome, telefone, plano, vencimento FROM clientes WHERE vencimento = ?", (data_alvo.strftime("%Y-%m-%d"),))
        for nome, telefone, plano, vencimento in cursor.fetchall():
            texto = mensagens[tipo].format(nome=nome, plano=plano, venc=vencimento, pix=chave_pix)
            await bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"💬 [{nome}](https://wa.me/55{telefone}?text={texto.replace(' ', '%20').replace(chr(10), '%0A')})",
                parse_mode="Markdown",
                disable_web_page_preview=True
            )

    conn.close()

async def enviar_lembretes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Acesso negado.")
        return
    await enviar_lembretes_job(context)
    await update.message.reply_text("✅ Mensagens de lembrete verificadas e enviadas.")

def main():
    criar_tabela()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pix", cadastrar_pix))
    app.add_handler(CommandHandler("lembretes", enviar_lembretes))

    # Agendamento automático todos os dias às 08:00
    app.job_queue.run_daily(enviar_lembretes_job, time=datetime.strptime("08:00", "%H:%M").time())

    app.run_polling()

if __name__ == '__main__':
    main()
