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

# Estados de conversação
ADD_NAME, ADD_PHONE, ADD_PACOTE, ADD_PLANO, ADD_SERVIDOR, ESCOLHER_MENSAGEM, ALTERAR_VENCIMENTO = range(7)

PACOTES = ["1 mês", "3 meses", "6 meses", "1 ano"]
PLANOS = [30, 35, 40, 45, 60, 65, 70, 90, 110, 135]

# Servidores com emojis
SERVIDORES = {
    "Fast Play": "🚀",
    "Genial TV": "📺",
    "EITV": "🎬",
    "Gold Play": "💰",
    "Slim TV": "📡",
    "UniTV": "🎥",
    "Live21": "🔴",
    "ZTech Play": "⚙️",
    "XServer Play": "🖥️"
}

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
        ["📤 Exportar Dados", "❌ Cancelar Operação"],
        ["⏰ Filtrar Vencimentos"]
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
            chat_id INTEGER,
            servidor TEXT
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

# ------------------ HANDLERS ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bem-vindo ao Bot de Gestão de Clientes!\n\n"
        "Escolha uma opção no menu abaixo ou digite um comando.",
        reply_markup=teclado_principal()
    )

# --- ADD CLIENTE ---

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

    context.user_data['plano'] = plano

    # Agora pedir para escolher o servidor
    buttons = [
        [KeyboardButton(f"{emoji} {nome}")] for nome, emoji in SERVIDORES.items()
    ]
    await update.message.reply_text(
        "🌐 Escolha o servidor:",
        reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)
    )
    return ADD_SERVIDOR

async def add_servidor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    # Remover emoji e espaço, se existir
    for nome, emoji in SERVIDORES.items():
        if texto == f"{emoji} {nome}" or texto == nome:
            context.user_data['servidor'] = nome
            break
    else:
        await update.message.reply_text("❗ Servidor inválido. Tente novamente.")
        return ADD_SERVIDOR

    nome = context.user_data['nome']
    telefone = context.user_data['telefone']
    pacote = context.user_data['pacote']
    plano = context.user_data['plano']
    servidor = context.user_data['servidor']
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
        "INSERT INTO clientes (nome, telefone, pacote, plano, vencimento, chat_id, servidor) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (nome, telefone, pacote, plano, vencimento, chat_id, servidor)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Cliente {nome} cadastrado com plano válido até {vencimento} no servidor {servidor}.",
        reply_markup=teclado_principal()
    )
    return ConversationHandler.END

# --- LISTAR CLIENTES COM FILTROS ---

def formatar_cliente_texto(cliente):
    nome, telefone, pacote, plano, vencimento, servidor = cliente
    return f"{nome} ({telefone})\nPacote: {pacote} - Plano: R${plano}\nVence em: {vencimento}\nServidor: {servidor}"

async def listar_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, pacote, plano, vencimento, servidor FROM clientes ORDER BY vencimento")
    clientes = cursor.fetchall()
    conn.close()

    if not clientes:
        await update.message.reply_text("Nenhum cliente cadastrado.", reply_markup=teclado_principal())
        return

    buttons = [
        [InlineKeyboardButton(formatar_cliente_texto(c), callback_data=f"cliente:{c[1]}")] for c in clientes
    ]

    await update.message.reply_text(
        "Clientes cadastrados:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def filtrar_vencimentos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teclado = [
        [KeyboardButton("Vence em 2 dias")],
        [KeyboardButton("Vence em 1 dia")],
        [KeyboardButton("Vence hoje")],
        [KeyboardButton("Vencido há 1 dia")],
        [KeyboardButton("Cancelar")]
    ]
    await update.message.reply_text("Selecione o filtro desejado:", reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True, resize_keyboard=True))

async def aplicar_filtro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    hoje = datetime.now().date()

    if texto == "Cancelar":
        await update.message.reply_text("Operação cancelada.", reply_markup=teclado_principal())
        return ConversationHandler.END

    if texto == "Vence em 2 dias":
        data_alvo = hoje + relativedelta(days=2)
    elif texto == "Vence em 1 dia":
        data_alvo = hoje + relativedelta(days=1)
    elif texto == "Vence hoje":
        data_alvo = hoje
    elif texto == "Vencido há 1 dia":
        data_alvo = hoje - relativedelta(days=1)
    else:
        await update.message.reply_text("Filtro inválido. Tente novamente.")
        return

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, telefone, pacote, plano, vencimento, servidor FROM clientes WHERE vencimento = ? ORDER BY vencimento", (data_alvo.strftime("%Y-%m-%d"),))
    clientes = cursor.fetchall()
    conn.close()

    if not clientes:
        await update.message.reply_text("Nenhum cliente encontrado para o filtro selecionado.", reply_markup=teclado_principal())
        return ConversationHandler.END

    buttons = [
        [InlineKeyboardButton(formatar_cliente_texto(c), callback_data=f"cliente:{c[1]}")] for c in clientes
    ]

    await update.message.reply_text(
        f"Clientes com vencimento em {data_alvo.strftime('%Y-%m-%d')}:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return ConversationHandler.END

# --- CALLBACKS DE OPÇÕES DO CLIENTE ---

async def callback_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telefone = query.data.split(":")[1]

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, pacote, plano, vencimento, servidor FROM clientes WHERE telefone = ?", (telefone,))
    result = cursor.fetchone()
    conn.close()

    if not result:
        await query.edit_message_text("Cliente não encontrado.")
        return ConversationHandler.END

    nome, pacote, plano, vencimento, servidor = result

    teclado = [
        [InlineKeyboardButton("🔄 Renovar Plano", callback_data=f"renovar:{telefone}")],
        [InlineKeyboardButton("🗓 Alterar Vencimento", callback_data=f"alterar_venc:{telefone}")],
        [InlineKeyboardButton("🗑 Remover Cliente", callback_data=f"remover:{telefone}")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="voltar")]
    ]

    await query.edit_message_text(
        f"Cliente: {nome}\nPacote: {pacote}\nPlano: R${plano}\nVencimento: {vencimento}\nServidor: {servidor}",
        reply_markup=InlineKeyboardMarkup(teclado)
    )

