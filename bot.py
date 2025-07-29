import os
import csv
import re
import sqlite3
import tempfile
from datetime import datetime, timedelta
from urllib.parse import quote_plus
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

# Coloque aqui o chat_id do admin para receber os avisos
ADMIN_CHAT_ID = 123456789  # <<< SUBSTITUA PELO SEU CHAT_ID REAL

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
    chat_id = update.effective_chat.id  # capturando chat_id do usuário que está cadastrando

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

    await update.message.reply_text(
        f"✅ Cliente {nome} cadastrado com plano válido até {vencimento}.",
        reply_markup=teclado_principal()
    )
    return ConversationHandler.END

# --- MODIFICAÇÃO AQUI --- #
async def list_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, pacote, plano, vencimento FROM clientes")
    lista = cursor.fetchall()
    conn.close()

    if not lista:
        await update.message.reply_text("Nenhum cliente cadastrado.")
        return

    # Envia uma mensagem individual por cliente com botão do WhatsApp
    for nome, telefone, pacote, plano, venc in lista:
        venc_formatado = datetime.strptime(venc, '%Y-%m-%d').strftime('%d/%m/%Y')
        texto = f"👤 {nome}\n📞 {telefone}\n💰 R$ {plano:.2f} ({pacote})\n📅 Vence em {venc_formatado}"

        # Montar link do WhatsApp com mensagem opcional (urlencoded)
        mensagem_whatsapp = quote_plus(f"Olá {nome}, tudo bem?")
        link_whatsapp = f"https://wa.me/{telefone}?text={mensagem_whatsapp}"

        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 WhatsApp", url=link_whatsapp)]
        ])

        await update.message.reply_text(texto, reply_markup=teclado)
# --- FIM DA MODIFICAÇÃO --- #

async def renovar_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, vencimento FROM clientes")
    lista = cursor.fetchall()
    conn.close()

    if not lista:
        await update.message.reply_text("Nenhum cliente cadastrado para renovação.")
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
        cursor.execute("SELECT nome, pacote, plano FROM clientes WHERE telefone = ?", (telefone,))
        result = cursor.fetchone()
        if not result:
            await query.edit_message_text("Cliente não encontrado.")
            conn.close()
            return
        nome, pacote, plano = result
        meses = get_duracao_meses(pacote)
        novo_venc = (datetime.now() + timedelta(days=30 * meses)).strftime("%Y-%m-%d")
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

async def exportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes")
    rows = cursor.fetchall()
    conn.close()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", newline="") as tmpfile:
        writer = csv.writer(tmpfile)
        writer.writerow(["ID", "Nome", "Telefone", "Pacote", "Plano", "Vencimento", "Chat_ID"])
        writer.writerows(rows)
        tmpfile_path = tmpfile.name

    await update.message.reply_document(document=open(tmpfile_path, "rb"), filename="clientes_export.csv")
    os.remove(tmpfile_path)

async def relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM renovacoes")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("Nenhuma renovação registrada.")
        return

    msg = "📋 Log de renovações:\n"
    for _, tel, data, venc, pacote, plano in rows:
        msg += f"{tel} - {data} -> {venc} ({pacote}, R$ {plano})\n"
    await update.message.reply_text(msg)

async def enviar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton(f"📨 {k}")] for k in mensagens_padrao.keys()]
    await update.message.reply_text("Escolha uma mensagem para enviar:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return ESCOLHER_MENSAGEM

async def escolher_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chave = update.message.text.replace("📨 ", "")
    if chave not in mensagens_padrao:
        await update.message.reply_text("Mensagem inválida. Tente novamente.")
        return ESCOLHER_MENSAGEM
    context.user_data['msg_escolhida'] = chave

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, chat_id FROM clientes")
    clientes = cursor.fetchall()
    conn.close()

    count = 0
    for nome, telefone, chat_id_cliente in clientes:
        texto = mensagens_padrao[chave].format(nome=nome)
        try:
            await context.bot.send_message(chat_id=chat_id_cliente or update.effective_chat.id, text=texto)
            count += 1
        except Exception:
            pass

    await update.message.reply_text(f"✅ Mensagem enviada para {count} clientes.", reply_markup=teclado_principal())
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada.", reply_markup=teclado_principal())
    return ConversationHandler.END

# Função que lembra o admin dos vencimentos
async def lembrar_admin_vencimentos(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()

    hoje = datetime.now().date()
    datas_aviso = {
        "3 dias": hoje + timedelta(days=3),
        "1 dia": hoje + timedelta(days=1),
        "vencimento hoje": hoje,
        "1 dia após": hoje - timedelta(days=1),
    }

    resultados = {k: [] for k in datas_aviso.keys()}

    cursor.execute("SELECT nome, telefone, vencimento FROM clientes")
    clientes = cursor.fetchall()
    conn.close()

    for nome, telefone, vencimento in clientes:
        dt_venc = datetime.strptime(vencimento, "%Y-%m-%d").date()
        if dt_venc == datas_aviso["3 dias"]:
            resultados["3 dias"].append((nome, telefone, vencimento))
        elif dt_venc == datas_aviso["1 dia"]:
            resultados["1 dia"].append((nome, telefone, vencimento))
        elif dt_venc == datas_aviso["vencimento hoje"]:
            resultados["vencimento hoje"].append((nome, telefone, vencimento))
        elif dt_venc == datas_aviso["1 dia após"]:
            resultados["1 dia após"].append((nome, telefone, vencimento))

    mensagens = []
    if resultados["3 dias"]:
        mensagens.append("⏳ Planos vencendo em 3 dias:")
        for nome, telefone, venc in resultados["3 dias"]:
            mensagens.append(f"  - {nome} (Tel: {telefone}) vence em {venc}")
    if resultados["1 dia"]:
        mensagens.append("⏳ Planos vencendo em 1 dia:")
        for nome, telefone, venc in resultados["1 dia"]:
            mensagens.append(f"  - {nome} (Tel: {telefone}) vence em {venc}")
    if resultados["vencimento hoje"]:
        mensagens.append("⚠️ Planos vencendo hoje:")
        for nome, telefone, venc in resultados["vencimento hoje"]:
            mensagens.append(f"  - {nome} (Tel: {telefone}) vence hoje!")
    if resultados["1 dia após"]:
        mensagens.append("❌ Planos vencidos ontem:")
        for nome, telefone, venc in resultados["1 dia após"]:
            mensagens.append(f"  - {nome} (Tel: {telefone}) venceu ontem!")

    if mensagens:
        texto = "\n".join(mensagens)
        try:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=texto)
        except Exception as e:
            print(f"Erro ao enviar mensagem ao admin: {e}")

def main():
    criar_tabela()

    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addcliente", add_cliente)],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)],
            ADD_PACOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pacote)],
            ADD_PLANO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plano)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    enviar_msg_handler = ConversationHandler(
        entry_points=[CommandHandler("enviarmensagem", enviar_mensagem)],
        states={
            ESCOLHER_MENSAGEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, escolher_mensagem)]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(enviar_msg_handler)
    application.add_handler(CommandHandler("listclientes", list_clientes))
    application.add_handler(CommandHandler("renovar", renovar_cliente))
    application.add_handler(CallbackQueryHandler(callback_opcoes))
    application.add_handler(CommandHandler("exportar", exportar))
    application.add_handler(CommandHandler("relatorio", relatorio))
    application.add_handler(CommandHandler("cancelar", cancelar))

    # Job para lembrar admin dos vencimentos
    job_queue = application.job_queue
    job_queue.run_daily(lembrar_admin_vencimentos, time=datetime.now().time())

    application.run_polling()

if __name__ == "__main__":
    main()
