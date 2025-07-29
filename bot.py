import os
import csv
import re
import sqlite3
import tempfile
from datetime import datetime, timedelta, time as dtime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler,
    filters, ConversationHandler, CallbackQueryHandler
)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN não definido no ambiente.")

# No Railway, use /tmp para armazenar arquivos e DB (pois /tmp é gravável e temporário)
DB_PATH = "/tmp/clientes.db"

ADMIN_CHAT_ID = 123456789  # <<< Substitua pelo seu chat_id real

ADD_NAME, ADD_PHONE, ADD_PACOTE, ADD_PLANO, ESCOLHER_MENSAGEM = range(5)

PACOTES = ["1 mês", "3 meses", "6 meses", "1 ano"]
PLANOS = [30, 35, 40, 45, 60, 65, 70, 90, 110, 135]

mensagens_padrao = {
    "promo": "📢 Olá {nome}, confira nossa promoção especial!",
    "lembrete": "⏰ Olá {nome}, só passando para lembrar do seu compromisso amanhã.",
    "vencimento_hoje": "⚠️ Olá {nome}, seu plano vence hoje!",
    "vencido": "❌ Olá {nome}, seu plano está vencido desde ontem."
}

def criar_tabela():
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                telefone TEXT UNIQUE NOT NULL,
                pacote TEXT NOT NULL,
                plano REAL NOT NULL,
                vencimento TEXT NOT NULL,
                chat_id INTEGER
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS renovacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telefone TEXT NOT NULL,
                data_renovacao TEXT NOT NULL,
                novo_vencimento TEXT NOT NULL,
                pacote TEXT NOT NULL,
                plano REAL NOT NULL
            )
        ''')

def telefone_valido(telefone: str) -> bool:
    return bool(re.fullmatch(r'\d{10,11}', telefone))

def get_duracao_meses(pacote: str) -> int:
    return {"1 mês":1, "3 meses":3, "6 meses":6, "1 ano":12}.get(pacote, 1)

def teclado_principal():
    teclado = [
        ["➕ Adicionar Cliente", "📋 Listar Clientes"],
        ["🔄 Renovar Plano", "📊 Relatório"],
        ["📤 Exportar Dados", "❌ Cancelar Operação"]
    ]
    return ReplyKeyboardMarkup(teclado, resize_keyboard=True)

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
    nome = update.message.text.strip()
    if not nome:
        await update.message.reply_text("Nome não pode ser vazio. Digite novamente:")
        return ADD_NAME
    context.user_data['nome'] = nome
    await update.message.reply_text("Digite o telefone do cliente (DDD + número, só números):")
    return ADD_PHONE

async def add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telefone = update.message.text.strip()
    if not telefone_valido(telefone):
        await update.message.reply_text("📵 Telefone inválido. Use apenas números com DDD (ex: 11999998888).")
        return ADD_PHONE
    context.user_data['telefone'] = telefone
    buttons = [[KeyboardButton(f"📦 {p}")] for p in PACOTES]
    await update.message.reply_text("📦 Escolha o pacote do cliente (duração):", 
                                    reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True))
    return ADD_PACOTE

async def add_pacote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pacote = update.message.text.replace("📦 ", "").strip()
    if pacote not in PACOTES:
        await update.message.reply_text("❗ Pacote inválido. Tente novamente.")
        return ADD_PACOTE
    context.user_data['pacote'] = pacote
    buttons = [[KeyboardButton(f"💰 {p}")] for p in PLANOS]
    await update.message.reply_text("💰 Escolha o valor do plano:", 
                                    reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True))
    return ADD_PLANO

async def add_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.replace("💰 ", "").strip()
    try:
        plano = float(texto)
        if plano not in PLANOS:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❗ Valor inválido. Tente novamente.")
        return ADD_PLANO

    nome = context.user_data['nome']
    telefone = context.user_data['telefone']
    pacote = context.user_data['pacote']
    chat_id = update.effective_chat.id

    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM clientes WHERE telefone = ?", (telefone,))
        if cursor.fetchone():
            await update.message.reply_text("⚠️ Cliente com esse telefone já existe.", reply_markup=teclado_principal())
            return ConversationHandler.END

        meses = get_duracao_meses(pacote)
        vencimento = (datetime.now() + timedelta(days=30*meses)).strftime("%Y-%m-%d")
        cursor.execute(
            "INSERT INTO clientes (nome, telefone, pacote, plano, vencimento, chat_id) VALUES (?, ?, ?, ?, ?, ?)",
            (nome, telefone, pacote, plano, vencimento, chat_id)
        )
        conn.commit()

    await update.message.reply_text(
        f"✅ Cliente {nome} cadastrado com plano válido até {vencimento}.",
        reply_markup=teclado_principal()
    )
    return ConversationHandler.END

async def list_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nome, telefone, pacote, plano, vencimento FROM clientes ORDER BY nome")
        clientes = cursor.fetchall()

    if not clientes:
        await update.message.reply_text("Nenhum cliente cadastrado.")
        return

    msg = "👥 Clientes cadastrados:\n"
    for nome, telefone, pacote, plano, venc in clientes:
        try:
            venc_dt = datetime.strptime(venc, "%Y-%m-%d")
            venc_str = venc_dt.strftime("%d/%m/%Y")
        except Exception:
            venc_str = venc
        msg += f"- {nome} ({telefone}): R$ {plano:.2f} ({pacote}) até {venc_str}\n"
    await update.message.reply_text(msg)

async def renovar_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nome, telefone, vencimento FROM clientes ORDER BY nome")
        clientes = cursor.fetchall()

    if not clientes:
        await update.message.reply_text("Nenhum cliente cadastrado para renovação.")
        return

    keyboard = []
    for nome, telefone, vencimento in clientes:
        keyboard.append([
            InlineKeyboardButton(f"🔁 {nome} - {vencimento}", callback_data=f"renovar:{telefone}"),
            InlineKeyboardButton("🗑️ Cancelar", callback_data=f"cancelar:{telefone}")
        ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👥 Selecione um cliente:", reply_markup=reply_markup)

async def callback_opcoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()

        if data.startswith("renovar:"):
            telefone = data.split(":", 1)[1]
            cursor.execute("SELECT nome, pacote, plano FROM clientes WHERE telefone = ?", (telefone,))
            res = cursor.fetchone()
            if not res:
                await query.edit_message_text("Cliente não encontrado.")
                return
            nome, pacote, plano = res
            meses = get_duracao_meses(pacote)
            novo_venc = (datetime.now() + timedelta(days=30 * meses)).strftime("%Y-%m-%d")
            cursor.execute("UPDATE clientes SET vencimento = ? WHERE telefone = ?", (novo_venc, telefone))
            cursor.execute(
                "INSERT INTO renovacoes (telefone, data_renovacao, novo_vencimento, pacote, plano) VALUES (?, ?, ?, ?, ?)",
                (telefone, datetime.now().strftime("%Y-%m-%d"), novo_venc, pacote, plano)
            )
            conn.commit()
            await query.edit_message_text(f"✅ {nome} renovado até {novo_venc}.")

        elif data.startswith("cancelar:"):
            telefone = data.split(":", 1)[1]
            cursor.execute("DELETE FROM clientes WHERE telefone = ?", (telefone,))
            conn.commit()
            await query.edit_message_text("🗑️ Cliente removido.")

async def exportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clientes")
        rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("Nenhum dado para exportar.")
        return

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", newline="") as tmpfile:
        writer = csv.writer(tmpfile)
        writer.writerow(["ID", "Nome", "Telefone", "Pacote", "Plano", "Vencimento", "Chat_ID"])
        writer.writerows(rows)
        tmpfile_path = tmpfile.name

    try:
        await update.message.reply_document(document=open(tmpfile_path, "rb"), filename="clientes_export.csv")
    finally:
        os.remove(tmpfile_path)

async def relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT telefone, data_renovacao, novo_vencimento, pacote, plano FROM renovacoes ORDER BY data_renovacao DESC")
        rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("Nenhuma renovação registrada.")
        return

    msg = "📋 Log de renovações:\n"
    for tel, data, venc, pacote, plano in rows:
        msg += f"{tel} - {data} -> {venc} ({pacote}, R$ {plano})\n"
    await update.message.reply_text(msg)

async def enviar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton(f"📨 {k}")] for k in mensagens_padrao.keys()]
    await update.message.reply_text(
        "Escolha uma mensagem para enviar:", 
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ESCOLHER_MENSAGEM

async def escolher_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chave = update.message.text.replace("📨 ", "").strip()
    if chave not in mensagens_padrao:
        await update.message.reply_text("Mensagem inválida. Tente novamente.")
        return ESCOLHER_MENSAGEM
    context.user_data['msg_escolhida'] = chave

    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nome, telefone, chat_id FROM clientes")
        clientes = cursor.fetchall()

    count = 0
    for nome, telefone, chat_id_cliente in clientes:
        texto = mensagens_padrao[chave].format(nome=nome)
        dest_chat_id = chat_id_cliente if chat_id_cliente else update.effective_chat.id
        try:
            await context.bot.send_message(chat_id=dest_chat_id, text=texto)
            count += 1
        except Exception:
            # Pode logar erro aqui se quiser
            pass

    await update.message.reply_text(f"✅ Mensagem enviada para {count} clientes.", reply_markup=teclado_principal())
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada.", reply_markup=teclado_principal())
    return ConversationHandler.END

async def lembrar_admin_vencimentos(context: ContextTypes.DEFAULT_TYPE):
    hoje = datetime.now().date()
    datas_aviso = {
        "3 dias": hoje + timedelta(days=3),
        "1 dia": hoje + timedelta(days=1),
        "vencimento hoje": hoje,
        "1 dia após": hoje - timedelta(days=1),
    }
    resultados = {k: [] for k in datas_aviso.keys()}

    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nome, telefone, vencimento FROM clientes")
        for nome, telefone, venc_str in cursor.fetchall():
            try:
                venc = datetime.strptime(venc_str, "%Y-%m-%d").date()
            except Exception:
                continue
            for label, data_alvo in datas_aviso.items():
                if venc == data_alvo:
                    resultados[label].append(f"{nome} ({telefone}) - vence em {venc.strftime('%d/%m/%Y')}")
                    break

    msg = "📅 *Resumo de vencimentos de clientes*\n\n"
    tem_alerta = False
    for label in ["3 dias", "1 dia", "vencimento hoje", "1 dia após"]:
        clientes = resultados[label]
        if clientes:
            tem_alerta = True
            msg += f"*{label.upper()}*:\n" + "\n".join(clientes) + "\n\n"

    if not tem_alerta:
        msg = "✅ Nenhum cliente para alertar hoje."

    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="Markdown")
    except Exception:
        # Pode logar erro aqui
        pass

def main():
    criar_tabela()

    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(➕ Adicionar Cliente)$"), add_cliente)],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)],
            ADD_PACOTE: [MessageHandler(filters.Regex("^📦"), add_pacote)],
            ADD_PLANO: [MessageHandler(filters.Regex("^💰"), add_plano)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True
    )

    conv_mensagem_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📨"), enviar_mensagem)],
        states={
            ESCOLHER_MENSAGEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, escolher_mensagem)]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(conv_mensagem_handler)
    application.add_handler(MessageHandler(filters.Regex("^(📋 Listar Clientes)$"), list_clientes))
    application.add_handler(MessageHandler(filters.Regex("^(🔄 Renovar Plano)$"), renovar_cliente))
    application.add_handler(CallbackQueryHandler(callback_opcoes))
    application.add_handler(MessageHandler(filters.Regex("^(📤 Exportar Dados)$"), exportar))
    application.add_handler(MessageHandler(filters.Regex("^(📊 Relatório)$"), relatorio))
    application.add_handler(MessageHandler(filters.Regex("^(❌ Cancelar Operação)$"), cancelar))

    # Agendamento diário para avisos (exemplo: 10:00 da manhã)
    from telegram.ext import JobQueue
    job_queue = application.job_queue
    job_queue.run_daily(lembrar_admin_vencimentos, time=dtime(hour=10, minute=0, second=0))

    application.run_polling()

if __name__ == "__main__":
    main()
