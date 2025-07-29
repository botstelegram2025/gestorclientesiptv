import os
import re
import sqlite3
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import (
    Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler,
    filters, ConversationHandler
)

TOKEN = os.getenv("BOT_TOKEN")  # Configure sua variável de ambiente
DB_PATH = "clientes.db"

# Estados da conversa
ADD_NAME, ADD_PHONE, ADD_PACOTE, ADD_PLANO = range(4)

PACOTES = ["1 mês", "3 meses", "6 meses", "1 ano"]
PLANOS = [30, 35, 40, 45, 60, 65, 70, 90, 110, 135]

scheduler = BackgroundScheduler()
scheduler.start()

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
            vencimento TEXT
        )
    ''')
    conn.commit()
    conn.close()

def telefone_valido(telefone):
    return re.match(r'^\d{10,11}$', telefone)

def get_duracao_meses(pacote):
    mapa = {"1 mês": 1, "3 meses": 3, "6 meses": 6, "1 ano": 12}
    return mapa.get(pacote, 1)

def teclado_principal():
    teclado = [
        ["➕ Adicionar Cliente"]
    ]
    return ReplyKeyboardMarkup(teclado, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bem-vindo ao Bot de Gestão de Clientes!\n"
        "Use o menu para adicionar um cliente.",
        reply_markup=teclado_principal()
    )

async def add_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Digite o nome do cliente:", reply_markup=ReplyKeyboardRemove())
    return ADD_NAME

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nome = update.message.text.strip()
    print(f"DEBUG - Nome recebido: {nome}")
    context.user_data['nome'] = nome
    await update.message.reply_text("Digite o telefone do cliente (com DDD, somente números):")
    return ADD_PHONE

async def add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telefone = update.message.text.strip()
    print(f"DEBUG - Telefone recebido: {telefone}")
    if not telefone_valido(telefone):
        await update.message.reply_text("📵 Telefone inválido. Use apenas números com DDD (ex: 11999998888).")
        return ADD_PHONE
    context.user_data['telefone'] = telefone
    buttons = [[KeyboardButton(f"📦 {p}")] for p in PACOTES]
    await update.message.reply_text(
        "📦 Escolha o pacote do cliente (duração):",
        reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)
    )
    return ADD_PACOTE

async def add_pacote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    print(f"DEBUG - Pacote recebido: {texto}")
    pacote = texto.replace("📦 ", "")
    if pacote not in PACOTES:
        await update.message.reply_text("❗ Pacote inválido. Tente novamente.")
        return ADD_PACOTE
    context.user_data['pacote'] = pacote
    buttons = [[KeyboardButton(f"💰 {p}")] for p in PLANOS]
    await update.message.reply_text(
        "💰 Escolha o valor do plano:",
        reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)
    )
    return ADD_PLANO

async def add_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    print(f"DEBUG - Plano recebido: {texto}")
    try:
        plano = float(texto.replace("💰 ", ""))
        if plano not in PLANOS:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❗ Valor inválido. Tente novamente.")
        return ADD_PLANO

    nome = context.user_data['nome']
    telefone = context.user_data['telefone']
    pacote = context.user_data['pacote']

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes WHERE telefone = ?", (telefone,))
    if cursor.fetchone():
        await update.message.reply_text("⚠️ Cliente com esse telefone já existe.", reply_markup=teclado_principal())
        conn.close()
        return ConversationHandler.END

    meses = get_duracao_meses(pacote)
    vencimento = (datetime.now() + timedelta(days=30 * meses)).strftime("%Y-%m-%d")
    cursor.execute(
        "INSERT INTO clientes (nome, telefone, pacote, plano, vencimento) VALUES (?, ?, ?, ?, ?)",
        (nome, telefone, pacote, plano, vencimento)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Cliente {nome} cadastrado com plano válido até {vencimento}.",
        reply_markup=teclado_principal()
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operação cancelada.", reply_markup=teclado_principal())
    return ConversationHandler.END

def main():
    criar_tabela()
    application = ApplicationBuilder().token(TOKEN).build()

    conv_add = ConversationHandler(
        entry_points=[CommandHandler("addcliente", add_cliente),
                      MessageHandler(filters.Regex("^➕ Adicionar Cliente$") & filters.TEXT, add_cliente)],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)],
            ADD_PACOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pacote)],
            ADD_PLANO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plano)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_add)

    # Também capturamos o clique no botão do teclado principal que é texto
    application.add_handler(MessageHandler(filters.Regex("^➕ Adicionar Cliente$") & filters.TEXT, add_cliente))

    application.run_polling()

if __name__ == "__main__":
    main()
