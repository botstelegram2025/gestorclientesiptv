import os
import csv
import re
import sqlite3
import tempfile
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
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
    "promo": "📢 Olá {nome}, confira nossa promoção especial!",
    "lembrete": "⏰ Olá {nome}, só passando para lembrar do seu compromisso amanhã.",
    "vencimento_hoje": "⚠️ Olá {nome}, seu plano vence hoje!",
    "vencido": "❌ Olá {nome}, seu plano está vencido desde ontem."
}

scheduler = AsyncIOScheduler()
scheduler.start()


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


async def avisar_vencimentos(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    hoje = datetime.now().strftime("%Y-%m-%d")

    # Clientes com vencimento HOJE
    cursor.execute("SELECT nome, chat_id FROM clientes WHERE vencimento = ?", (hoje,))
    vencem_hoje = cursor.fetchall()

    # Clientes com vencimento VENCIDO (anterior a hoje)
    cursor.execute("SELECT nome, chat_id FROM clientes WHERE vencimento < ?", (hoje,))
    vencidos = cursor.fetchall()

    for nome, chat_id in vencem_hoje:
        if chat_id:
            msg = mensagens_padrao["vencimento_hoje"].format(nome=nome)
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg)
            except Exception as e:
                print(f"Erro ao enviar para chat_id {chat_id}: {e}")

    for nome, chat_id in vencidos:
        if chat_id:
            msg = mensagens_padrao["vencido"].format(nome=nome)
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg)
            except Exception as e:
                print(f"Erro ao enviar para chat_id {chat_id}: {e}")

    conn.close()


def agendar_lembretes(bot, nome, chat_id, vencimento):
    # Essa função pode ser mantida para lembretes pontuais quando o cliente é cadastrado ou renovado.
    from datetime import datetime as dt

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
                lambda n=nome, c=chat_id, k=tipo_msg: bot.send_message(chat_id=c, text=mensagens_padrao[k].format(nome=n)),
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
    chat_id = update.effective_chat.id  # captura chat_id do usuário que está cadastrando

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
        "INSERT INTO clientes (nome, telefone, pacote, plano, vencimento, chat_id) VALUES (?, ?, ?, ?, ?, ?)",
        (nome, telefone, pacote, plano, vencimento, chat_id)
    )
    conn.commit()
    conn.close()

    agendar_lembretes(context.bot, nome, chat_id, vencimento)

    await update.message.reply_text(
        f"✅ Cliente {nome} cadastrado com plano válido até {vencimento}.",
        reply_markup=teclado_principal()
    )
    return ConversationHandler.END


async def list_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, pacote, plano, vencimento FROM clientes")
    lista = cursor.fetchall()
    conn.close()

    if not lista:
        await update.message.reply_text("Nenhum cliente cadastrado.")
        return

    msg = "👥 Clientes cadastrados:\n"
    for nome, telefone, pacote, plano, venc in lista:
        venc_formatado = datetime.strptime(venc, '%Y-%m-%d').strftime('%d/%m/%Y')
        msg += f"- {nome} ({telefone}): R$ {plano:.2f} ({pacote}) até {venc_formatado}\n"
    await update.message.reply_text(msg)


async def renovar_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, vencimento FROM clientes")
    lista = cursor.fetchall()
    conn.close()

    if not lista:
        await update.message.reply_text("Nenhum cliente cadastrado.")
        return

    keyboard = [
        [
            InlineKeyboardButton(f"🔁 {nome} - {vencimento}", callback_data=f"renovar:{telefone}"),
            InlineKeyboardButton("🗑️ Cancelar", callback_data=f"cancelar:{telefone}")
        ] for nome, telefone, vencimento in lista
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👥 Selecione um cliente:", reply_markup=reply_markup)


async def callback_opcoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()

    if data.startswith("renovar:"):
        telefone = data.split(":")[1]
        cursor.execute("SELECT nome, pacote, plano, chat_id FROM clientes WHERE telefone = ?", (telefone,))
        result = cursor.fetchone()
        if not result:
            await query.edit_message_text("Cliente não encontrado.")
            conn.close()
            return
        nome, pacote, plano, chat_id = result
        meses = get_duracao_meses(pacote)
        novo_venc = (datetime.now() + timedelta(days=30 * meses)).strftime("%Y-%m-%d")
        cursor.execute("UPDATE clientes SET vencimento = ? WHERE telefone = ?", (novo_venc, telefone))
        cursor.execute(
            "INSERT INTO renovacoes (telefone, data_renovacao, novo_vencimento, pacote, plano) VALUES (?, ?, ?, ?, ?)",
            (telefone, datetime.now().strftime("%Y-%m-%d"), novo_venc, pacote, plano)
        )
        conn.commit()
        conn.close()

        agendar_lembretes(context.bot, nome, chat_id, novo_venc)

        await query.edit_message_text(f"✅ {nome} renovado até {novo_venc}.")

    elif data.startswith("cancelar:"):
        telefone = data.split(":")[1]
        cursor.execute("DELETE FROM clientes WHERE telefone = ?", (telefone,))
        conn.commit()
        conn.close()
        await query.edit_message_text("🗑️ Cliente removido.")


async def exportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes")
    rows = cursor.fetchall()
    conn.close()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", newline="") as tmpfile:
        writer = csv.writer(tmpfile)
        writer.writerow(["ID", "Nome", "Telefone", "Pacote", "Plano", "Vencimento", "ChatID"])
        writer.writerows(rows)
        tmpfile_path = tmpfile.name

    await update.message.reply_document(document=open(tmpfile_path, "rb"), filename="clientes_export.csv")


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada.", reply_markup=teclado_principal())
    return ConversationHandler.END


def main():
    criar_tabela()
    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Adicionar Cliente$"), add_cliente)],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)],
            ADD_PACOTE: [MessageHandler(filters.Regex("^📦 "), add_pacote)],
            ADD_PLANO: [MessageHandler(filters.Regex("^💰 "), add_plano)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar Operação$"), cancelar)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.Regex("^📋 Listar Clientes$"), list_clientes))
    application.add_handler(MessageHandler(filters.Regex("^🔄 Renovar Plano$"), renovar_cliente))
    application.add_handler(CallbackQueryHandler(callback_opcoes))
    application.add_handler(MessageHandler(filters.Regex("^📤 Exportar Dados$"), exportar))
    application.add_handler(MessageHandler(filters.Regex("^❌ Cancelar Operação$"), cancelar))

    # Agendar job diário para avisar vencimentos
    application.job_queue.run_daily(avisar_vencimentos, time=datetime.strptime("09:00", "%H:%M").time())

    application.run_polling()


if __name__ == "__main__":
    main()
