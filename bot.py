import os
import re
import sqlite3
from datetime import datetime
from dateutil.relativedelta import relativedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler,
    filters, ConversationHandler, CallbackQueryHandler
)

TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "clientes.db"

ADMIN_CHAT_ID = 123456789  # <<< SUBSTITUA PELO SEU CHAT_ID REAL

ADD_NAME, ADD_PHONE, ADD_PACOTE, ADD_PLANO = range(4)

PACOTES = ["1 mês", "3 meses", "6 meses", "1 ano"]
PLANOS = [30, 35, 40, 45, 60, 65, 70, 90, 110, 135]

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

async def add_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Digite o nome do cliente:", reply_markup=ReplyKeyboardRemove())
    return ADD_NAME

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nome'] = update.message.text.strip()
    await update.message.reply_text("Digite o telefone do cliente (com DDD, somente números):")
    return ADD_PHONE

async def add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telefone = update.message.text.strip()
    if not telefone_valido(telefone):
        await update.message.reply_text("📵 Telefone inválido. Use apenas números com DDD (ex: 11999998888).")
        return ADD_PHONE
    context.user_data['telefone'] = telefone
    buttons = [[KeyboardButton(f"📦 {p}")] for p in PACOTES]
    await update.message.reply_text("📦 Escolha o pacote do cliente (duração):", reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True))
    return ADD_PACOTE

async def add_pacote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pacote = update.message.text.replace("📦 ", "")
    if pacote not in PACOTES:
        await update.message.reply_text("❗ Pacote inválido. Tente novamente.")
        return ADD_PACOTE
    context.user_data['pacote'] = pacote
    buttons = [[KeyboardButton(f"💰 {p}")] for p in PLANOS]
    await update.message.reply_text("💰 Escolha o valor do plano:", reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True))
    return ADD_PLANO

async def add_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        plano = float(update.message.text.replace("💰 ", ""))
        if plano not in PLANOS:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❗ Valor inválido. Tente novamente.")
        return ADD_PLANO

    nome = context.user_data['nome']
    telefone = context.user_data['telefone']
    pacote = context.user_data['pacote']
    chat_id = update.effective_chat.id

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes WHERE telefone = ?", (telefone,))
    if cursor.fetchone():
        await update.message.reply_text("⚠️ Cliente com esse telefone já existe.", reply_markup=teclado_principal())
        conn.close()
        return ConversationHandler.END

    meses = get_duracao_meses(pacote)
    vencimento = (datetime.now().date() + relativedelta(months=meses)).strftime("%Y-%m-%d")

    cursor.execute(
        "INSERT INTO clientes (nome, telefone, pacote, plano, vencimento, chat_id) VALUES (?, ?, ?, ?, ?, ?)",
        (nome, telefone, pacote, plano, vencimento, chat_id)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Cliente {nome} cadastrado com plano válido até {vencimento}.",
        reply_markup=teclado_principal()
    )
    return ConversationHandler.END

async def listar_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, pacote, plano, vencimento FROM clientes ORDER BY nome")
    clientes = cursor.fetchall()
    conn.close()

    if not clientes:
        await update.message.reply_text("Nenhum cliente cadastrado.", reply_markup=teclado_principal())
        return

    buttons = []
    for nome, telefone, pacote, plano, vencimento in clientes:
        label = f"{nome} - {telefone} - {pacote} até {vencimento}"
        buttons.append([
            InlineKeyboardButton(f"🔄 Renovar", callback_data=f"renovar:{telefone}"),
            InlineKeyboardButton(f"❌ Cancelar", callback_data=f"cancelar:{telefone}")
        ])
        buttons.append([InlineKeyboardButton(label, callback_data="ignore")])

    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Lista de clientes:", reply_markup=markup)

async def callback_opcoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "ignore":
        return

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()

    if data.startswith("renovar:"):
        telefone = data.split(":")[1]
        cursor.execute("SELECT nome, pacote, plano, vencimento FROM clientes WHERE telefone = ?", (telefone,))
        result = cursor.fetchone()
        if not result:
            await query.edit_message_text("Cliente não encontrado.")
            conn.close()
            return

        nome, pacote, plano, vencimento_str = result
        meses = get_duracao_meses(pacote)
        vencimento_atual = datetime.strptime(vencimento_str, "%Y-%m-%d").date()

        base_data = max(datetime.now().date(), vencimento_atual)
        novo_venc = (base_data + relativedelta(months=meses)).strftime("%Y-%m-%d")

        cursor.execute("UPDATE clientes SET vencimento = ? WHERE telefone = ?", (novo_venc, telefone))
        cursor.execute(
            "INSERT INTO renovacoes (telefone, data_renovacao, novo_vencimento, pacote, plano) VALUES (?, ?, ?, ?, ?)",
            (telefone, datetime.now().strftime("%Y-%m-%d"), novo_venc, pacote, plano)
        )
        conn.commit()
        conn.close()

        await query.edit_message_text(f"✅ {nome} renovado até {novo_venc}.")

    elif data.startswith("cancelar:"):
        telefone = data.split(":")[1]
        cursor.execute("DELETE FROM clientes WHERE telefone = ?", (telefone,))
        conn.commit()
        conn.close()
        await query.edit_message_text("🗑️ Cliente removido.")

async def cancelar_operacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada.", reply_markup=teclado_principal())
    return ConversationHandler.END

async def mensagem_nao_reconhecida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Comando não reconhecido. Use o menu abaixo.", reply_markup=teclado_principal())

def main():
    criar_tabela()
    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Adicionar Cliente$"), add_cliente)],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)],
            ADD_PACOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pacote)],
            ADD_PLANO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plano)],
        },
        fallbacks=[CommandHandler('cancelar', cancelar_operacao), MessageHandler(filters.Regex("^❌ Cancelar Operação$"), cancelar_operacao)],
        allow_reentry=True,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.Regex("^📋 Listar Clientes$"), listar_clientes))
    application.add_handler(CallbackQueryHandler(callback_opcoes))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem_nao_reconhecida))

    application.run_polling()

if __name__ == "__main__":
    main()
