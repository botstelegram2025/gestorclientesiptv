import os
import csv
import re
import sqlite3
import tempfile
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
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

ADD_NAME, ADD_PHONE, ADD_PACOTE, ADD_PLANO = range(4)
ESCOLHER_MENSAGEM = 4

PACOTES = ["1 mês", "3 meses", "6 meses", "1 ano"]
PLANOS = [30, 35, 40, 45, 60, 65, 70, 90, 110, 135]

mensagens_padrao = {
    "promo": "Olá {nome}, confira nossa promoção especial!",
    "lembrete": "Olá {nome}, só passando para lembrar do seu compromisso amanhã.",
    "vencimento_hoje": "Olá {nome}, seu plano vence hoje!",
    "vencido": "Olá {nome}, seu plano está vencido desde ontem."
}

scheduler = BackgroundScheduler()
scheduler.start()

def teclado_principal():
    teclado = [
        ["➕ Adicionar Cliente", "📋 Listar Clientes"],
        ["🔄 Renovar Plano", "📊 Relatório"],
        ["📤 Exportar Dados", "❌ Cancelar Operação"]
    ]
    return ReplyKeyboardMarkup(teclado, resize_keyboard=True)

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

def telefone_valido(telefone):
    return re.match(r'^\d{10,11}$', telefone)

def get_duracao_meses(pacote):
    mapa = {"1 mês": 1, "3 meses": 3, "6 meses": 6, "1 ano": 12}
    return mapa.get(pacote.lower(), 1)

def agendar_lembretes(bot, nome, telefone, vencimento):
    datas = {
        -1: "vencido",
        0: "vencimento_hoje",
        1: "lembrete",
        3: "lembrete"
    }
    for dias, tipo_msg in datas.items():
        quando = datetime.strptime(vencimento, "%Y-%m-%d") - timedelta(days=dias)
        if quando > datetime.now():
            scheduler.add_job(
                lambda n=nome, t=telefone, k=tipo_msg: bot.send_message(chat_id=t, text=mensagens_padrao[k].format(nome=n)),
                'date', run_date=quando
            )

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
    context.user_data['nome'] = update.message.text
    await update.message.reply_text("Digite o telefone do cliente (com DDD):")
    return ADD_PHONE

async def add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telefone = update.message.text.strip()
    if not telefone_valido(telefone):
        await update.message.reply_text("Telefone inválido. Use apenas números com DDD (ex: 11999998888).")
        return ADD_PHONE
    context.user_data['telefone'] = telefone
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

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes WHERE telefone = ?", (telefone,))
    if cursor.fetchone():
        await update.message.reply_text("⚠️ Cliente com esse telefone já existe.")
        conn.close()
        return ConversationHandler.END

    meses = get_duracao_meses(pacote)
    vencimento = (datetime.now() + timedelta(days=30 * meses)).strftime("%Y-%m-%d")
    cursor.execute("INSERT INTO clientes (nome, telefone, pacote, plano, vencimento) VALUES (?, ?, ?, ?, ?)",
                   (nome, telefone, pacote, plano, vencimento))
    conn.commit()
    conn.close()

    agendar_lembretes(context.bot, nome, telefone, vencimento)

    await update.message.reply_text(
        f"✅ Cliente {nome} cadastrado até {vencimento}.",
        reply_markup=teclado_principal()
    )
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
        venc_formatado = datetime.strptime(venc, '%Y-%m-%d').strftime('%d/%m/%Y')
        msg += f"- {nome} ({telefone}): R${plano:.2f} ({pacote}) até {venc_formatado}\n"
    await update.message.reply_text(msg)

async def renovar_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, vencimento FROM clientes")
    lista = cursor.fetchall()
    conn.close()

    keyboard = [
        [
            InlineKeyboardButton(f"🔁 {nome} - {vencimento}", callback_data=f"renovar:{telefone}"),
            InlineKeyboardButton("❌ Cancelar", callback_data=f"cancelar:{telefone}")
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
        conn.close()

        agendar_lembretes(context.bot, nome, telefone, novo_venc)

        await query.edit_message_text(f"✅ {nome} renovado até {novo_venc}.")

    elif data.startswith("cancelar:"):
        telefone = data.split(":")[1]
        cursor.execute("DELETE FROM clientes WHERE telefone = ?", (telefone,))
        conn.commit()
        conn.close()
        await query.edit_message_text("❌ Cliente removido.")

async def exportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes")
    rows = cursor.fetchall()
    conn.close()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", newline="") as tmpfile:
        writer = csv.writer(tmpfile)
        writer.writerow(["ID", "Nome", "Telefone", "Pacote", "Plano", "Vencimento"])
        writer.writerows(rows)
        tmpfile_path = tmpfile.name

    await update.message.reply_document(document=open(tmpfile_path, "rb"))
    os.remove(tmpfile_path)

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

async def enviar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton(k)] for k in mensagens_padrao.keys()]
    await update.message.reply_text("Escolha o tipo de mensagem para enviar:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return ESCOLHER_MENSAGEM

async def escolher_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tipo = update.message.text.strip().lower()
    mensagem = mensagens_padrao.get(tipo)
    if not mensagem:
        await update.message.reply_text("Tipo de mensagem inválido.")
        return ESCOLHER_MENSAGEM

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone FROM clientes")
    clientes = cursor.fetchall()
    conn.close()

    for nome, telefone in clientes:
        texto = mensagem.format(nome=nome)
        try:
            await context.bot.send_message(chat_id=telefone, text=texto)
        except Exception as e:
            print(f"Erro ao enviar para {telefone}: {e}")

    await update.message.reply_text("✅ Mensagens enviadas.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operação cancelada.", reply_markup=teclado_principal())
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

    conv_msg = ConversationHandler(
        entry_points=[CommandHandler("enviarmensagem", enviar_mensagem)],
        states={
            ESCOLHER_MENSAGEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, escolher_mensagem)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_add)
    application.add_handler(conv_msg)
    application.add_handler(CommandHandler("listclientes", list_clientes))
    application.add_handler(CommandHandler("renovarcliente", renovar_cliente))
    application.add_handler(CallbackQueryHandler(callback_opcoes, pattern="^(renovar|cancelar):"))
    application.add_handler(CommandHandler("exportar", exportar))
    application.add_handler(CommandHandler("relatorio", relatorio))
    application.add_handler(CommandHandler("cancel", cancel))

    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^➕ Adicionar Cliente$"), add_cliente))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📋 Listar Clientes$"), list_clientes))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^🔄 Renovar Plano$"), renovar_cliente))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📊 Relatório$"), relatorio))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📤 Exportar Dados$"), exportar))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^❌ Cancelar Operação$"), cancel))

    application.run_polling()

if __name__ == "__main__":
    main()
