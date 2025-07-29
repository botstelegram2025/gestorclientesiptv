import os
import csv
import sqlite3
from datetime import datetime, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler,
    filters, ConversationHandler, CallbackQueryHandler
)

TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "clientes.db"

# Estados para ConversationHandler
ADD_NAME, ADD_PHONE, ADD_PACOTE, ADD_PLANO = range(4)
SEND_CLIENTE, SEND_MSG = range(4, 6)

# Planos e pacotes
PACOTES = ["1 mês", "3 meses", "6 meses", "1 ano"]
PLANOS = [30, 35, 40, 45, 60, 65, 70, 90, 110, 135]

mensagens_padrao = {
    "promo": "Olá {nome}, confira nossa promoção especial!",
    "lembrete": "Olá {nome}, só passando para lembrar do seu compromisso amanhã.",
}

def criar_tabela():
    conn = sqlite3.connect(DB_PATH)
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
    conn.commit()
    conn.close()

def get_duracao_meses(pacote):
    mapa = {"1 mês": 1, "3 meses": 3, "6 meses": 6, "1 ano": 12}
    return mapa.get(pacote.lower(), 1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        KeyboardButton("/addcliente"),
        KeyboardButton("/listclientes")
    ], [
        KeyboardButton("/renovarcliente"),
        KeyboardButton("/relatorio")
    ]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Bem-vindo ao Bot de Gestão de Clientes!\n"
        "Escolha uma opção no menu abaixo ou digite um comando.",
        reply_markup=reply_markup
    )

async def add_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Digite o nome do cliente:", reply_markup=ReplyKeyboardRemove())
    return ADD_NAME

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nome'] = update.message.text
    await update.message.reply_text("Digite o telefone do cliente (com DDD):")
    return ADD_PHONE

async def add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['telefone'] = update.message.text
    buttons = [[KeyboardButton(p)] for p in PACOTES]
    await update.message.reply_text("Escolha o pacote do cliente (duração):", reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True))
    return ADD_PACOTE

async def add_pacote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pacote = update.message.text
    if pacote not in PACOTES:
        await update.message.reply_text("Pacote inválido. Tente novamente.")
        return ADD_PACOTE
    context.user_data['pacote'] = pacote
    buttons = [[KeyboardButton(str(p))] for p in PLANOS]
    await update.message.reply_text("Escolha o valor do plano:", reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True))
    return ADD_PLANO

async def add_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        plano = float(update.message.text)
        if plano not in PLANOS:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Valor inválido. Tente novamente.")
        return ADD_PLANO

    nome = context.user_data['nome']
    telefone = context.user_data['telefone']
    pacote = context.user_data['pacote']
    meses = get_duracao_meses(pacote)
    vencimento = (datetime.now() + timedelta(days=30 * meses)).strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO clientes (nome, telefone, pacote, plano, vencimento) VALUES (?, ?, ?, ?, ?)",
                   (nome, telefone, pacote, plano, vencimento))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Cliente {nome} cadastrado até {vencimento}.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def list_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, pacote, plano, vencimento FROM clientes")
    lista = cursor.fetchall()
    conn.close()

    if not lista:
        await update.message.reply_text("Nenhum cliente cadastrado.")
        return

    msg = "Clientes cadastrados:\n"
    for nome, telefone, pacote, plano, venc in lista:
        msg += f"- {nome} ({telefone}): R${plano} ({pacote}) até {venc}\n"
    await update.message.reply_text(msg)

async def renovar_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, vencimento FROM clientes")
    lista = cursor.fetchall()
    conn.close()

    keyboard = [
        [
            InlineKeyboardButton(
                f"🔁 {nome} - {vencimento}", callback_data=f"renovar:{telefone}"
            ),
            InlineKeyboardButton(
                "❌ Cancelar", callback_data=f"cancelar:{telefone}"
            )
        ] for nome, telefone, vencimento in lista
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Selecione um cliente:", reply_markup=reply_markup)

async def callback_opcoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if data.startswith("renovar:"):
        telefone = data.split(":")[1]
        cursor.execute("SELECT nome, pacote, plano FROM clientes WHERE telefone = ?", (telefone,))
        result = cursor.fetchone()
        if not result:
            await query.edit_message_text("Cliente não encontrado.")
            return
        nome, pacote, plano = result
        meses = get_duracao_meses(pacote)
        novo_venc = (datetime.now() + timedelta(days=30 * meses)).strftime("%Y-%m-%d")
        cursor.execute("UPDATE clientes SET vencimento = ? WHERE telefone = ?", (novo_venc, telefone))
        cursor.execute("INSERT INTO renovacoes (telefone, data_renovacao, novo_vencimento, pacote, plano) VALUES (?, ?, ?, ?, ?)",
                       (telefone, datetime.now().strftime("%Y-%m-%d"), novo_venc, pacote, plano))
        conn.commit()
        await query.edit_message_text(f"✅ {nome} renovado até {novo_venc}.")

    elif data.startswith("cancelar:"):
        telefone = data.split(":")[1]
        cursor.execute("DELETE FROM clientes WHERE telefone = ?", (telefone,))
        conn.commit()
        await query.edit_message_text("❌ Cliente removido.")

    conn.close()

async def exportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes")
    rows = cursor.fetchall()
    conn.close()

    with open("clientes_export.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Nome", "Telefone", "Pacote", "Plano", "Vencimento"])
        writer.writerows(rows)

    await update.message.reply_document(document=open("clientes_export.csv", "rb"))

async def relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM renovacoes")
    rows = cursor.fetchall()
    conn.close()

    msg = "📋 Log de renovações:\n"
    for _, tel, data, venc, pacote, plano in rows:
        msg += f"{tel} - {data} -> {venc} ({pacote}, R${plano})\n"
    await update.message.reply_text(msg or "Nenhuma renovação registrada.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    criar_tabela()
    application = ApplicationBuilder().token(TOKEN).build()

    conv_add = ConversationHandler(
        entry_points=[CommandHandler("addcliente", add_cliente)],
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
    application.add_handler(CommandHandler("listclientes", list_clientes))
    application.add_handler(CommandHandler("renovarcliente", renovar_cliente))
    application.add_handler(CallbackQueryHandler(callback_opcoes, pattern="^(renovar|cancelar):"))
    application.add_handler(CommandHandler("exportar", exportar))
    application.add_handler(CommandHandler("relatorio", relatorio))
    application.add_handler(CommandHandler("cancel", cancel))

    application.run_polling()

if __name__ == '__main__':
    main()