async def callback_opcoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("renovar:"):
        telefone = data.split(":")[1]
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT nome, pacote, plano, vencimento FROM clientes WHERE telefone = ?", (telefone,))
        result = cursor.fetchone()
        if not result:
            await query.edit_message_text("Cliente não encontrado.")
            conn.close()
            return ConversationHandler.END

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

        await query.edit_message_text(f"✅ Plano renovado para {nome} até {novo_venc}.")
        return ConversationHandler.END

    elif data.startswith("alterar_venc:"):
        telefone = data.split(":")[1]
        context.user_data['telefone_alterar'] = telefone
        await query.edit_message_text("Por favor, envie a nova data de vencimento no formato AAAA-MM-DD (ex: 2025-08-31)")
        return ALTERAR_VENCIMENTO

    elif data.startswith("remover:"):
        telefone = data.split(":")[1]
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT nome FROM clientes WHERE telefone = ?", (telefone,))
        res = cursor.fetchone()
        if not res:
            await query.edit_message_text("Cliente não encontrado.")
            conn.close()
            return ConversationHandler.END
        nome = res[0]
        cursor.execute("DELETE FROM clientes WHERE telefone = ?", (telefone,))
        conn.commit()
        conn.close()
        await query.edit_message_text(f"🗑 Cliente {nome} removido.")
        return ConversationHandler.END

    elif data.startswith("cliente:"):
        await callback_cliente(update, context)
        return

    elif data == "voltar":
        await query.edit_message_text(
            "Menu Principal:",
            reply_markup=teclado_principal()
        )
        return ConversationHandler.END

    else:
        await query.edit_message_text("Opção desconhecida.")
        return ConversationHandler.END

# --- ALTERAR VENCIMENTO MANUALMENTE ---

async def receber_nova_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    telefone = context.user_data.get('telefone_alterar')

    try:
        nova_data = datetime.strptime(texto, "%Y-%m-%d").date()
        if nova_data < datetime.now().date():
            await update.message.reply_text("❌ Data não pode ser menor que hoje. Envie uma data válida.")
            return ALTERAR_VENCIMENTO
    except ValueError:
        await update.message.reply_text("❌ Formato inválido. Use AAAA-MM-DD.")
        return ALTERAR_VENCIMENTO

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("SELECT nome FROM clientes WHERE telefone = ?", (telefone,))
    res = cursor.fetchone()
    if not res:
        await update.message.reply_text("Cliente não encontrado.")
        conn.close()
        return ConversationHandler.END

    nome = res[0]

    cursor.execute("UPDATE clientes SET vencimento = ? WHERE telefone = ?", (nova_data.strftime("%Y-%m-%d"), telefone))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Vencimento de {nome} alterado para {nova_data.strftime('%Y-%m-%d')}.", reply_markup=teclado_principal())

    return ConversationHandler.END

# --- CANCELAR ---

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada.", reply_markup=teclado_principal())
    return ConversationHandler.END

# --- MAIN ---

def main():
    criar_tabela()

    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(filters.Regex("➕ Adicionar Cliente"), add_cliente),
            MessageHandler(filters.Regex("📋 Listar Clientes"), listar_clientes),
            MessageHandler(filters.Regex("⏰ Filtrar Vencimentos"), filtrar_vencimentos),
            MessageHandler(filters.Regex("Cancelar"), cancelar),
            MessageHandler(filters.Regex("Vence em 2 dias|Vence em 1 dia|Vence hoje|Vencido há 1 dia"), aplicar_filtro)
        ],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & (~filters.COMMAND), add_name)],
            ADD_PHONE: [MessageHandler(filters.TEXT & (~filters.COMMAND), add_phone)],
            ADD_PACOTE: [MessageHandler(filters.TEXT & (~filters.COMMAND), add_pacote)],
            ADD_PLANO: [MessageHandler(filters.TEXT & (~filters.COMMAND), add_plano)],
            ADD_SERVIDOR: [MessageHandler(filters.TEXT & (~filters.COMMAND), add_servidor)],
            ALTERAR_VENCIMENTO: [MessageHandler(filters.TEXT & (~filters.COMMAND), receber_nova_data)],
        },
        fallbacks=[CommandHandler('cancelar', cancelar)]
    )

    application.add_handler(conv_handler)

    # CallbackQueryHandler para os botões inline
    application.add_handler(CallbackQueryHandler(callback_opcoes, pattern=r"renovar:|alterar_venc:|cliente:|voltar|remover:"))

    application.run_polling()

if __name__ == '__main__':
    main()
